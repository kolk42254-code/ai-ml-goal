"""Tests for order tracking (My orders), stock history, earnings, order search, the spreadsheet download,
settings for any kind of shop, and upgrading a shop.db made by an older version.
No keys and no internet needed.  Run:  python -m pytest -q"""
import json
import sqlite3
from contextlib import closing
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

import app as server
import config
import database
from test_bot import FakeGemini
from test_shop import order, product


@pytest.fixture
def web():
    return TestClient(server.app)


@pytest.fixture
def owner(web, monkeypatch):
    monkeypatch.setattr(config, "OWNER_PASSWORD", "cake-secret-2026")
    assert web.post("/api/owner/login", json={"password": "cake-secret-2026"}).status_code == 200
    return web


def mine(web, *tokens):
    r = web.post("/api/my-orders", json={"tokens": list(tokens)})
    assert r.status_code == 200
    return r.json()["orders"]


def set_status(owner, order_id, status):
    return owner.post(f"/api/owner/orders/{order_id}/status", json={"status": status})


# ---------- My orders: the customer follows their order ----------

def test_customer_sees_the_owner_confirm_their_order(owner):
    placed = order(owner, [(1, 1)]).json()["order"]
    token = placed["track_token"]
    assert len(token) >= 16
    [seen] = mine(owner, token)
    assert seen["id"] == placed["id"] and seen["status"] == "new" and seen["can_cancel"]
    assert seen["times"]["new"] == placed["created_at"] and seen["token"] == token

    set_status(owner, placed["id"], "preparing")                     # the owner confirms
    [seen] = mine(owner, token)
    assert seen["status"] == "preparing" and not seen["can_cancel"] and "preparing" in seen["times"]
    set_status(owner, placed["id"], "ready")
    set_status(owner, placed["id"], "completed")
    [seen] = mine(owner, token)
    assert seen["status"] == "completed" and set(seen["times"]) == {"new", "preparing", "ready", "completed"}


def test_tracking_code_stays_private(owner):
    placed = order(owner, [(1, 1)]).json()["order"]
    listed = owner.get("/api/owner/orders").json()["orders"][0]
    assert "track_token" not in listed                               # not in owner lists either
    [seen] = mine(owner, placed["track_token"])
    assert "phone" not in seen                                       # the customer view leaves the phone out


def test_my_orders_needs_the_secret_code(web):
    first = order(web, [(1, 1)]).json()["order"]
    order(web, [(9, 1)], customer_name="Someone Else")
    assert mine(web, "A" * 22) == []                                 # a made-up code finds nothing
    assert [o["id"] for o in mine(web, first["track_token"])] == [first["id"]]   # only your own order
    assert web.post("/api/my-orders", json={"tokens": ["short"]}).status_code == 422
    assert web.post("/api/my-orders", json={"tokens": ["x" * 20] * 51}).status_code == 422


def test_customer_can_cancel_only_before_the_shop_confirms(owner):
    first = order(owner, [(5, 2)]).json()["order"]
    assert product(owner, 5)["stock"] == 1
    r = owner.post("/api/my-orders/cancel", json={"token": first["track_token"]})
    assert r.status_code == 200
    cancelled = r.json()["order"]
    assert cancelled["status"] == "cancelled" and cancelled["cancelled_by"] == "customer"
    assert product(owner, 5)["stock"] == 3                           # the stock came back
    again = owner.post("/api/my-orders/cancel", json={"token": first["track_token"]})
    assert again.status_code == 400 and "already cancelled" in again.json()["detail"]

    second = order(owner, [(1, 1)]).json()["order"]
    set_status(owner, second["id"], "preparing")
    late = owner.post("/api/my-orders/cancel", json={"token": second["track_token"]})
    assert late.status_code == 400 and "already confirmed" in late.json()["detail"]
    assert owner.post("/api/my-orders/cancel", json={"token": "B" * 22}).status_code == 404
    owner_view = next(o for o in owner.get("/api/owner/orders").json()["orders"] if o["id"] == first["id"])
    assert owner_view["status"] == "cancelled" and owner_view["cancelled_by"] == "customer"


def test_find_an_order_with_its_number_and_phone(web):
    placed = order(web, [(1, 1)], phone="98765 43210").json()["order"]
    wrong = web.post("/api/track", json={"order_id": placed["id"], "phone": "9000000000"})
    assert wrong.status_code == 404 and "No order matches" in wrong.json()["detail"]
    assert web.post("/api/track", json={"order_id": 999, "phone": "9876543210"}).status_code == 404
    found = web.post("/api/track", json={"order_id": placed["id"], "phone": "+91 98765 43210"})
    assert found.status_code == 200 and found.json()["order"]["token"] == placed["track_token"]


