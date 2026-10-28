"""The shop's memory: products, orders and shop details, saved in one SQLite file (shop.db).
SQLite comes with Python, so there is nothing extra to install.

Important rule: prices, stock and totals are always worked out HERE in Python,
never by the AI. The AI only passes item IDs and quantities."""
import json
import re
import sqlite3
import threading
from contextlib import closing
from datetime import datetime, time, timedelta

import config

STATUSES = ["new", "preparing", "ready", "completed", "cancelled"]
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
SOURCES = ["cart", "chat", "whatsapp", "instagram", "terminal"]
MAX_QUANTITY = 50          # the most of one item in a single order
LOW_STOCK = 3              # at or below this, the shop shows "Only 3 left"

_lock = threading.RLock()  # one change at a time, so two customers can't buy the same last cake
_ready = set()             # database files whose tables already exist

DEFAULT_SETTINGS = {
    "shop_name": "Sweet Crumbs Bakery",
    "tagline": "Cakes, pastries and puffs, baked fresh every morning.",
    "phone": "+91 90000 00000",
    "address": "12 Market Road, near the City Bus Stand",
    "open_time": "09:00",
    "close_time": "21:00",
    "closed_days": "Tuesday",
    "delivery_fee": "40",
    "free_delivery_above": "500",
    "delivery_area": "Home delivery within 3 km, from 11:00 AM to 8:00 PM.",
    "assistant_notes": ("Every cake can be made eggless at no extra cost. A name or message on a cake is free "
                        "(up to 20 letters). Photo cakes and theme cakes need 2 days' notice and 50% advance by UPI. "
                        "Customers pay at pickup or delivery by UPI, cash or card."),
}

# (name, category, description, emoji, price in rupees, stock)
SAMPLE_PRODUCTS = [
    ("Black Forest Cake", "Cakes", "1 kg. Chocolate sponge, fresh cream and cherries.", "🎂", 850, 6),
    ("Chocolate Truffle Cake", "Cakes", "1 kg. Dark chocolate ganache, layer after layer.", "🍫", 950, 5),
    ("Pineapple Cake", "Cakes", "1 kg. Light sponge with pineapple cream.", "🍍", 750, 6),
    ("Butterscotch Cake", "Cakes", "1 kg. Caramel crunch in every slice.", "🍮", 800, 4),
    ("Red Velvet Cake", "Cakes", "1 kg. Cream cheese frosting.", "🍰", 1050, 3),
    ("Chocolate Pastry", "Pastries", "One generous slice.", "🧁", 70, 20),
    ("Pineapple Pastry", "Pastries", "One slice, extra cream.", "🧁", 60, 18),
    ("Red Velvet Pastry", "Pastries", "One slice with cream cheese frosting.", "🍰", 90, 12),
    ("Veg Puff", "Puffs and snacks", "Spiced potato and peas in flaky pastry.", "🥐", 25, 30),
    ("Paneer Puff", "Puffs and snacks", "Masala paneer in flaky pastry.", "🥐", 35, 25),
    ("Garlic Bread", "Puffs and snacks", "Buttery, toasted, four pieces.", "🥖", 60, 10),
    ("Butter Cookies", "Cookies", "250 g box, baked this morning.", "🍪", 180, 15),
]


class OrderError(ValueError):
    """A problem with an order that the customer can fix, like asking for more than the stock left."""


def now():
    return datetime.now(config.SHOP_TIMEZONE)


def connect():
    """Open the database file (creating the tables and sample items the first time)."""
    path = str(config.DATABASE_FILE)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    if path not in _ready:
        with _lock:
            _create_tables(conn)
            _ready.add(path)
    return conn


def _create_tables(conn):
    conn.executescript("""
        PRAGMA journal_mode = WAL;
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            emoji TEXT NOT NULL DEFAULT '🧁',
            image TEXT NOT NULL DEFAULT '',
            price INTEGER NOT NULL,
            offer_price INTEGER,
            offer_ends_at TEXT,
            stock INTEGER NOT NULL DEFAULT 0,
            visible INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            source TEXT NOT NULL,
            customer_name TEXT NOT NULL,
            phone TEXT NOT NULL,
            fulfilment TEXT NOT NULL,
            address TEXT NOT NULL DEFAULT '',
            wanted_at TEXT NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT '',
            items TEXT NOT NULL,
            subtotal INTEGER NOT NULL,
            delivery_fee INTEGER NOT NULL DEFAULT 0,
            total INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'new'
        );
        CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    """)
    with conn:
        if conn.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 0:
            conn.executemany(
                "INSERT INTO products (name, category, description, emoji, price, stock) VALUES (?, ?, ?, ?, ?, ?)",
                SAMPLE_PRODUCTS)
            # One sample offer, so the shop shows a live countdown from the first run
            ends = _preset_end("closing", now(), {**DEFAULT_SETTINGS, "closed_days": []})
            conn.execute("UPDATE products SET offer_price = 799, offer_ends_at = ? WHERE name = ?",
                         (ends.isoformat(timespec="seconds"), "Chocolate Truffle Cake"))


