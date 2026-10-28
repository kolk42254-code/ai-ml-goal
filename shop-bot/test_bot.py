"""Tests for the AI brain and the WhatsApp/Instagram webhooks, with FAKE messages and a FAKE AI.
No keys and no internet needed.  Run:  python -m pytest -q"""
import hashlib
import hmac
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from google import genai
from google.genai import types

import app as server
import brain
import config
import database
import platforms

CUSTOMER_PHONE = "919876543210"


# ---------- Sample webhooks, shaped like the examples in Meta's docs ----------

def whatsapp_message(text="Hi!", msg_id="wamid.TEST1", msg_type="text"):
    message = {"from": CUSTOMER_PHONE, "id": msg_id, "timestamp": "1758254144", "type": msg_type}
    if msg_type == "text":
        message["text"] = {"body": text}
    else:
        message[msg_type] = {"id": "MEDIA_ID", "mime_type": "image/jpeg"}
    return {"object": "whatsapp_business_account", "entry": [{"id": "1", "changes": [{
        "field": "messages",
        "value": {
            "messaging_product": "whatsapp",
            "metadata": {"display_phone_number": "15551797781", "phone_number_id": "7794189252778687"},
            "contacts": [{"profile": {"name": "Asha"}, "wa_id": CUSTOMER_PHONE}],
            "messages": [message],
        }}]}]}


WHATSAPP_STATUS_UPDATE = {"object": "whatsapp_business_account", "entry": [{"id": "1", "changes": [{
    "field": "messages",
    "value": {
        "messaging_product": "whatsapp",
        "metadata": {"display_phone_number": "15551797781", "phone_number_id": "7794189252778687"},
        "statuses": [{"id": "wamid.SENT1", "status": "read", "recipient_id": CUSTOMER_PHONE}],
    }}]}]}


def instagram_dm(text="Do you have eggless cakes?", mid="aWdfTEST1", echo=False):
    message = {"mid": mid, "text": text}
    sender, recipient = "IGSID_CUSTOMER", "IGID_SHOP"
    if echo:
        message["is_echo"] = True
        sender, recipient = recipient, sender
    return {"object": "instagram", "entry": [{"id": "IGID_SHOP", "time": 1569262486134, "messaging": [{
        "sender": {"id": sender}, "recipient": {"id": recipient},
        "timestamp": 1569262485349, "message": message}]}]}


# ---------- Fakes ----------

class FakeBrain:
    """Pretends to be the AI: it just answers 'AI reply to: <message>'."""
    def __init__(self):
        self.calls = []

    def reply(self, platform, user_id, text, name=""):
        self.calls.append((platform, user_id, text, name))
        return f"AI reply to: {text}"


class FakeChat:
    """Pretends to be a Gemini chat. Records each message and the settings sent with it."""
    def __init__(self, settings, fail=False, script=None):
        self.settings = settings
        self.fail = fail
        self.script = script
        self.sent = []

    def send_message(self, message, config=None):
        self.sent.append((message, config))
        if self.fail:
            raise ConnectionError("pretend the internet is down")
        if self.script:                                   # pretend the AI decided to use a tool
            return SimpleNamespace(text=self.script(message, config))
        return SimpleNamespace(text=f"fake answer {len(self.sent)}")


class FakeGemini:
    """Pretends to be genai.Client: client.chats.create(...) returns a FakeChat."""
    def __init__(self, fail=False, script=None):
        self.created = []
        self.chats = SimpleNamespace(create=self._create)
        self.fail = fail
        self.script = script

    def _create(self, model, config):
        chat = FakeChat(config, self.fail, self.script)
        self.created.append(chat)
        return chat


@pytest.fixture
def client(monkeypatch):
    sent = []
    monkeypatch.setattr(config, "VERIFY_TOKEN", "my-secret-word")
    monkeypatch.setattr(config, "WHATSAPP_APP_SECRET", "")
    monkeypatch.setattr(config, "INSTAGRAM_APP_SECRET", "")
    monkeypatch.setattr(server, "brain", FakeBrain())
    monkeypatch.setattr(platforms, "send_whatsapp", lambda to, text: sent.append(("whatsapp", to, text)))
    monkeypatch.setattr(platforms, "send_instagram", lambda to, text: sent.append(("instagram", to, text)))
    test_client = TestClient(server.app)
    test_client.sent = sent
    return test_client