def test_finding_orders_is_slowed_down_against_guessing(web):
    codes = [web.post("/api/track", json={"order_id": 1, "phone": "9000000000"}).status_code for _ in range(11)]
    assert codes[:10] == [404] * 10 and codes[10] == 429


def test_chat_order_also_gets_a_tracking_code(web, monkeypatch):
    def pretend_ai(message, settings):
        return settings.tools[0](customer_name="Meera", items="8:1", pickup_or_delivery="pickup", delivery_address="",
                                 wanted_at="today 5 PM", phone="9123456780", notes="")

    monkeypatch.setattr(server, "brain", server.ShopBrain(client=FakeGemini(script=pretend_ai)))
    reply = web.post("/api/chat", json={"chat_id": "chat-test-01", "message": "yes"}).json()
    token = reply["orders"][0]["track_token"]
    assert mine(web, token)[0]["source"] == "chat"


def test_ai_knows_to_send_customers_to_my_orders():
    fake = FakeGemini()
    database_brain = server.ShopBrain(client=fake)
    database_brain.reply("web", "abc12345", "Where is my order?")
    assert "My orders" in fake.created[0].sent[0][1].system_instruction


# ---------- the owner's board never loses a waiting order ----------

def test_old_waiting_orders_stay_on_the_board(owner):
    oldest = order(owner, [(9, 1)]).json()["order"]
    for _ in range(3):
        newer = order(owner, [(9, 1)]).json()["order"]
        set_status(owner, newer["id"], "completed")
    ids = [o["id"] for o in database.list_orders(limit=2)]
    assert oldest["id"] in ids and len(ids) == 3                     # 2 newest + the old one still waiting


def test_double_click_on_a_status_is_harmless(owner):
    placed = order(owner, [(9, 1)]).json()["order"]
    set_status(owner, placed["id"], "preparing")
    assert set_status(owner, placed["id"], "preparing").status_code == 200
    with closing(database.connect()) as conn:
        events = conn.execute("SELECT status FROM order_events WHERE order_id = ?", (placed["id"],)).fetchall()
    assert [e["status"] for e in events] == ["new", "preparing"]


# ---------- stock history and safe stock buttons ----------

def test_stock_history_shows_sales_cancels_and_owner_changes(owner):
    placed = order(owner, [(5, 2)]).json()["order"]                  # Red Velvet Cake: 3 -> 1
    set_status(owner, placed["id"], "cancelled")                     # 1 -> 3
    owner.patch("/api/owner/products/5", json={"stock": 10})         # 3 -> 10 (typed by the owner)
    owner.post("/api/owner/products/5/stock", json={"change": 1})    # +1 right after: joins the +7
    moves = owner.get("/api/owner/products/5/stock-history").json()["moves"]
    summary = [(m["reason"], m["delta"], m["stock_after"]) for m in moves]
    assert summary == [("owner", 8, 11), ("cancel", 2, 3), ("order", -2, 1), ("added", 3, 3)]
    assert moves[2]["order_id"] == placed["id"]
    assert owner.get("/api/owner/products/999/stock-history").status_code == 404


def test_plus_and_minus_never_undo_a_sale(owner):
    assert product(owner, 1)["stock"] == 6                           # the owner's page shows 6...
    order(owner, [(1, 2)])                                           # ...then a customer buys 2
    r = owner.post("/api/owner/products/1/stock", json={"change": 1})
    assert r.json()["product"]["stock"] == 5                         # 6 - 2 + 1, not 7
    too_many = owner.post("/api/owner/products/1/stock", json={"change": -6})
    assert too_many.status_code == 400 and "only 5" in too_many.json()["detail"]
    assert owner.post("/api/owner/products/1/stock", json={"change": 0}).status_code == 400
    assert owner.post("/api/owner/products/999/stock", json={"change": 1}).status_code == 404


def test_plus_then_minus_leaves_no_history_line(owner):
    owner.post("/api/owner/products/9/stock", json={"change": 1})
    owner.post("/api/owner/products/9/stock", json={"change": -1})
    reasons = [m["reason"] for m in owner.get("/api/owner/products/9/stock-history").json()["moves"]]
    assert reasons == ["added"]


def test_stock_page_puts_items_that_need_attention_first(owner):
    owner.patch("/api/owner/products/9", json={"stock": 0})
    order(owner, [(6, 14)])                                          # Chocolate Pastry: 20 -> 6, selling fast
    data = owner.get("/api/owner/stock").json()
    first = data["items"][0]
    assert (first["id"], first["level"]) == (9, "sold_out")
    pastry = next(i for i in data["items"] if i["id"] == 6)
    assert pastry["sold_7d"] == 14 and pastry["days_left"] == 3.0    # 6 left at 2 a day
    assert data["moves"][0]["reason"] == "order"