# ---------------- small helpers ----------------

def rupees(amount):
    """1050 -> "1,050" and 105000 -> "1,05,000" (Indian digit grouping)."""
    digits = str(int(amount))
    if len(digits) <= 3:
        return digits
    head, last3 = digits[:-3], digits[-3:]
    pairs = [head[max(i - 2, 0):i] for i in range(len(head), 0, -2)][::-1]   # split the rest into pairs
    return ",".join(pairs + [last3])


def clock(t):
    """time(21, 0) -> "9:00 PM"."""
    return f"{t.hour % 12 or 12}:{t.minute:02d} {'AM' if t.hour < 12 else 'PM'}"


def when_text(moment, at=None):
    """A moment as people say it: "9:00 PM today", "tomorrow at 9:00 PM" or "Sat 24 Oct at 9:00 PM"."""
    at = at or now()
    days_away = (moment.date() - at.date()).days
    if days_away == 0:
        return f"{clock(moment.time())} today"
    if days_away == 1:
        return f"tomorrow at {clock(moment.time())}"
    return f"{moment:%a %d %b} at {clock(moment.time())}"


def _clean(text, max_len):
    """Trim spaces and line breaks, and cut very long text."""
    return " ".join(str(text or "").split())[:max_len]


def clean_phone(phone):
    """Keep only digits; a valid number has 10 to 13 digits (with or without the 91 country code)."""
    digits = re.sub(r"\D", "", str(phone or ""))
    return digits if 10 <= len(digits) <= 13 else ""


# ---------------- shop details ----------------

def get_settings():
    with closing(connect()) as conn:
        saved = {row["key"]: row["value"] for row in conn.execute("SELECT key, value FROM settings")}
    s = {**DEFAULT_SETTINGS, **saved}
    s["closed_days"] = [day for day in DAYS if day in s["closed_days"].split(",")]
    s["delivery_fee"] = int(s["delivery_fee"])
    s["free_delivery_above"] = int(s["free_delivery_above"])
    return s


def update_settings(changes):
    """Check and save shop details. Raises ValueError with a clear message if something is wrong."""
    current = get_settings()
    limits = {"shop_name": 60, "tagline": 120, "phone": 20, "address": 160,
              "delivery_area": 200, "assistant_notes": 1500}
    new = {}
    for key, max_len in limits.items():
        if key in changes:
            value = str(changes[key]).strip()[:max_len]
            if key in ("shop_name", "phone", "address") and not value:
                raise ValueError("Shop name, phone and address can't be empty.")
            new[key] = value
    for key in ("open_time", "close_time"):
        if key in changes:
            try:
                new[key] = time.fromisoformat(str(changes[key])).strftime("%H:%M")
            except ValueError:
                raise ValueError("Opening and closing times must look like 09:00 or 21:30.") from None
    opening = time.fromisoformat(new.get("open_time", current["open_time"]))
    closing_time = time.fromisoformat(new.get("close_time", current["close_time"]))
    if closing_time <= opening:
        raise ValueError("The closing time must be later than the opening time.")
    if "closed_days" in changes:
        days = [day for day in DAYS if day in changes["closed_days"]]
        if len(days) == 7:
            raise ValueError("The shop can't be closed on all 7 days.")
        new["closed_days"] = ",".join(days)
    for key in ("delivery_fee", "free_delivery_above"):
        if key in changes:
            try:
                amount = int(changes[key])
            except (TypeError, ValueError):
                raise ValueError("Delivery amounts must be whole rupees, like 40.") from None
            if not 0 <= amount <= 100000:
                raise ValueError("Delivery amounts must be between ₹0 and ₹1,00,000.")
            new[key] = str(amount)
    with _lock, closing(connect()) as conn, conn:
        conn.executemany("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", list(new.items()))
    return get_settings()


