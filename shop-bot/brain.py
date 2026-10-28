"""The AI assistant. It answers customers using the LIVE menu from the shop database,
remembers each chat, and places real orders through Python (which checks stock and totals)."""
import re
import threading
from datetime import timedelta

from google import genai
from google.genai import types

import config
import database

FORGET_AFTER = timedelta(hours=24)   # start a fresh chat after a day of silence
MAX_TURNS = 30                       # ...or after 30 customer messages (keeps it fast and cheap)
FALLBACK = "Sorry, I couldn't answer just now. Please try again in a minute."
PLATFORM_NAMES = {"whatsapp": "WhatsApp", "instagram": "Instagram", "web": "the shop's website"}

RULES = """You are the AI shop assistant of {shop_name}. Customers chat with you on the shop's website, WhatsApp or Instagram.
Follow these rules:
1. Only help with this shop: products, prices, offers, stock, timings, delivery, payment and orders.
   For anything else, politely say you can only help with the shop.
2. Use ONLY the shop details and the menu below. They are live and always up to date.
   Never make up items, prices, offers, stock or timings. If something isn't there, say you're not sure
   and share the shop's phone number.
3. Keep replies short (under 500 characters), warm and simple.
   Always reply in the plain language the customer writes in or asks for, including Kannada, Hindi, Tamil and Telugu.
   Never say you can't use a language. Write plain text only: no markdown, no ** stars and no # headings.
4. In your first reply of a chat, say you are the shop's AI assistant.
5. Never offer sold-out items, and never promise more than the stock left.
6. To take an order, collect: name, items and quantities, pickup or delivery (full address for delivery),
   when they want it, and phone number (unless it is already known). Then repeat the order with prices and the total
   (add the delivery fee if there is one) and ask the customer to confirm.
   Call place_order only after they clearly say yes. If place_order reports a problem, explain it and help fix it.
   After a successful order, give the order number and total that place_order returned.
7. If a customer is upset, asks for a refund or wants a human, share the shop's phone number and say the owner will help.

SHOP DETAILS:
{details}

RIGHT NOW: it is {now}. {status}.

MENU (live; the # number is the item ID to use in place_order):
{menu}

ABOUT THIS CUSTOMER: {about}"""


class ShopBrain:
    """One brain serves every customer. Each customer gets their own chat memory."""

    def __init__(self, client=None):
        if client is None:
            if not config.GEMINI_API_KEY:
                raise RuntimeError("GEMINI_API_KEY is missing. Put it in your .env file.")
            client = genai.Client(api_key=config.GEMINI_API_KEY)
        self.client = client
        self.sessions = {}                   # "web:abc123" -> {"chat", "last_seen", "turns"}
        self.locks = {}                      # one lock per customer
        self.locks_guard = threading.Lock()
        self.new_orders = {}                 # orders placed during the message being answered

    def reply(self, platform, user_id, text, name=""):
        """Just the answer text (used by WhatsApp, Instagram and the terminal)."""
        return self.chat(platform, user_id, text, name)[0]

    def chat(self, platform, user_id, text, name=""):
        """Answer one customer message. Returns (answer, list of orders placed while answering)."""
        key = f"{platform}:{user_id}"
        with self._lock_for(key):            # handle one message at a time per customer
            self.new_orders[key] = []
            session = self._session_for(key, platform, user_id, name)
            try:
                # Fresh settings every message, so the AI always sees today's prices, stock and time
                response = session["chat"].send_message(text, config=self._settings(platform, user_id, name))
                answer = (response.text or "").strip()
            except Exception as error:       # no internet, wrong key, free limit reached...
                print(f"[brain] Gemini error for {key}: {error}")
                answer = ""
            session["last_seen"] = database.now()
            session["turns"] += 1
            orders = self.new_orders.pop(key, [])
        return answer or FALLBACK, orders

    def _session_for(self, key, platform, user_id, name):
        """Reuse the customer's chat, or start a new one if it is too old or too long."""
        now = database.now()
        session = self.sessions.get(key)
        if session is None or now - session["last_seen"] > FORGET_AFTER or session["turns"] >= MAX_TURNS:
            # forget chats that have been quiet for a day, so memory doesn't grow forever
            self.sessions = {k: s for k, s in self.sessions.items() if now - s["last_seen"] <= FORGET_AFTER}
            chat = self.client.chats.create(model=config.GEMINI_MODEL, config=self._settings(platform, user_id, name))
            session = {"chat": chat, "last_seen": now, "turns": 0}
            self.sessions[key] = session
        return session

    def _settings(self, platform, user_id, name):
        """The AI's instructions with the live shop details, time, open/closed status and menu."""
        shop = database.get_settings()
        at = database.now()
        if platform == "whatsapp":
            about = "They are on WhatsApp, so their phone number is already known: don't ask for it."
        else:
            where = PLATFORM_NAMES.get(platform, "a test chat")
            about = f"They are on {where}, so ask for their phone number when taking an order."
        if name:
            about += f" Their profile name is {name}."
        instructions = RULES.format(
            shop_name=shop["shop_name"], details=database.shop_details_text(shop),
            now=f"{at:%A %d %B %Y}, {database.clock(at.time())}", status=database.shop_status(shop, at)["text"],
            menu=database.menu_text(at), about=about)
        return types.GenerateContentConfig(system_instruction=instructions,
                                           tools=[self.make_place_order(platform, user_id)])

    def make_place_order(self, platform, user_id):
        """Build the place_order tool for one customer (it remembers their platform and ID)."""
        key = f"{platform}:{user_id}"

        def place_order(customer_name: str, items: str, pickup_or_delivery: str, delivery_address: str,
                        wanted_at: str, phone: str, notes: str) -> str:
            """Place a confirmed order. Call this only after the customer said yes to the order summary.

            Args:
                customer_name: The customer's name.
                items: Item IDs from the menu with quantities, like "3:1, 9:6" (item 3 x1 and item 9 x6).
                pickup_or_delivery: "pickup" or "delivery".
                delivery_address: The full address for delivery, or an empty string for pickup.
                wanted_at: When the customer wants the order, for example "Saturday 5 PM".
                phone: The customer's phone number. Use an empty string if it is already known.
                notes: Extra requests like eggless or the message on the cake, or an empty string.
            """
            pairs = [(int(item_id), int(qty)) for item_id, qty in re.findall(r"(\d+)\s*[:xX×*]\s*(\d+)", items)]
            if not pairs:
                return 'Order NOT placed: the items could not be read. Use menu IDs and quantities like "3:1, 9:6".'
            if platform == "whatsapp" and not database.clean_phone(phone):
                phone = user_id              # on WhatsApp the sender ID is their phone number
            source = "chat" if platform == "web" else platform
            try:
                order = database.place_order(source, customer_name, phone, pickup_or_delivery, delivery_address,
                                             wanted_at, notes, pairs)
            except database.OrderError as problem:
                return f"Order NOT placed: {problem} Explain this to the customer and help them fix it."
            self.new_orders.setdefault(key, []).append(order)
            if order["fulfilment"] == "pickup":
                how = "pickup"
            elif order["delivery_fee"]:
                how = f"delivery fee ₹{database.rupees(order['delivery_fee'])}"
            else:
                how = "free delivery"
            return (f"Order #{order['id']} is placed. Total ₹{database.rupees(order['total'])} "
                    f"(items ₹{database.rupees(order['subtotal'])}, {how}). Tell the customer the order number and "
                    "total, that payment is at pickup or delivery, and that the shop will contact them to confirm.")

        return place_order

    def _lock_for(self, key):
        with self.locks_guard:
            return self.locks.setdefault(key, threading.Lock())
