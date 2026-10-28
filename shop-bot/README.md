# Sweet Crumbs: an AI shop website

A website for one local shop, with two pages:

| Page | Address | Who uses it |
|---|---|---|
| **Shop** | http://localhost:8000/ | Customers. They see the menu, offers and stock, order with a cart, or chat with the AI assistant in any language. |
| **Owner desk** | http://localhost:8000/owner | The shop owner only (password). Orders arrive here live. The owner adds or removes items, changes prices and stock, and starts offers with a timer. |

Everything the owner changes shows in the shop within 20 seconds, and the AI assistant knows about it straight away.

## What it does

**Customers**
- See every item with its price tag, "Only 2 left" warnings and "Sold out today" labels.
- See offers with a live countdown ("Offer ends in 1 h 12 min"). When the timer ends, the normal price comes back by itself.
- Order with the cart: pickup or home delivery, with the delivery fee worked out automatically.
- Or just chat: "1 kg red velvet for Saturday 5 PM, pickup". The AI repeats the order, asks "Shall I place it?", and places it after "yes".
- The assistant replies in Kannada, Hindi, English or any language the customer uses.

**Owner**
- Orders arrive on the desk by themselves (with an optional sound), sorted into New, Preparing and Ready.
- One click moves an order along. Cancelling puts the items back in stock.
- Edit name, category, description, price and stock right in the list. Add photos, hide items, delete items.
- Start an offer for 1 hour, 3 hours, until closing, until midnight, or until any time you pick.
- Change shop details: name, phone, address, opening hours, closed days, delivery fee, and notes for the AI assistant.

**Safety built in**
- Prices, stock and totals are always worked out by Python, never by the AI. The AI can't give a wrong price or sell more than the stock.
- Two customers can't buy the same last cake.
- The owner desk needs the password. Five wrong tries lock it for 10 minutes.
- Pages block outside scripts, and uploaded photos are checked.

## How it works

```
Customer page ──► app.py (web server) ──► database.py ──► shop.db (items, orders, shop details)
      │                  │
      └── chat ──► brain.py ──► Gemini AI (sees the live menu, places orders through Python)
Owner page ────► app.py (password needed) ──► database.py
```

| File | What it does |
|---|---|
| `app.py` | The web server: pages, customer API, owner API and sign-in. |
| `database.py` | Items, orders, offers and shop details, saved in `shop.db` (SQLite, built into Python). |
| `brain.py` | The AI assistant. Gets the live menu every message and places real orders. |
| `static/` | The two pages: HTML, CSS and JavaScript, plus the fonts. |
| `test_shop.py`, `test_bot.py` | 53 automatic tests. No keys or internet needed. |
| `try_in_terminal.py` | Chat with the assistant in the terminal. |
| `platforms.py`, `connect_instagram.py`, `fake_whatsapp_message.py` | WhatsApp and Instagram (paused, see the end). |

## Run it

1. Open a terminal in this folder and turn on the venv:
   ```
   venv\Scripts\activate
   ```
2. Add an owner password to `.env` (open it with `notepad .env`):
   ```
   OWNER_PASSWORD=choose-a-long-password
   ```
3. Run the tests. You should see `53 passed`:
   ```
   python -m pytest -q
   ```
4. Start the shop:
   ```
   python -m uvicorn app:app --port 8000
   ```
5. Open http://localhost:8000 for the shop and http://localhost:8000/owner for the owner desk.

The first start creates `shop.db` with 12 sample items and one sample offer. To start again from the sample shop, stop the server and delete `shop.db`.

**Show it on your phone:** keep the server running and run `ngrok http 8000` in a second terminal. Open your ngrok address on the phone. Add `/owner` for the owner desk.

## Make it a real shop's website

1. Sign in at `/owner`.
2. **Shop details** tab: change the name, phone, address, hours, delivery fee and notes for the assistant.
3. **Items** tab: delete the sample items and add the real ones with photos.

No code changes are needed. (`shop_info.txt` and `orders.csv` are from the first version and are no longer used.)

## Before real customers use it

- **Gemini paid tier:** on the free tier, Google may use the chats to improve its products. Real customers' chats should use the paid tier.
- **Always on:** your laptop and ngrok must stay on. A real shop needs the server on a cloud host.
- **Backups:** `shop.db` holds every order. Copy it somewhere safe regularly.
- **Payments:** customers pay at pickup or delivery. Online payment (UPI) would need a payment company like Razorpay.
- **Privacy:** `shop.db` has customers' names and phone numbers. `.gitignore` keeps it off GitHub. Keep it that way.

## WhatsApp and Instagram (paused)

The code is still here and tested. WhatsApp needs a payment method on Meta's side before replies are delivered. Instagram needs a professional account and a published Meta app. The webhook addresses are `/whatsapp` and `/instagram`.

## Fonts

Baloo Tamma 2 and Hind Mysuru, both made for Kannada and English, under the SIL Open Font License (licences in `static/fonts/`).
