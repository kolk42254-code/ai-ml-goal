"""The AI assistant. It answers customers using the LIVE menu from the shop database,
remembers each chat, and places real orders through Python (which checks stock and totals)."""
import json
import re
import threading
import urllib.error
import urllib.request
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
   Items marked (VEG) are vegetarian and (NON-VEG) are not. If a customer asks for veg food, offer only (VEG) items;
   if an item has no mark, say you're not sure and share the shop's phone number.
6. To take an order, collect: name, items and quantities, pickup or delivery (full address for delivery),
   when they want it, and phone number (unless it is already known). Then repeat the order with prices and the total
   (add the delivery fee if there is one) and ask the customer to confirm.
   Call place_order only after they clearly say yes. If place_order reports a problem, explain it and help fix it.
   After a successful order, give the order number and total that place_order returned.
7. If a customer is upset, asks for a refund or wants a human, share the shop's phone number and say the owner will help.
8. If a customer asks about an order they already placed: on the website, tell them to tap "My orders" at the top
   of the page to see its live status and cancel it while it is still waiting. Otherwise share the shop's phone number.
   You can't see or change existing orders yourself.

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
        return honest_reply(answer, orders) or FALLBACK, orders

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
        """Gemini's settings: the instructions plus the place_order tool."""
        return types.GenerateContentConfig(system_instruction=self._instructions(platform, user_id, name),
                                           tools=[self.make_place_order(platform, user_id)])

    def _instructions(self, platform, user_id, name):
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
        return instructions

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


# ===================== A local model through Ollama (for testing on your own computer) =====================

NO_TOOLS_NOTE = ("\n\nIMPORTANT: you can't place orders in this chat. When a customer wants to order, tell them to tap "
                 "Add on the items and use the cart, or to call the shop.")
PLACE_ORDER_TOOL = {"type": "function", "function": {
    "name": "place_order",
    "description": "Place a confirmed order. Call this only after the customer said yes to the order summary.",
    "parameters": {"type": "object", "required": ["customer_name", "items", "pickup_or_delivery", "delivery_address",
                                                   "wanted_at", "phone", "notes"],
                   "properties": {
                       "customer_name": {"type": "string", "description": "The customer's name."},
                       "items": {"type": "string",
                                 "description": 'Item IDs from the menu with quantities, like "3:1, 9:6".'},
                       "pickup_or_delivery": {"type": "string", "enum": ["pickup", "delivery"]},
                       "delivery_address": {"type": "string", "description": "Full address, or empty for pickup."},
                       "wanted_at": {"type": "string", "description": "When the customer wants it, like today 8 PM."},
                       "phone": {"type": "string", "description": "Phone number, or empty if already known."},
                       "notes": {"type": "string", "description": "Extra requests like less spicy, or empty."}}}}}


def _ollama_post(url, payload, timeout=180):
    request = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as error:
        raise OllamaError(error.read().decode(errors="replace")) from None


class OllamaError(Exception):
    pass