def test_new_item_starts_its_stock_history(owner):
    new_id = owner.post("/api/owner/products", json={"name": "Plum Cake", "category": "Cakes", "price": 450,
                                                     "stock": 8}).json()["product"]["id"]
    [move] = owner.get(f"/api/owner/products/{new_id}/stock-history").json()["moves"]
    assert (move["reason"], move["delta"], move["stock_after"]) == ("added", 8, 8)


# ---------- earnings ----------

def test_earnings_count_only_real_money(owner):
    done = order(owner, [(1, 1)]).json()["order"]                    # 850, completed
    for status in ("preparing", "ready", "completed"):
        set_status(owner, done["id"], status)
    order(owner, [(9, 2)], fulfilment="delivery", address="5 Temple Street, Ward 3")   # 50 + 40 delivery, waiting
    gone = order(owner, [(6, 1)], phone="9000000001").json()["order"]
    set_status(owner, gone["id"], "cancelled")
    r = owner.get("/api/owner/report?period=7d").json()["report"]
    s = r["summary"]
    assert (s["earned"], s["waiting"], s["value"], s["orders"]) == (850, 90, 940, 2)
    assert (s["cancelled_orders"], s["cancelled_value"], s["items_sold"], s["delivery_fees"]) == (1, 70, 3, 40)
    assert (s["pickup"], s["delivery"], s["average"]) == (1, 1, 470)
    assert len(r["bars"]) == 7 and r["bars"][-1]["earned"] == 850 and r["bars"][-1]["waiting"] == 90
    assert r["top_items"][0]["name"] == "Black Forest Cake" and r["top_items"][0]["money"] == 850
    assert s["customers"] == 1 and s["repeat_customers"] == 1 and r["customers"][0]["orders"] == 2
    assert owner.get("/api/owner/report?period=forever").status_code == 400
    assert TestClient(server.app).get("/api/owner/report").status_code == 401


def test_all_time_earnings_are_grouped_by_month(owner, monkeypatch):
    real_now = database.now()
    monkeypatch.setattr(database, "now", lambda: real_now - timedelta(days=70))
    order(owner, [(1, 1)])                                           # an order from about two months ago
    monkeypatch.setattr(database, "now", lambda: real_now)
    order(owner, [(9, 1)])
    all_time = owner.get("/api/owner/report?period=all").json()["report"]
    assert all_time["grouping"] == "month" and len(all_time["bars"]) >= 3
    assert all_time["summary"]["orders"] == 2
    assert owner.get("/api/owner/report?period=7d").json()["report"]["summary"]["orders"] == 1


# ---------- order search and spreadsheet ----------

def test_owner_finds_orders_by_name_phone_or_number(owner):
    asha = order(owner, [(1, 1)]).json()["order"]
    ravi = order(owner, [(9, 1)], customer_name="Ravi Kumar", phone="9000012345").json()["order"]
    find = lambda q: [o["id"] for o in owner.get("/api/owner/orders/search", params={"q": q}).json()["orders"]]
    assert find("ravi") == [ravi["id"]]
    assert find("12345") == [ravi["id"]]
    assert find(f"#{asha['id']}") == [asha["id"]]
    assert find("%") == [] and find("") == []                        # wildcards are just text


def test_spreadsheet_download_is_safe_to_open(owner):
    order(owner, [(1, 2)], customer_name="=HYPERLINK(\"http://bad.example\")")
    r = owner.get("/api/owner/orders.csv?period=7d")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    text = r.content.decode("utf-8")
    assert text.startswith("﻿Order,Date,Time,Status")
    assert "'=HYPERLINK" in text and "2 x Black Forest Cake" in text
    assert TestClient(server.app).get("/api/owner/orders.csv").status_code == 401


# ---------- any kind of shop ----------

def test_shop_page_words_and_icon_come_from_the_owner(owner):
    r = owner.put("/api/owner/settings", json={"shop_emoji": "🥦", "notes_hint": "Any brand you prefer",
                                               "quick_questions": ["Do you deliver?", "  ", "Is it fresh today?"]})
    assert r.status_code == 200
    shop = owner.get("/api/shop").json()["shop"]
    assert shop["shop_emoji"] == "🥦" and shop["notes_hint"] == "Any brand you prefer"
    assert shop["quick_questions"] == ["Do you deliver?", "Is it fresh today?"]
    owner.put("/api/owner/settings", json={"shop_emoji": "   "})
    assert owner.get("/api/shop").json()["shop"]["shop_emoji"] == database.DEFAULT_EMOJI
    assert owner.put("/api/owner/settings", json={"quick_questions": ["a", "b", "c", "d"]}).status_code == 422


