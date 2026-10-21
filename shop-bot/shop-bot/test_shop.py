"""Tests for the shop website: menu, cart orders, stock, offers, owner sign-in and owner changes.
No keys and no internet needed.  Run:  python -m pytest -q"""
import base64
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

import app as server
import config
import database
from test_bot import FakeGemini

# A real 1x1 pixel PNG photo
TINY_PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")


@pytest.fixture
def web():
    return TestClient(server.app)


@pytest.fixture
def owner(web, monkeypatch):
    """A browser where the owner is signed in."""
    monkeypatch.setattr(config, "OWNER_PASSWORD", "cake-secret-2026")
    assert web.post("/api/owner/login", json={"password": "cake-secret-2026"}).status_code == 200
    return web


def order(web, items, fulfilment="pickup", address="", **extra):
    body = {"customer_name": "Asha", "phone": "98765 43210", "fulfilment": fulfilment, "address": address,
            "wanted_at": "today 6 PM", "notes": "", "items": [{"product_id": i, "quantity": q} for i, q in items]}
    return web.post("/api/orders", json={**body, **extra})


def product(web, product_id):
    return next(p for p in web.get("/api/shop").json()["products"] if p["id"] == product_id)


# ---------- pages ----------

def test_pages_load_with_browser_protection(web):
    for path in ("/", "/owner"):
        page = web.get(path)
        assert page.status_code == 200 and "<!doctype html>" in page.text
        assert "script-src 'self'" in page.headers["content-security-policy"]
    assert web.get("/health").json() == {"status": "Shop chatbot is running"}
    assert web.get("/static/fonts/baloo-tamma-2.woff2").status_code == 200
    icon = web.get("/favicon.ico")
    assert icon.status_code == 200 and icon.headers["content-type"].startswith("image/svg+xml")


def test_shop_shows_the_sample_menu(web):
    data = web.get("/api/shop").json()
    assert data["shop"]["shop_name"] == "Sweet Crumbs Bakery"
    assert len(data["products"]) == 12 and data["status"]["text"]
    truffle = next(p for p in data["products"] if p["name"] == "Chocolate Truffle Cake")
    assert truffle["offer_price"] == 799 and truffle["current_price"] == 799   # the sample offer


# ---------- cart orders ----------

def test_cart_order_works_out_total_and_takes_stock(web):
    r = order(web, [(1, 2), (6, 3)])
    assert r.status_code == 200
    placed = r.json()["order"]
    assert placed["subtotal"] == 2 * 850 + 3 * 70 and placed["delivery_fee"] == 0 and placed["total"] == 1910
    assert placed["phone"] == "9876543210" and placed["source"] == "cart" and placed["status"] == "new"
    assert product(web, 1)["stock"] == 4 and product(web, 6)["stock"] == 17


def test_delivery_fee_only_below_the_free_limit(web):
    small = order(web, [(9, 2)], fulfilment="delivery", address="5 Temple Street, Ward 3").json()["order"]
    assert (small["subtotal"], small["delivery_fee"], small["total"]) == (50, 40, 90)
    big = order(web, [(1, 1)], fulfilment="delivery", address="5 Temple Street, Ward 3").json()["order"]
    assert big["delivery_fee"] == 0 and big["total"] == 850


def test_cannot_order_more_than_the_stock(web):
    r = order(web, [(5, 4)])                       # Red Velvet Cake has 3
    assert r.status_code == 400 and "Only 3 Red Velvet Cake left" in r.json()["detail"]
    assert product(web, 5)["stock"] == 3           # nothing was taken


def test_same_item_twice_is_joined_before_checking_stock(web):
    assert order(web, [(5, 2), (5, 2)]).status_code == 400


def test_order_needs_good_details(web):
    assert "delivery address" in order(web, [(1, 1)], fulfilment="delivery").json()["detail"]
    assert "phone number" in order(web, [(1, 1)], phone="12345").json()["detail"]
    assert "name" in order(web, [(1, 1)], customer_name="  ").json()["detail"]
    assert "no items" in order(web, []).json()["detail"]
    assert order(web, [(999, 1)]).status_code == 400


def test_offer_price_is_used_only_while_the_offer_runs(web, monkeypatch):
    truffle = product(web, 2)
    assert order(web, [(2, 1)]).json()["order"]["total"] == 799
    after = datetime.fromisoformat(truffle["offer_ends_at"]) + timedelta(minutes=1)
    monkeypatch.setattr(database, "now", lambda: after)
    assert product(web, 2)["offer_price"] is None
    assert order(web, [(2, 1)]).json()["order"]["total"] == 950


def test_too_many_orders_from_one_device_are_slowed_down(web):
    codes = [order(web, [(9, 1)]).status_code for _ in range(11)]
    assert codes[:10] == [200] * 10 and codes[10] == 429


# ---------- owner sign-in ----------

def test_owner_pages_need_sign_in(web, monkeypatch):
    monkeypatch.setattr(config, "OWNER_PASSWORD", "cake-secret-2026")
    assert web.get("/api/owner/orders").status_code == 401
    assert web.patch("/api/owner/products/1", json={"price": 1}).status_code == 401
    assert web.get("/api/owner/me").json() == {"signed_in": False, "password_set": True}


