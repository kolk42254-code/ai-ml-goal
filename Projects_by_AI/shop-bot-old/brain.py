"""The bot's brain: it reads the shop info, asks Gemini for replies,
remembers each customer's chat, and saves confirmed orders to orders.csv."""
import csv
import threading
from datetime import datetime, timedelta

from google import genai
from google.genai import types

import config

FORGET_AFTER = timedelta(hours=24)   # start a fresh chat after a day of silence
MAX_TURNS = 30                       # ...or after 30 customer messages (keeps it fast and cheap)
FALLBACK = "Sorry, I couldn't answer just now. Please try again in a minute."
ORDER_COLUMNS = ["saved_at", "platform", "customer_name", "items",
                 "pickup_or_delivery", "date_and_time", "phone"]
PLATFORM_NAMES = {"whatsapp": "WhatsApp", "instagram": "Instagram"}

RULES = """You are the AI assistant of the shop described below. Customers message you on WhatsApp or Instagram.
Follow these rules:
1. Only help with this shop: products, prices, timings, delivery, payment and orders.
   For anything else, politely say you can only help with the shop.
2. Use ONLY the shop info below. If something isn't there, say you're not sure and share the shop's phone number.
   Never make up prices, offers, stock or timings.
3. Keep replies short (under 500 characters), warm and simple. Reply in the same language the customer uses.
4. In your first reply of a chat, say you are the shop's AI assistant.
5. To take an order, collect: name, items (size and quantity), pickup or delivery (with address),
   date and time, and phone number (unless it is already known). Then repeat the full order with the
   total price and ask the customer to confirm. Call save_order only after they clearly say yes.
6. Every customer message starts with the shop's current date and time in [square brackets].
   Use it for questions like "are you open now?", but never repeat the brackets.
7. If a customer is upset, asks for a refund or wants a human, share the shop's phone number
   and say the owner will help them.

SHOP INFO:
"""

_orders_lock = threading.Lock()


def save_order_to_csv(platform, customer_name, items, pickup_or_delivery, date_and_time, phone):
    """Add one order as a new row in orders.csv (the file is created the first time)."""
    row = {
        "saved_at": datetime.now(config.SHOP_TIMEZONE).strftime("%Y-%m-%d %H:%M"),
        "platform": platform,
        "customer_name": customer_name,
        "items": items,
        "pickup_or_delivery": pickup_or_delivery,
        "date_and_time": date_and_time,
        "phone": phone,
    }
    with _orders_lock:                       # two orders at the same moment won't mix
        is_new_file = not config.ORDERS_FILE.exists()
        # "utf-8-sig" lets Excel show the ₹ sign correctly
        with open(config.ORDERS_FILE, "a", newline="", encoding="utf-8-sig") as file:
            writer = csv.DictWriter(file, fieldnames=ORDER_COLUMNS)
            if is_new_file:
                writer.writeheader()
            writer.writerow(row)


class ShopBrain:
    """One brain serves every customer. Each customer gets their own chat memory."""

    def __init__(self, client=None):
        if client is None:
            if not config.GEMINI_API_KEY:
                raise RuntimeError("GEMINI_API_KEY is missing. Put it in your .env file.")
            client = genai.Client(api_key=config.GEMINI_API_KEY)
        self.client = client
        self.shop_info = config.SHOP_INFO_FILE.read_text(encoding="utf-8")
        self.sessions = {}                   # "whatsapp:9198..." -> {"chat", "last_seen", "turns"}
        self.locks = {}                      # one lock per customer
        self.locks_guard = threading.Lock()

    def reply(self, platform, user_id, text, name=""):
        """Get the bot's answer to one customer message."""
        key = f"{platform}:{user_id}"
        with self._lock_for(key):            # handle one message at a time per customer
            session = self._session_for(key, platform, user_id, name)
            now = datetime.now(config.SHOP_TIMEZONE)
            try:
                response = session["chat"].send_message(f"[{now:%A %d %B %Y, %I:%M %p}] {text}")
                answer = (response.text or "").strip()
            except Exception as error:       # no internet, wrong key, free limit reached...
                print(f"[brain] Gemini error for {key}: {error}")
                answer = ""
            session["last_seen"] = now
            session["turns"] += 1
        return answer or FALLBACK

    def _session_for(self, key, platform, user_id, name):
        """Reuse the customer's chat, or start a new one if it is too old or too long."""
        session = self.sessions.get(key)
        now = datetime.now(config.SHOP_TIMEZONE)
        if (session is None
                or now - session["last_seen"] > FORGET_AFTER
                or session["turns"] >= MAX_TURNS):
            session = {"chat": self._new_chat(platform, user_id, name), "last_seen": now, "turns": 0}
            self.sessions[key] = session
        return session

    def _new_chat(self, platform, user_id, name):
        """Start a Gemini chat that knows the rules, the shop info and the save_order tool."""
        if platform == "whatsapp":
            about = "They are on WhatsApp, so their phone number is already known: don't ask for it."
        else:
            where = PLATFORM_NAMES.get(platform, "a test chat")
            about = f"They are on {where}, so ask for their phone number when taking an order."
        if name:
            about += f" Their profile name is {name}."
        settings = types.GenerateContentConfig(
            system_instruction=RULES + self.shop_info + "\n\nABOUT THIS CUSTOMER: " + about,
            tools=[self.make_save_order(platform, user_id)],   # Gemini may call this function
        )
        return self.client.chats.create(model=config.GEMINI_MODEL, config=settings)

    def make_save_order(self, platform, user_id):
        """Build the save_order tool for one customer (it remembers their platform and ID)."""

        def save_order(customer_name: str, items: str, pickup_or_delivery: str,
                       date_and_time: str, phone: str) -> str:
            """Save a confirmed order so the shop owner can prepare it.

            Args:
                customer_name: The customer's name.
                items: Everything ordered, with size and quantity.
                pickup_or_delivery: "Pickup", or "Delivery to " followed by the full address.
                date_and_time: When the customer wants the order.
                phone: The customer's phone number. Use an empty string if it is already known.
            """
            if platform == "whatsapp" and not phone:
                phone = user_id              # on WhatsApp the sender ID is their phone number
            save_order_to_csv(platform, customer_name, items, pickup_or_delivery, date_and_time, phone)
            return "Saved. Tell the customer the order is confirmed and the shop will contact them."

        return save_order

    def _lock_for(self, key):
        with self.locks_guard:
            return self.locks.setdefault(key, threading.Lock())
