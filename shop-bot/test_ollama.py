"""Tests for the local-model assistant (Ollama, like gemma4:e2b), with a pretend Ollama. No internet needed."""
import json

from fastapi.testclient import TestClient

import app as server
import brain
import config
import database


class FakeOllama:
    """Pretends to be Ollama's /api/chat. `script(payload)` returns the message the model sends back."""
    def __init__(self, script):
        self.script, self.calls = script, []

    def __call__(self, url, payload):
        self.calls.append(payload)
        return {"message": self.script(payload)}


ORDER_ARGS = {"customer_name": "Ravi", "items": "9:2", "pickup_or_delivery": "pickup", "delivery_address": "",
              "wanted_at": "today 8 PM", "phone": "9123456780", "notes": "less spicy"}


def test_local_model_places_a_real_order_through_python():
    def model(payload):
        last = payload["messages"][-1]
        if last["role"] == "tool":                       # the order result came back: confirm to the customer
            return {"role": "assistant", "content": "**Done!** " + last["content"].split(".")[0] + "."}
        if last["content"] == "yes":
            return {"role": "assistant", "content": "", "tool_calls": [
                {"function": {"name": "place_order", "arguments": ORDER_ARGS}}]}
        return {"role": "assistant", "content": "2 Veg Puff, Rs 50. Shall I place the order?"}

    fake = FakeOllama(model)
    bot = brain.OllamaBrain(post=fake, model="gemma4:e2b")
    first, orders = bot.chat("web", "chat-test-01", "2 veg puffs please")
    assert "Shall I place" in first and orders == []
    answer, orders = bot.chat("web", "chat-test-01", "yes")
    assert answer == "Done! Order #1 is placed."                # markdown stars cleaned away
    assert orders[0]["total"] == 50 and orders[0]["notes"] == "less spicy" and orders[0]["track_token"]
    assert database.get_product(9)["stock"] == 28              # Python took the stock
    sent = fake.calls[-1]
    assert sent["model"] == "gemma4:e2b" and sent["tools"][0]["function"]["name"] == "place_order"
    assert "#9 Veg Puff" in sent["messages"][0]["content"]     # the live menu goes with every message
    assert [m["role"] for m in sent["messages"][1:3]] == ["user", "assistant"]   # it remembers the chat


def test_model_without_tools_or_thinking_still_answers():
    def model(payload):
        if payload.get("think") is not None:
            raise brain.OllamaError('"gemma4:e2b" does not support thinking')
        if "tools" in payload:
            raise brain.OllamaError('registry.ollama.ai/library/gemma4:e2b does not support tools')
        assert "can't place orders" in payload["messages"][0]["content"]   # told to send customers to the cart
        return {"role": "assistant", "content": "Please add the items to the cart to order."}

    bot = brain.OllamaBrain(post=FakeOllama(model))
    answer, orders = bot.chat("web", "chat-test-02", "I want to order")
    assert answer == "Please add the items to the cart to order." and orders == []
    assert bot.use_tools is False and bot.use_think is False


def test_ollama_closed_gives_the_friendly_fallback():
    def closed(url, payload):
        raise ConnectionRefusedError("Ollama is not running")

    bot = brain.OllamaBrain(post=closed)
    assert bot.reply("web", "chat-test-03", "hi") == brain.FALLBACK
    assert bot.sessions["web:chat-test-03"]["history"] == []   # the failed message isn't kept


def test_bad_order_from_the_model_is_refused_by_python():
    def model(payload):
        last = payload["messages"][-1]
        if last["role"] == "tool":
            return {"role": "assistant", "content": last["content"]}
        return {"role": "assistant", "content": "", "tool_calls": [{"function": {
            "name": "place_order", "arguments": {**ORDER_ARGS, "items": "5:99"}}}]}   # more than the stock

    answer, orders = brain.OllamaBrain(post=FakeOllama(model)).chat("web", "chat-test-04", "yes")
    assert answer.startswith("Order NOT placed") and orders == []


def test_shop_chat_uses_the_local_model_when_switched_on(monkeypatch):
    monkeypatch.setattr(config, "AI_PROVIDER", "ollama")
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")           # no Google key needed
    monkeypatch.setattr(server, "brain", None)
    monkeypatch.setattr(brain, "_ollama_post", FakeOllama(lambda p: {"role": "assistant", "content": "Namaste!"}))
    r = TestClient(server.app).post("/api/chat", json={"chat_id": "chat-test-05", "message": "hi"})
    assert r.status_code == 200 and r.json()["reply"] == "Namaste!"
    assert isinstance(server.brain, brain.OllamaBrain)