def test_owner_sign_in_is_off_without_a_password(web, monkeypatch):
    monkeypatch.setattr(config, "OWNER_PASSWORD", "")
    r = web.post("/api/owner/login", json={"password": ""})
    assert r.status_code == 503 and "OWNER_PASSWORD" in r.json()["detail"]


def test_wrong_passwords_lock_the_door_for_ten_minutes(web, monkeypatch):
    monkeypatch.setattr(config, "OWNER_PASSWORD", "cake-secret-2026")
    messages = [web.post("/api/owner/login", json={"password": "guess"}).json()["detail"] for _ in range(5)]
    assert messages[0] == "Wrong password. 4 tries left." and "Wait 10 minutes" in messages[4]
    locked = web.post("/api/owner/login", json={"password": "cake-secret-2026"})
    assert locked.status_code == 429


def test_sign_out_ends_the_session(owner):
    assert owner.get("/api/owner/orders").status_code == 200
    owner.post("/api/owner/logout")
    assert owner.get("/api/owner/orders").status_code == 401


# ---------- owner changes show in the shop ----------

def test_owner_changes_price_stock_and_hides_items(owner):
    assert owner.patch("/api/owner/products/1", json={"price": 900, "stock": 0}).status_code == 200
    black_forest = product(owner, 1)
    assert black_forest["price"] == 900 and black_forest["stock"] == 0
    assert order(owner, [(1, 1)]).json()["detail"] == "Sorry, Black Forest Cake is sold out."

    owner.patch("/api/owner/products/3", json={"visible": False})
    assert all(p["id"] != 3 for p in owner.get("/api/shop").json()["products"])
    assert order(owner, [(3, 1)]).json()["detail"] == "Item #3 is not on the menu."


def test_owner_checks_bad_values(owner):
    assert owner.patch("/api/owner/products/1", json={"price": 0}).status_code == 400
    assert owner.patch("/api/owner/products/1", json={"stock": -1}).status_code == 400
    assert owner.patch("/api/owner/products/1", json={"name": "   "}).status_code == 400
    assert owner.patch("/api/owner/products/2", json={"price": 700}).status_code == 400   # below its live offer
    assert owner.patch("/api/owner/products/999", json={"price": 10}).status_code == 404


def test_owner_starts_and_ends_offers(owner):
    assert owner.put("/api/owner/products/1/offer", json={"offer_price": 900}).status_code == 400  # not cheaper
    r = owner.put("/api/owner/products/1/offer", json={"offer_price": 699, "preset": "1h"})
    assert r.status_code == 200
    ends = datetime.fromisoformat(r.json()["product"]["offer_ends_at"])
    assert timedelta(minutes=59) < ends - database.now() <= timedelta(hours=1)
    assert product(owner, 1)["current_price"] == 699
    owner.delete("/api/owner/products/1/offer")
    assert product(owner, 1)["offer_price"] is None