def shop_status(settings, at=None):
    """Is the shop open right now? Worked out in Python, so it is always right."""
    at = at or now()
    opening = time.fromisoformat(settings["open_time"])
    closing_time = time.fromisoformat(settings["close_time"])
    today = DAYS[at.weekday()]
    if today not in settings["closed_days"] and opening <= at.time() < closing_time:
        return {"open": True, "text": f"Open now, closes at {clock(closing_time)}"}
    for days_ahead in range(8):                              # find the next opening time
        day = at + timedelta(days=days_ahead)
        start = datetime.combine(day.date(), opening, tzinfo=at.tzinfo)
        if DAYS[day.weekday()] not in settings["closed_days"] and start > at:
            when = "today" if days_ahead == 0 else "tomorrow" if days_ahead == 1 else f"on {DAYS[day.weekday()]}"
            return {"open": False, "text": f"Closed now, opens {when} at {clock(opening)}"}
    return {"open": False, "text": "Closed now"}


def shop_details_text(settings):
    """The shop details written out for the AI assistant."""
    closed = ", ".join(settings["closed_days"]) or "no day"
    fee, free_above = settings["delivery_fee"], settings["free_delivery_above"]
    delivery = "Delivery is free." if fee == 0 else (
        f"Delivery fee is ₹{rupees(fee)}, free for orders of ₹{rupees(free_above)} or more.")
    return (f"Shop: {settings['shop_name']}. {settings['tagline']}\n"
            f"Address: {settings['address']}\n"
            f"Phone: {settings['phone']}\n"
            f"Opening hours: {clock(time.fromisoformat(settings['open_time']))} to "
            f"{clock(time.fromisoformat(settings['close_time']))}, closed on {closed}.\n"
            f"Delivery: {delivery} {settings['delivery_area']}\n"
            f"More: {settings['assistant_notes']}")


# ---------------- products ----------------

def _product_view(row, at):
    """A product as the website sees it, with today's real price."""
    offer_on = (row["offer_price"] is not None and row["offer_ends_at"] is not None
                and datetime.fromisoformat(row["offer_ends_at"]) > at)
    return {
        "id": row["id"], "name": row["name"], "category": row["category"],
        "description": row["description"], "emoji": row["emoji"], "image": row["image"],
        "price": row["price"],
        "offer_price": row["offer_price"] if offer_on else None,
        "offer_ends_at": row["offer_ends_at"] if offer_on else None,
        "current_price": row["offer_price"] if offer_on else row["price"],
        "stock": row["stock"], "visible": bool(row["visible"]),
    }


def list_products(include_hidden=False, at=None):
    at = at or now()
    query = "SELECT * FROM products" + ("" if include_hidden else " WHERE visible = 1") + " ORDER BY category, id"
    with closing(connect()) as conn:
        return [_product_view(row, at) for row in conn.execute(query)]


def get_product(product_id):
    with closing(connect()) as conn:
        row = conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
    if row is None:
        raise KeyError(product_id)
    return _product_view(row, now())


def _check_product_fields(fields):
    """Check product values from the owner page. Raises ValueError with a clear message."""
    checked = {}
    for key, max_len in (("name", 60), ("category", 30), ("description", 160), ("emoji", 8)):
        if key in fields:
            value = _clean(fields[key], max_len)
            if key in ("name", "category") and not value:
                raise ValueError("Every item needs a name and a category.")
            if key == "emoji" and not value:
                value = "🧁"                                  # default picture
            checked[key] = value
    if "price" in fields:
        if not 1 <= int(fields["price"]) <= 1_000_000:
            raise ValueError("The price must be between ₹1 and ₹10,00,000.")
        checked["price"] = int(fields["price"])
    if "stock" in fields:
        if not 0 <= int(fields["stock"]) <= 100_000:
            raise ValueError("Stock must be between 0 and 1,00,000.")
        checked["stock"] = int(fields["stock"])
    if "visible" in fields:
        checked["visible"] = 1 if fields["visible"] else 0
    return checked


def create_product(fields):
    checked = _check_product_fields({"emoji": "🧁", "description": "", "stock": 0, "visible": True, **fields})
    if "name" not in checked or "category" not in checked or "price" not in checked:
        raise ValueError("Every item needs a name, a category and a price.")
    columns = ", ".join(checked)
    with _lock, closing(connect()) as conn, conn:
        cursor = conn.execute(f"INSERT INTO products ({columns}) VALUES ({', '.join('?' * len(checked))})",
                              list(checked.values()))
    return get_product(cursor.lastrowid)


def update_product(product_id, fields):
    checked = _check_product_fields(fields)
    with _lock, closing(connect()) as conn, conn:
        row = conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
        if row is None:
            raise KeyError(product_id)
        offer_price = _product_view(row, now())["offer_price"]        # None if there's no live offer
        if "price" in checked and offer_price is not None and offer_price >= checked["price"]:
            raise ValueError("End the offer first, or keep the price above the offer price.")
        if checked:
            assignments = ", ".join(f"{key} = ?" for key in checked)
            conn.execute(f"UPDATE products SET {assignments} WHERE id = ?", [*checked.values(), product_id])
    return get_product(product_id)