# ---------- Webhook tests ----------

def test_meta_can_verify_both_webhooks(client):
    for path in ("/whatsapp", "/instagram"):
        r = client.get(path, params={"hub.mode": "subscribe", "hub.verify_token": "my-secret-word",
                                     "hub.challenge": "1158201444"})
        assert r.status_code == 200 and r.text == "1158201444"


def test_wrong_verify_token_is_refused(client):
    r = client.get("/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "1"})
    assert r.status_code == 403


def test_whatsapp_text_gets_ai_reply(client):
    r = client.post("/whatsapp", json=whatsapp_message("Hi!"))
    assert r.status_code == 200
    assert server.brain.calls == [("whatsapp", CUSTOMER_PHONE, "Hi!", "Asha")]
    assert client.sent == [("whatsapp", CUSTOMER_PHONE, "AI reply to: Hi!")]


def test_whatsapp_status_update_is_ignored(client):
    client.post("/whatsapp", json=WHATSAPP_STATUS_UPDATE)
    assert client.sent == []


def test_same_message_twice_is_answered_once(client):
    client.post("/whatsapp", json=whatsapp_message("Hi!", msg_id="wamid.SAME"))
    client.post("/whatsapp", json=whatsapp_message("Hi!", msg_id="wamid.SAME"))
    assert len(client.sent) == 1


def test_photo_gets_text_only_note(client):
    client.post("/whatsapp", json=whatsapp_message(msg_type="image", msg_id="wamid.PHOTO"))
    assert client.sent == [("whatsapp", CUSTOMER_PHONE, server.TEXT_ONLY)]
    assert server.brain.calls == []          # the AI is not asked


def test_instagram_dm_gets_ai_reply(client):
    client.post("/instagram", json=instagram_dm("Do you have eggless cakes?"))
    assert client.sent == [("instagram", "IGSID_CUSTOMER", "AI reply to: Do you have eggless cakes?")]


def test_instagram_echo_of_our_own_reply_is_ignored(client):
    client.post("/instagram", json=instagram_dm("Yes we do!", echo=True))
    assert client.sent == []


def test_fake_signature_is_rejected_and_real_one_accepted(client, monkeypatch):
    monkeypatch.setattr(config, "WHATSAPP_APP_SECRET", "app-secret-123")
    body = json.dumps(whatsapp_message()).encode()
    real = "sha256=" + hmac.new(b"app-secret-123", body, hashlib.sha256).hexdigest()
    headers = {"Content-Type": "application/json"}

    fake = client.post("/whatsapp", content=body, headers={**headers, "X-Hub-Signature-256": "sha256=fake"})
    assert fake.status_code == 401 and client.sent == []

    ok = client.post("/whatsapp", content=body, headers={**headers, "X-Hub-Signature-256": real})
    assert ok.status_code == 200 and len(client.sent) == 1


# ---------- Message splitting ----------

def test_short_reply_is_not_split():
    assert platforms.split_message("Hello!", platforms.INSTAGRAM_MAX_BYTES) == ["Hello!"]


def test_long_instagram_reply_is_split_under_1000_bytes():
    text = "Black Forest cake ₹850 🎂 " * 80
    parts = platforms.split_message(text, platforms.INSTAGRAM_MAX_BYTES)
    assert len(parts) > 1
    assert max(len(p.encode("utf-8")) for p in parts) <= 1000
    assert "".join(parts).replace(" ", "") == text.replace(" ", "")   # nothing lost


# ---------- Brain tests (fake Gemini) ----------

def test_each_customer_gets_own_chat():
    fake = FakeGemini()
    shop = brain.ShopBrain(client=fake)
    assert shop.reply("whatsapp", CUSTOMER_PHONE, "Hi") == "fake answer 1"
    assert shop.reply("whatsapp", CUSTOMER_PHONE, "Price of pineapple cake?") == "fake answer 2"
    shop.reply("web", "abc12345", "Hello")
    assert len(fake.created) == 2                       # 2 customers -> 2 chats
    assert fake.created[0].sent[0][0] == "Hi"


def test_ai_gets_live_menu_every_message_but_not_the_phone_number():
    fake = FakeGemini()
    shop = brain.ShopBrain(client=fake)
    shop.reply("whatsapp", CUSTOMER_PHONE, "Hi", "Asha")
    first = fake.created[0].sent[0][1].system_instruction
    assert "Sweet Crumbs Bakery" in first and "#5 Red Velvet Cake" in first and "3 left" in first
    assert CUSTOMER_PHONE not in first

    database.update_product(5, {"stock": 0})          # the owner marks it sold out...
    shop.reply("whatsapp", CUSTOMER_PHONE, "Is red velvet there?")
    second = fake.created[0].sent[1][1].system_instruction
    assert "#5 Red Velvet Cake" in second and "OUT OF STOCK" in second   # ...and the AI sees it straight away


def test_ai_is_told_if_the_shop_is_open(monkeypatch):
    from datetime import datetime
    tuesday_noon = datetime(2026, 10, 20, 12, 0, tzinfo=config.SHOP_TIMEZONE)   # the sample shop closes on Tuesdays
    monkeypatch.setattr(database, "now", lambda: tuesday_noon)
    fake = FakeGemini()
    brain.ShopBrain(client=fake).reply("web", "abc12345", "Are you open?")
    assert "Closed now, opens tomorrow at 9:00 AM" in fake.created[0].sent[0][1].system_instruction


def test_new_chat_after_max_turns():
    fake = FakeGemini()
    shop = brain.ShopBrain(client=fake)
    for _ in range(brain.MAX_TURNS + 1):
        shop.reply("whatsapp", CUSTOMER_PHONE, "Hi")
    assert len(fake.created) == 2


def test_friendly_fallback_when_ai_fails():
    shop = brain.ShopBrain(client=FakeGemini(fail=True))
    assert shop.reply("whatsapp", CUSTOMER_PHONE, "Hi") == brain.FALLBACK


def test_place_order_tool_saves_order_and_takes_stock():
    shop = brain.ShopBrain(client=FakeGemini())
    tool = shop.make_place_order("whatsapp", CUSTOMER_PHONE)
    result = tool(customer_name="Asha", items="1:2, 9:4", pickup_or_delivery="pickup", delivery_address="",
                  wanted_at="Saturday 5 PM", phone="", notes="eggless")
    assert result.startswith("Order #1 is placed. Total ₹1,800")          # 2 x 850 + 4 x 25
    order = database.get_order(1)
    assert order["phone"] == CUSTOMER_PHONE and order["source"] == "whatsapp" and order["notes"] == "eggless"
    assert database.get_product(1)["stock"] == 4 and database.get_product(9)["stock"] == 26


def test_place_order_tool_reports_problems_to_the_ai():
    tool = brain.ShopBrain(client=FakeGemini()).make_place_order("web", "abc12345")
    too_many = tool(customer_name="Ravi", items="5:9", pickup_or_delivery="pickup", delivery_address="",
                    wanted_at="today", phone="9000000001", notes="")
    assert too_many.startswith("Order NOT placed: Only 3 Red Velvet Cake left")
    unreadable = tool(customer_name="Ravi", items="red velvet", pickup_or_delivery="pickup", delivery_address="",
                      wanted_at="today", phone="9000000001", notes="")
    assert "could not be read" in unreadable
    no_phone = tool(customer_name="Ravi", items="1:1", pickup_or_delivery="pickup", delivery_address="",
                    wanted_at="today", phone="", notes="")
    assert "phone number" in no_phone
    assert database.list_orders() == []                   # nothing was saved


# ---------- The real Gemini library accepts our settings (nothing is sent) ----------

def test_real_gemini_library_accepts_our_chat_and_tool():
    real = genai.Client(api_key="not-a-real-key")
    shop = brain.ShopBrain(client=real)
    settings = shop._settings("web", "abc12345", "")
    chat = real.chats.create(model=config.GEMINI_MODEL, config=settings)   # builds the chat only
    assert chat is not None
    tool = types.FunctionDeclaration.from_callable(client=real._api_client,
                                                   callable=shop.make_place_order("web", "abc12345"))
    assert tool.name == "place_order"
    assert set(tool.parameters.properties) == {"customer_name", "items", "pickup_or_delivery", "delivery_address",
                                               "wanted_at", "phone", "notes"}