def test_custom_offer_time_is_india_time_and_must_be_future(owner):
    soon = (database.now() + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M")
    ok = owner.put("/api/owner/products/4/offer", json={"offer_price": 700, "preset": "custom", "ends_at": soon})
    assert ok.json()["product"]["offer_ends_at"].startswith(soon) and ok.json()["product"]["offer_ends_at"].endswith("+05:30")
    past = (database.now() - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M")
    r = owner.put("/api/owner/products/4/offer", json={"offer_price": 700, "preset": "custom", "ends_at": past})
    assert r.status_code == 400 and "future" in r.json()["detail"]


def test_owner_adds_and_deletes_items(owner):
    r = owner.post("/api/owner/products", json={"name": "Plum Cake", "category": "Cakes", "price": 450, "stock": 8,
                                                "emoji": "🎂", "description": "500 g, Christmas special"})
    new_id = r.json()["product"]["id"]
    assert product(owner, new_id)["name"] == "Plum Cake"
    assert owner.post("/api/owner/products", json={"name": "No price", "category": "Cakes", "price": 0}).status_code == 400
    assert owner.delete(f"/api/owner/products/{new_id}").status_code == 200
    assert all(p["id"] != new_id for p in owner.get("/api/shop").json()["products"])


def test_owner_photos_must_be_real_photos(owner):
    png = "data:image/png;base64," + base64.b64encode(TINY_PNG).decode()
    r = owner.put("/api/owner/products/1/photo", json={"image": png})
    assert r.status_code == 200
    path = r.json()["product"]["image"]
    assert path.startswith("/uploads/") and (config.UPLOADS_DIR / path.split("/")[-1]).exists()

    fake = "data:image/png;base64," + base64.b64encode(b"<script>alert(1)</script>").decode()
    assert owner.put("/api/owner/products/1/photo", json={"image": fake}).status_code == 400
    assert owner.put("/api/owner/products/1/photo", json={"image": "data:text/html;base64,PGI+"}).status_code == 400

    owner.delete("/api/owner/products/1/photo")
    assert not (config.UPLOADS_DIR / path.split("/")[-1]).exists()     # old file cleaned up


# ---------- orders on the owner desk ----------

def test_order_moves_along_and_cancel_puts_stock_back(owner):
    placed = order(owner, [(5, 2)]).json()["order"]
    assert product(owner, 5)["stock"] == 1
    for status in ("preparing", "ready"):
        assert owner.post(f"/api/owner/orders/{placed['id']}/status", json={"status": status}).json()["order"]["status"] == status
    owner.post(f"/api/owner/orders/{placed['id']}/status", json={"status": "cancelled"})
    assert product(owner, 5)["stock"] == 3
    again = owner.post(f"/api/owner/orders/{placed['id']}/status", json={"status": "new"})
    assert again.status_code == 400 and "cancelled" in again.json()["detail"]


def test_owner_sees_todays_numbers(owner):
    order(owner, [(1, 1)])
    second = order(owner, [(9, 2)]).json()["order"]
    owner.post(f"/api/owner/orders/{second['id']}/status", json={"status": "cancelled"})
    stats = owner.get("/api/owner/orders").json()["stats"]
    assert stats == {"today_orders": 1, "today_revenue": 850, "waiting": 1, "low_stock": 1}


# ---------- shop details ----------

def test_shop_details_are_checked_and_shown(owner):
    bad = owner.put("/api/owner/settings", json={"open_time": "21:00", "close_time": "09:00"})
    assert bad.status_code == 400 and "closing time" in bad.json()["detail"]
    week = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    assert owner.put("/api/owner/settings", json={"closed_days": week}).status_code == 400
    ok = owner.put("/api/owner/settings", json={"shop_name": "Lohi's Cakes", "delivery_fee": 30, "closed_days": ["Monday"]})
    assert ok.status_code == 200
    shop = owner.get("/api/shop").json()["shop"]
    assert shop["shop_name"] == "Lohi's Cakes" and shop["delivery_fee"] == 30 and shop["closed_days"] == ["Monday"]


@pytest.mark.parametrize("when, expected", [
    (datetime(2026, 10, 21, 11, 0), "Open now, closes at 9:00 PM"),            # Wednesday morning
    (datetime(2026, 10, 21, 7, 30), "Closed now, opens today at 9:00 AM"),     # Wednesday, too early
    (datetime(2026, 10, 19, 22, 0), "Closed now, opens on Wednesday at 9:00 AM"),  # Monday night, Tuesday closed
    (datetime(2026, 10, 20, 12, 0), "Closed now, opens tomorrow at 9:00 AM"),  # Tuesday (closed day)
])
def test_open_and_closed_messages(when, expected):
    at = when.replace(tzinfo=config.SHOP_TIMEZONE)
    assert database.shop_status(database.get_settings(), at)["text"] == expected


# ---------- the AI assistant on the website ----------

def test_chat_can_place_a_real_order(web, monkeypatch):
    def pretend_ai(message, settings):
        if message == "yes please":
            tool = settings.tools[0]                    # the AI calls place_order
            return tool(customer_name="Meera", items="8:2", pickup_or_delivery="pickup", delivery_address="",
                        wanted_at="today 5 PM", phone="9123456780", notes="")
        return "Two red velvet pastries for ₹180. Shall I place the order?"

    monkeypatch.setattr(server, "brain", server.ShopBrain(client=FakeGemini(script=pretend_ai)))
    first = web.post("/api/chat", json={"chat_id": "chat-test-01", "message": "2 red velvet pastries"}).json()
    assert first["orders"] == [] and "Shall I place" in first["reply"]
    second = web.post("/api/chat", json={"chat_id": "chat-test-01", "message": "yes please"}).json()
    assert second["reply"].startswith("Order #1 is placed. Total ₹180")
    assert second["orders"][0]["source"] == "chat" and second["orders"][0]["customer_name"] == "Meera"
    assert product(web, 8)["stock"] == 10


def test_chat_checks_its_input(web):
    assert web.post("/api/chat", json={"chat_id": "x", "message": "hi"}).status_code == 422
    assert web.post("/api/chat", json={"chat_id": "chat-test-01", "message": "a" * 501}).status_code == 422


def test_chat_without_a_gemini_key_says_so(web, monkeypatch):
    monkeypatch.setattr(server, "brain", None)
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")
    r = web.post("/api/chat", json={"chat_id": "chat-test-01", "message": "hi"})
    assert r.status_code == 503 and "cart" in r.json()["detail"]


# ---------- small helpers ----------

@pytest.mark.parametrize("amount, text", [(850, "850"), (1050, "1,050"), (105000, "1,05,000"), (12345678, "1,23,45,678")])
def test_rupees_use_indian_grouping(amount, text):
    assert database.rupees(amount) == text


def test_menu_for_the_ai_shows_offers_and_sold_out_items():
    database.update_product(9, {"stock": 0})
    menu = database.menu_text()
    assert "#2 Chocolate Truffle Cake [Cakes]: OFFER ₹799 (normal price ₹950), offer ends" in menu
    assert "#9 Veg Puff [Puffs and snacks]: ₹25; OUT OF STOCK." in menu