def delete_product(product_id):
    """Delete an item. Returns its photo path (if any) so the photo file can be removed too."""
    with _lock, closing(connect()) as conn, conn:
        row = conn.execute("SELECT image FROM products WHERE id = ?", (product_id,)).fetchone()
        if row is None:
            raise KeyError(product_id)
        conn.execute("DELETE FROM products WHERE id = ?", (product_id,))
    return row["image"]


def set_product_image(product_id, image_path):
    """Save a new photo path. Returns the old photo path so the old file can be removed."""
    with _lock, closing(connect()) as conn, conn:
        row = conn.execute("SELECT image FROM products WHERE id = ?", (product_id,)).fetchone()
        if row is None:
            raise KeyError(product_id)
        conn.execute("UPDATE products SET image = ? WHERE id = ?", (image_path, product_id))
    return row["image"]


def _preset_end(preset, at, settings):
    """When an offer ends: "1h", "3h", "closing" (today's closing time) or "midnight"."""
    if preset in ("1h", "3h"):
        return at + timedelta(hours=int(preset[0]))
    if preset == "midnight":
        return datetime.combine(at.date() + timedelta(days=1), time(0, 0), tzinfo=at.tzinfo)
    if preset == "closing":
        closing_time = datetime.combine(at.date(), time.fromisoformat(settings["close_time"]), tzinfo=at.tzinfo)
        return closing_time if closing_time > at else closing_time + timedelta(days=1)
    raise ValueError("Choose when the offer ends.")


def set_offer(product_id, offer_price, preset="closing", ends_at=""):
    """Start a limited-time offer. preset is 1h, 3h, closing, midnight, or custom (then ends_at is used)."""
    at = now()
    if preset == "custom":
        try:
            ends = datetime.fromisoformat(ends_at)
        except ValueError:
            raise ValueError("Pick the date and time when the offer ends.") from None
        if ends.tzinfo is None:
            ends = ends.replace(tzinfo=config.SHOP_TIMEZONE)      # times typed on the owner page are India time
    else:
        ends = _preset_end(preset, at, get_settings())
    if ends <= at:
        raise ValueError("The offer must end in the future.")
    if ends > at + timedelta(days=60):
        raise ValueError("Offers can run for up to 60 days.")
    with _lock, closing(connect()) as conn, conn:
        row = conn.execute("SELECT price FROM products WHERE id = ?", (product_id,)).fetchone()
        if row is None:
            raise KeyError(product_id)
        if not 1 <= int(offer_price) < row["price"]:
            raise ValueError(f"The offer price must be less than the normal price (₹{rupees(row['price'])}).")
        conn.execute("UPDATE products SET offer_price = ?, offer_ends_at = ? WHERE id = ?",
                     (int(offer_price), ends.isoformat(timespec="seconds"), product_id))
    return get_product(product_id)


def end_offer(product_id):
    with _lock, closing(connect()) as conn, conn:
        if conn.execute("UPDATE products SET offer_price = NULL, offer_ends_at = NULL WHERE id = ?",
                        (product_id,)).rowcount == 0:
            raise KeyError(product_id)
    return get_product(product_id)


def menu_text(at=None):
    """The live menu written out for the AI assistant. '#' numbers are the item IDs."""
    at = at or now()
    lines = []
    for p in list_products(at=at):
        if p["offer_price"] is not None:
            ends = datetime.fromisoformat(p["offer_ends_at"])
            price = (f"OFFER ₹{rupees(p['offer_price'])} (normal price ₹{rupees(p['price'])}), "
                     f"offer ends {when_text(ends, at)}")
        else:
            price = f"₹{rupees(p['price'])}"
        stock = "OUT OF STOCK" if p["stock"] == 0 else f"{p['stock']} left"
        lines.append(f"#{p['id']} {p['name']} [{p['category']}]: {price}; {stock}. {p['description']}")
    return "\n".join(lines) or "(The menu is empty right now.)"


# ---------------- orders ----------------

def _order_view(row):
    order = dict(row)
    order["items"] = json.loads(row["items"])
    return order