class OllamaBrain(ShopBrain):
    """The same assistant, answered by a model running on this computer with Ollama (like gemma4:e2b).
    Prices, stock and totals still come from Python. If the model can't use tools, it answers questions
    and sends customers to the cart instead of placing orders."""

    def __init__(self, post=None, model=None, url=None):
        self.post = post or _ollama_post
        self.model = model or config.OLLAMA_MODEL
        self.url = (url or config.OLLAMA_URL).rstrip("/") + "/api/chat"
        self.use_tools = True
        self.use_think = True
        self.sessions, self.locks, self.new_orders = {}, {}, {}
        self.locks_guard = threading.Lock()

    def chat(self, platform, user_id, text, name=""):
        key = f"{platform}:{user_id}"
        with self._lock_for(key):
            self.new_orders[key] = []
            session = self._session_for(key, platform, user_id, name)
            session["history"].append({"role": "user", "content": text})
            try:
                answer = self._answer(session, platform, user_id, name)
            except Exception as error:                    # Ollama closed, model not downloaded, too slow...
                print(f"[brain] Ollama error for {key}: {error}")
                session["history"].pop()
                answer = ""
            if answer and not self.new_orders.get(key) and ORDER_CLAIM.search(answer) and said_yes(text):
                answer = self._place_from_form(session, platform, user_id, name, key) or answer
            if answer:
                session["history"].append({"role": "assistant", "content": answer})
            session["history"] = session["history"][-20:]     # keep it quick on a small computer
            session["last_seen"] = database.now()
            session["turns"] += 1
            orders = self.new_orders.pop(key, [])
        return honest_reply(clean_reply(answer), orders) or FALLBACK, orders

    def _session_for(self, key, platform, user_id, name):
        now = database.now()
        session = self.sessions.get(key)
        if session is None or now - session["last_seen"] > FORGET_AFTER or session["turns"] >= MAX_TURNS:
            self.sessions = {k: s for k, s in self.sessions.items() if now - s["last_seen"] <= FORGET_AFTER}
            session = {"history": [], "last_seen": now, "turns": 0}
            self.sessions[key] = session
        return session

    def _answer(self, session, platform, user_id, name):
        tool = self.make_place_order(platform, user_id)
        extra = []                                            # tool calls and results within this one answer
        for _ in range(4):                                    # at most a few tool rounds, then a plain answer
            message = self._ask(session, platform, user_id, name, extra)
            calls = message.get("tool_calls") or []
            if not calls:
                return (message.get("content") or "").strip()
            extra.append({"role": "assistant", "content": message.get("content") or "", "tool_calls": calls})
            for call in calls:
                function = call.get("function", {})
                extra.append({"role": "tool", "tool_name": function.get("name", ""),
                              "content": self._run_tool(tool, function)})
        return ""

    def _place_from_form(self, session, platform, user_id, name, key):
        """The model said "order placed" after the customer said yes, but didn't call place_order (small models
        often don't). Ask it to fill in a strict order form instead, and let Python place and check the order.
        Returns the reply for the customer, or "" if no order could be read from the chat."""
        system = (self._instructions(platform, user_id, name) + "\n\nNow read the whole conversation and fill in the "
                  "order form for the order the customer just confirmed. Use the menu # numbers as item_id. "
                  "Set confirmed to false if the customer did not clearly confirm an order. Use empty text for "
                  "anything the customer didn't say.")
        payload = {"model": self.model, "stream": False, "format": ORDER_FORM, "options": {"temperature": 0},
                   "messages": [{"role": "system", "content": system}, *session["history"]]}
        if self.use_think:
            payload["think"] = False
        try:
            form = json.loads(self.post(self.url, payload)["message"]["content"])
        except Exception as error:                            # unreadable form: fall back to the honest message
            print(f"[brain] Couldn't read the order form: {error}")
            return ""
        if not isinstance(form, dict) or form.get("confirmed") is not True:
            return ""
        pairs = []
        for line in form.get("items") or []:
            try:
                pairs.append(f"{int(line['item_id'])}:{int(line['quantity'])}")
            except (KeyError, TypeError, ValueError):
                continue
        if not pairs:
            return ""
        tool = self.make_place_order(platform, user_id)
        result = tool(customer_name=str(form.get("customer_name") or ""), items=", ".join(pairs),
                      pickup_or_delivery=str(form.get("pickup_or_delivery") or ""),
                      delivery_address=str(form.get("delivery_address") or ""),
                      wanted_at=str(form.get("wanted_at") or ""), phone=str(form.get("phone") or ""),
                      notes=str(form.get("notes") or ""))
        placed = self.new_orders.get(key) or []
        if not placed:                                        # Python refused it: say exactly why
            problem = result.removeprefix("Order NOT placed:").split(" Explain this")[0].strip()
            return f"I couldn't place the order yet: {problem}"
        order = placed[-1]
        lines = ", ".join(f"{line['quantity']} x {line['name']}" for line in order["items"])
        how = ("pickup at the shop" if order["fulfilment"] == "pickup"
               else f"delivery fee Rs {database.rupees(order['delivery_fee'])}" if order["delivery_fee"] else "free delivery")
        return (f"Your order #{order['id']} is placed: {lines}. Total Rs {database.rupees(order['total'])} ({how}). "
                "You pay at pickup or delivery. You can follow it in My orders.")

    def _run_tool(self, tool, function):
        if function.get("name") != "place_order":
            return f"Unknown tool {function.get('name')!r}. Only place_order exists."
        arguments = function.get("arguments") or {}
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except ValueError:
                arguments = {}
        names = PLACE_ORDER_TOOL["function"]["parameters"]["required"]
        values = {k: str(arguments.get(k) or "") for k in names}
        return tool(**values)

    def _ask(self, session, platform, user_id, name, extra):
        system = self._instructions(platform, user_id, name) + ("" if self.use_tools else NO_TOOLS_NOTE)
        payload = {"model": self.model, "stream": False, "options": {"temperature": 0.3},
                   "messages": [{"role": "system", "content": system}, *session["history"], *extra]}
        if self.use_tools:
            payload["tools"] = [PLACE_ORDER_TOOL]
        if self.use_think:
            payload["think"] = False
        try:
            return self.post(self.url, payload)["message"]
        except OllamaError as error:
            problem = str(error).lower()
            if self.use_think and "think" in problem:         # this model has no thinking mode
                self.use_think = False
                return self._ask(session, platform, user_id, name, extra)
            if self.use_tools and "tool" in problem:          # this model can't call tools: answer without them
                print(f"[brain] {self.model} can't place orders by chat (no tool support). Customers use the cart.")
                self.use_tools = False
                return self._ask(session, platform, user_id, name, extra)
            raise