def test_owner_can_see_which_model_answers(monkeypatch):
    web = TestClient(server.app)
    assert web.get("/api/owner/assistant").status_code == 401           # customers can't see it
    monkeypatch.setattr(config, "OWNER_PASSWORD", "cake-secret-2026")
    web.post("/api/owner/login", json={"password": "cake-secret-2026"})
    monkeypatch.setattr(config, "AI_PROVIDER", "ollama")
    monkeypatch.setattr(config, "OLLAMA_MODEL", "gemma4:e2b")
    assert web.get("/api/owner/assistant").json() == {"assistant": "gemma4:e2b (Ollama, on this computer)"}
    monkeypatch.setattr(config, "AI_PROVIDER", "gemini")
    assert "Google Gemini" in web.get("/api/owner/assistant").json()["assistant"]


def test_a_pretend_order_never_reaches_the_customer():
    fake_claim = "I have placed your order. Your order number is [Order Number] and the total amount is Rs 2,100. Thank you!"
    bot = brain.OllamaBrain(post=FakeOllama(lambda p: {"role": "assistant", "content": fake_claim}))
    answer, orders = bot.chat("web", "chat-test-06", "yes")
    assert orders == [] and database.list_orders() == []
    assert answer.startswith("Sorry, I couldn't place the order") and "+91 90000 00000" in answer


def test_blanks_are_filled_with_the_real_order_number():
    def model(payload):
        last = payload["messages"][-1]
        if last["role"] == "tool":
            return {"role": "assistant", "content": "Your order number is [Order Number]. Thank you!"}
        return {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "place_order", "arguments": ORDER_ARGS}}]}

    answer, orders = brain.OllamaBrain(post=FakeOllama(model)).chat("web", "chat-test-07", "yes")
    assert answer == f"Your order number is #{orders[0]['id']}. Thank you!"


def test_normal_questions_are_not_mistaken_for_order_claims():
    for text in ("Shall I place the order?", "Paneer Butter Masala (Rs 210) is vegetarian.",
                 "To order, tell me your name and phone number."):
        assert brain.honest_reply(text, []) == text


def test_gemini_path_is_guarded_too():
    from test_bot import FakeGemini
    lie = lambda message, settings: "Order #7 is placed. Total Rs 500."
    answer, orders = server.ShopBrain(client=FakeGemini(script=lie)).chat("web", "chat-test-08", "yes")
    assert orders == [] and answer.startswith("Sorry, I couldn't place the order")


def form_model(form, claim="Order placed successfully! Your order number is [Order Number]."):
    """A model that never calls the tool, claims the order, and fills the order form when asked."""
    def model(payload):
        if "format" in payload:
            return {"role": "assistant", "content": json.dumps(form)}
        last = payload["messages"][-1]["content"]
        return {"role": "assistant", "content": claim if last == "yes" else "2 Veg Puff, Rs 50. Shall I place it?"}
    return model


GOOD_FORM = {"confirmed": True, "customer_name": "Ravi", "items": [{"item_id": 9, "quantity": 2}],
             "pickup_or_delivery": "pickup", "delivery_address": "", "wanted_at": "today 8 PM",
             "phone": "9123456780", "notes": ""}


def test_small_model_that_skips_the_tool_still_places_a_real_order():
    fake = FakeOllama(form_model(GOOD_FORM))
    bot = brain.OllamaBrain(post=fake)
    bot.chat("web", "chat-test-09", "2 veg puffs, pickup 8 PM, Ravi, 9123456780")
    answer, orders = bot.chat("web", "chat-test-09", "yes")
    assert len(orders) == 1 and orders[0]["total"] == 50 and database.get_product(9)["stock"] == 28
    assert answer == f"Your order #{orders[0]['id']} is placed: 2 x Veg Puff. Total Rs 50 (pickup at the shop). " \
                     "You pay at pickup or delivery. You can follow it in My orders."
    assert fake.calls[-1]["format"]["required"][0] == "confirmed"      # Ollama was asked for the strict form


def test_order_form_problems_are_explained_not_faked():
    no_phone = {**GOOD_FORM, "phone": ""}
    answer, orders = brain.OllamaBrain(post=FakeOllama(form_model(no_phone))).chat("web", "chat-test-10", "yes")
    assert orders == [] and answer.startswith("I couldn't place the order yet:") and "phone number" in answer
    unconfirmed = {**GOOD_FORM, "confirmed": False}
    answer, orders = brain.OllamaBrain(post=FakeOllama(form_model(unconfirmed))).chat("web", "chat-test-11", "yes")
    assert orders == [] and answer.startswith("Sorry, I couldn't place the order")
    assert database.list_orders() == []


def test_no_order_form_without_the_customer_saying_yes():
    fake = FakeOllama(form_model(GOOD_FORM, claim="Your order is placed!"))
    answer, orders = brain.OllamaBrain(post=fake).chat("web", "chat-test-12", "what time do you close?")
    assert orders == [] and not any("format" in call for call in fake.calls)


def test_yes_in_other_languages():
    for text in ("yes please", "OK", "haan", "ಹೌದು", "हाँ ठीक है", "sari, place it"):
        assert brain.said_yes(text), text
    for text in ("what is the price?", "no", "cancel"):
        assert not brain.said_yes(text), text
