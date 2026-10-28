"""Automatic tests with FAKE messages and a FAKE AI. No keys and no internet needed.
Run:  python -m pytest -q"""
import csv
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
    def __init__(self, settings, fail=False):
        self.settings = settings
        self.fail = fail
        self.sent = []

    def send_message(self, message):
        self.sent.append(message)
        if self.fail:
            raise ConnectionError("pretend the internet is down")
        return SimpleNamespace(text=f"fake answer {len(self.sent)}")


class FakeGemini:
    """Pretends to be genai.Client: client.chats.create(...) returns a FakeChat."""
    def __init__(self, fail=False):
        self.created = []
        self.chats = SimpleNamespace(create=self._create)
        self.fail = fail

    def _create(self, model, config):
        chat = FakeChat(config, self.fail)
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
    server.seen_ids.clear()
    test_client = TestClient(server.app)
    test_client.sent = sent
    return test_client


# ---------- Server tests ----------

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

def test_each_customer_gets_own_chat_and_time_stamp():
    fake = FakeGemini()
    shop = brain.ShopBrain(client=fake)
    assert shop.reply("whatsapp", CUSTOMER_PHONE, "Hi") == "fake answer 1"
    assert shop.reply("whatsapp", CUSTOMER_PHONE, "Price of pineapple cake?") == "fake answer 2"
    shop.reply("instagram", "IGSID_CUSTOMER", "Hello")
    assert len(fake.created) == 2                       # 2 customers -> 2 chats
    first = fake.created[0].sent[0]
    assert first.startswith("[") and first.endswith("] Hi")


def test_shop_info_goes_to_ai_but_phone_number_does_not():
    fake = FakeGemini()
    shop = brain.ShopBrain(client=fake)
    shop.reply("whatsapp", CUSTOMER_PHONE, "Hi", "Asha")
    instructions = fake.created[0].settings.system_instruction
    assert shop.shop_info in instructions and "save_order" in instructions
    assert CUSTOMER_PHONE not in instructions


def test_new_chat_after_max_turns():
    fake = FakeGemini()
    shop = brain.ShopBrain(client=fake)
    for _ in range(brain.MAX_TURNS + 1):
        shop.reply("whatsapp", CUSTOMER_PHONE, "Hi")
    assert len(fake.created) == 2


def test_friendly_fallback_when_ai_fails():
    shop = brain.ShopBrain(client=FakeGemini(fail=True))
    assert shop.reply("whatsapp", CUSTOMER_PHONE, "Hi") == brain.FALLBACK


def test_save_order_tool_writes_csv(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "ORDERS_FILE", tmp_path / "orders.csv")
    shop = brain.ShopBrain(client=FakeGemini())
    shop.make_save_order("whatsapp", CUSTOMER_PHONE)("Asha", "Black Forest 1 kg, eggless (₹900)",
                                                     "Pickup", "Friday 6 PM", "")
    shop.make_save_order("instagram", "IGSID_X")("Ravi", "6 veg puffs", "Delivery to 5 Temple Street",
                                                 "Today 7 PM", "9000000001")
    with open(config.ORDERS_FILE, encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))
    assert [row["customer_name"] for row in rows] == ["Asha", "Ravi"]
    assert rows[0]["phone"] == CUSTOMER_PHONE           # filled in from WhatsApp
    assert rows[1]["phone"] == "9000000001"
    assert "₹900" in rows[0]["items"]
    assert config.ORDERS_FILE.read_bytes().count(b"\xef\xbb\xbf") == 1   # Excel marker only once


# ---------- connect_instagram.py, with Meta's replies faked ----------

def test_connect_instagram_subscribes_the_right_account(monkeypatch, capsys):
    import connect_instagram
    calls = []

    def fake_get(url, params, timeout):
        calls.append(("GET", url, params))
        return SimpleNamespace(json=lambda: {"data": [{"user_id": "17841400000000", "username": "sweetcrumbs"}]})

    def fake_post(url, params, timeout):
        calls.append(("POST", url, params))
        return SimpleNamespace(json=lambda: {"success": True})

    monkeypatch.setattr(config, "INSTAGRAM_TOKEN", "fake-token")
    monkeypatch.setattr(config, "GRAPH_API_VERSION", "v26.0")
    monkeypatch.setattr(connect_instagram.requests, "get", fake_get)
    monkeypatch.setattr(connect_instagram.requests, "post", fake_post)
    connect_instagram.main()

    assert calls[1] == ("POST", "https://graph.instagram.com/v26.0/17841400000000/subscribed_apps",
                        {"subscribed_fields": "messages", "access_token": "fake-token"})
    assert "@sweetcrumbs" in capsys.readouterr().out


# ---------- The real Gemini library accepts our settings (nothing is sent) ----------

def test_real_gemini_library_accepts_our_chat_and_tool():
    real = genai.Client(api_key="not-a-real-key")
    shop = brain.ShopBrain(client=real)
    chat = shop._new_chat("whatsapp", CUSTOMER_PHONE, "Asha")      # builds the chat only
    assert chat is not None
    tool = types.FunctionDeclaration.from_callable(client=real._api_client,
                                                   callable=shop.make_save_order("whatsapp", "1"))
    assert tool.name == "save_order"
    assert set(tool.parameters.properties) == {"customer_name", "items", "pickup_or_delivery",
                                               "date_and_time", "phone"}