def place_order(source, customer_name, phone, fulfilment, address, wanted_at, notes, items):
    """Check everything, work out the prices, take the stock and save the order.
    items is a list of (product_id, quantity). Raises OrderError with a message the customer can act on."""
    customer_name = _clean(customer_name, 60)
    phone = clean_phone(phone)
    fulfilment = _clean(fulfilment, 10).lower()
    address, wanted_at, notes = _clean(address, 200), _clean(wanted_at, 60), _clean(notes, 300)
    if not customer_name:
        raise OrderError("Please give a name for the order.")
    if not phone:
        raise OrderError("Please give a phone number with 10 digits.")
    if fulfilment not in ("pickup", "delivery"):
        raise OrderError("Please choose pickup or delivery.")
    if fulfilment == "delivery" and len(address) < 8:
        raise OrderError("Please give the full delivery address.")
    if not wanted_at:
        raise OrderError("Please say when you want the order.")
    wanted = {}
    for product_id, quantity in items:                       # join repeated items: 2 + 1 of the same cake = 3
        wanted[int(product_id)] = wanted.get(int(product_id), 0) + int(quantity)
    if not wanted:
        raise OrderError("The order has no items yet.")
    if any(not 1 <= quantity <= MAX_QUANTITY for quantity in wanted.values()):
        raise OrderError(f"Each item's quantity must be between 1 and {MAX_QUANTITY}.")

    at = now()
    settings = get_settings()
    with _lock, closing(connect()) as conn, conn:            # if anything fails, nothing is saved
        lines = []
        for product_id, quantity in wanted.items():
            row = conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
            if row is None or not row["visible"]:
                raise OrderError(f"Item #{product_id} is not on the menu.")
            if row["stock"] < quantity:
                raise OrderError(f"Sorry, {row['name']} is sold out." if row["stock"] == 0
                                 else f"Only {row['stock']} {row['name']} left. Please order {row['stock']} or fewer.")
            price = _product_view(row, at)["current_price"]
            lines.append({"product_id": product_id, "name": row["name"], "emoji": row["emoji"],
                          "quantity": quantity, "unit_price": price, "line_total": price * quantity})
        subtotal = sum(line["line_total"] for line in lines)
        free = fulfilment == "pickup" or subtotal >= settings["free_delivery_above"]
        delivery_fee = 0 if free else settings["delivery_fee"]
        for line in lines:
            conn.execute("UPDATE products SET stock = stock - ? WHERE id = ?", (line["quantity"], line["product_id"]))
        cursor = conn.execute(
            """INSERT INTO orders (created_at, source, customer_name, phone, fulfilment, address, wanted_at,
                                   notes, items, subtotal, delivery_fee, total)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (at.isoformat(timespec="seconds"), source if source in SOURCES else "chat", customer_name, phone,
             fulfilment, address if fulfilment == "delivery" else "", wanted_at, notes,
             json.dumps(lines, ensure_ascii=False), subtotal, delivery_fee, subtotal + delivery_fee))
    return get_order(cursor.lastrowid)


def get_order(order_id):
    with closing(connect()) as conn:
        row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    if row is None:
        raise KeyError(order_id)
    return _order_view(row)


def list_orders(limit=300):
    with closing(connect()) as conn:
        return [_order_view(row) for row in conn.execute("SELECT * FROM orders ORDER BY id DESC LIMIT ?", (limit,))]


def update_order_status(order_id, status):
    """Move an order along: new -> preparing -> ready -> completed. Cancelling puts the stock back."""
    if status not in STATUSES:
        raise ValueError("Unknown order status.")
    with _lock, closing(connect()) as conn, conn:
        row = conn.execute("SELECT status, items FROM orders WHERE id = ?", (order_id,)).fetchone()
        if row is None:
            raise KeyError(order_id)
        if row["status"] == "cancelled":
            raise OrderError("This order was cancelled, so it can't be changed.")
        if status == "cancelled":
            for line in json.loads(row["items"]):
                conn.execute("UPDATE products SET stock = stock + ? WHERE id = ?", (line["quantity"], line["product_id"]))
        conn.execute("UPDATE orders SET status = ? WHERE id = ?", (status, order_id))
    return get_order(order_id)


def order_stats(at=None):
    """Numbers for the owner page: today's orders and money, orders waiting, items running low."""
    at = at or now()
    today = at.date().isoformat()
    with closing(connect()) as conn:
        today_rows = conn.execute("SELECT total FROM orders WHERE created_at >= ? AND status != 'cancelled'",
                                  (today,)).fetchall()
        waiting = conn.execute("SELECT COUNT(*) FROM orders WHERE status IN ('new', 'preparing', 'ready')").fetchone()[0]
        low = conn.execute("SELECT COUNT(*) FROM products WHERE visible = 1 AND stock <= ?", (LOW_STOCK,)).fetchone()[0]
    return {"today_orders": len(today_rows), "today_revenue": sum(row["total"] for row in today_rows),
            "waiting": waiting, "low_stock": low}