# ---------- a shop.db from the older version keeps working ----------

def test_old_shop_database_is_upgraded_without_losing_orders(tmp_path, monkeypatch):
    old_file = tmp_path / "old-shop.db"
    conn = sqlite3.connect(old_file)
    conn.executescript("""
        CREATE TABLE products (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, category TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '', emoji TEXT NOT NULL DEFAULT '🧁', image TEXT NOT NULL DEFAULT '',
            price INTEGER NOT NULL, offer_price INTEGER, offer_ends_at TEXT, stock INTEGER NOT NULL DEFAULT 0,
            visible INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE orders (id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL, source TEXT NOT NULL,
            customer_name TEXT NOT NULL, phone TEXT NOT NULL, fulfilment TEXT NOT NULL,
            address TEXT NOT NULL DEFAULT '', wanted_at TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '',
            items TEXT NOT NULL, subtotal INTEGER NOT NULL, delivery_fee INTEGER NOT NULL DEFAULT 0,
            total INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'new');
        CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        INSERT INTO products (name, category, price, stock) VALUES ('Old Cake', 'Cakes', 500, 4);
    """)
    lines = json.dumps([{"product_id": 1, "name": "Old Cake", "emoji": "🎂", "quantity": 1, "unit_price": 500,
                         "line_total": 500}])
    conn.execute("INSERT INTO orders (created_at, source, customer_name, phone, fulfilment, items, subtotal, total) "
                 "VALUES (?, 'cart', 'Asha', '9876543210', 'pickup', ?, 500, 500)",
                 (database.now().isoformat(timespec="seconds"), lines))
    conn.commit()
    conn.close()

    monkeypatch.setattr(config, "DATABASE_FILE", old_file)
    assert database.get_product(1)["diet"] == ""                       # old items get the new veg/non-veg field
    [old] = database.list_orders()
    assert old["customer_name"] == "Asha" and old["cancelled_by"] == ""
    found = database.track_order(old["id"], "9876543210")              # old orders get a tracking code when found
    assert found["token"] and database.customer_orders([found["token"]])[0]["id"] == old["id"]
    database.update_order_status(old["id"], "cancelled")
    assert database.get_product(1)["stock"] == 5
    assert database.sales_report("all")["summary"]["cancelled_orders"] == 1


# ---------- nightly backup ----------

def test_backup_has_orders_and_photos_and_keeps_only_the_newest(owner, tmp_path):
    import zipfile

    import backup

    placed = order(owner, [(1, 1)]).json()["order"]
    (config.UPLOADS_DIR / "cake.jpg").write_bytes(b"\xff\xd8\xff photo")
    made = [backup.make_backup(tmp_path / "backups", keep=2) for _ in range(3)]
    left = sorted((tmp_path / "backups").glob("shop-backup-*.zip"))
    assert left == made[1:]                                   # the oldest one was removed
    with zipfile.ZipFile(made[-1]) as archive:
        assert set(archive.namelist()) == {"shop.db", "uploads/cake.jpg"}
        archive.extract("shop.db", tmp_path / "restore")
    with closing(sqlite3.connect(tmp_path / "restore" / "shop.db")) as copy:
        assert copy.execute("SELECT customer_name FROM orders WHERE id = ?", (placed["id"],)).fetchone() == ("Asha",)
    assert oct(made[-1].stat().st_mode & 0o777) == "0o600"   # only the shop's user can read it


# ---------- veg / non-veg (dhabas and restaurants) ----------

def test_veg_and_non_veg_marks_reach_the_shop_and_the_ai(owner):
    owner.patch("/api/owner/products/9", json={"diet": "veg"})
    new_id = owner.post("/api/owner/products", json={"name": "Chicken Curry", "category": "Curries", "price": 220,
                                                     "stock": 20, "diet": "nonveg"}).json()["product"]["id"]
    assert product(owner, 9)["diet"] == "veg" and product(owner, new_id)["diet"] == "nonveg"
    assert product(owner, 1)["diet"] == ""                           # not set until the owner chooses
    menu = database.menu_text()
    assert "#9 Veg Puff (VEG) [" in menu and f"#{new_id} Chicken Curry (NON-VEG) [" in menu
    assert owner.patch("/api/owner/products/9", json={"diet": "vegan"}).status_code == 422
    owner.patch("/api/owner/products/9", json={"diet": ""})
    assert product(owner, 9)["diet"] == ""