# The order form a small model fills in when it won't call place_order by itself (Ollama keeps it to this shape).
ORDER_FORM = {"type": "object", "required": ["confirmed", "customer_name", "items", "pickup_or_delivery",
                                              "delivery_address", "wanted_at", "phone", "notes"],
              "properties": {
                  "confirmed": {"type": "boolean"},
                  "customer_name": {"type": "string"},
                  "items": {"type": "array", "items": {"type": "object", "required": ["item_id", "quantity"],
                                                       "properties": {"item_id": {"type": "integer"},
                                                                      "quantity": {"type": "integer"}}}},
                  "pickup_or_delivery": {"type": "string", "enum": ["pickup", "delivery"]},
                  "delivery_address": {"type": "string"}, "wanted_at": {"type": "string"},
                  "phone": {"type": "string"}, "notes": {"type": "string"}}}

YES = re.compile(r"\b(yes|yeah|yep|yup|ok|okay|sure|confirm(ed)?|place (it|the order)|go ahead|done|haan|han|ha|ji|"
                 r"theek|thik|correct|right)\b|ಹೌದು|ಸರಿ|ಆಗಲಿ|हाँ|हां|ठीक|சரி|ஆம்|అవును|సరే", re.IGNORECASE)


def said_yes(text):
    """Did the customer's message confirm (yes, ok, haan, ಹೌದು, सरी...)?"""
    return bool(YES.search(text or ""))


# Words a model uses when it says an order was placed. Small models sometimes say this without placing anything.
ORDER_CLAIM = re.compile(
    r"placed (?:your|the) order|order (?:is|has been|was) (?:placed|confirmed|booked)|(?:have|has|I've) placed"
    r"|order (?:number|no\.?|id) (?:is|:)|order\s*#\s*\d+|\[[^\]]*order[^\]]*\]", re.IGNORECASE)
PLACEHOLDER = re.compile(r"\[[^\]]*(?:order|number|total|amount)[^\]]*\]", re.IGNORECASE)


def honest_reply(text, orders):
    """Never let the model tell a customer an order was placed when Python didn't place one,
    and fill in blanks like [Order Number] with the real number."""
    if orders:
        last = orders[-1]
        return PLACEHOLDER.sub(f"#{last['id']}", text)
    if ORDER_CLAIM.search(text or ""):
        print(f"[brain] The model said an order was placed, but none was. Reply replaced: {text!r}")
        shop = database.get_settings()
        return ("Sorry, I couldn't place the order from this chat. Please tap Add on the items and order with the "
                f"cart, or call the shop at {shop['phone']}.")
    return text


def clean_reply(text):
    """Small models often add markdown stars and headings even when told not to."""
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text or "")
    return re.sub(r"^\s*#+\s*", "", text, flags=re.M).strip()


def assistant_name():
    """Which AI answers the chat, as set in .env, like "gemma4:e2b (Ollama, on this computer)"."""
    if config.AI_PROVIDER == "ollama":
        return f"{config.OLLAMA_MODEL} (Ollama, on this computer)"
    return f"{config.GEMINI_MODEL} (Google Gemini)"


def make_brain():
    """The assistant the shop uses: Gemini (default) or a local Ollama model (AI_PROVIDER=ollama in .env)."""
    bot = OllamaBrain() if config.AI_PROVIDER == "ollama" else ShopBrain()
    print(f"[brain] Chat answers come from: {assistant_name()}")
    return bot
