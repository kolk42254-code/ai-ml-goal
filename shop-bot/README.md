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
- **My orders:** every order placed on the phone shows its live status (Waiting for the shop, Confirmed, Ready, Picked up or Delivered) and updates by itself within 15 seconds when the owner moves it along.
- Cancel an order while the shop hasn't confirmed it yet (the items go back on the counter), or **Order again** with one tap.
- Ordered on another phone, or by WhatsApp? Find the order with its number and phone number.

**Owner**
- Orders arrive on the desk by themselves (with an optional sound), sorted into New, Preparing and Ready.
- One click moves an order along. Cancelling puts the items back in stock.
- Edit name, category, description, price and stock right in the list. Add photos, hide items, delete items.
- Start an offer for 1 hour, 3 hours, until closing, until midnight, or until any time you pick.
- Change shop details: name, phone, address, opening hours, closed days, delivery fee, and notes for the AI assistant.
- **Find an order** by customer name, phone digits or order number. A message pops up when a customer cancels.
- **Earnings:** today, 7 days, 30 days, this month or all time. Money earned (completed orders), still to collect, average order, items sold, best-selling items, best customers, and a chart by day. **Download** the orders as a spreadsheet for Excel or Google Sheets.
- **Stock:** sold-out and low items first, how many sold this week, about how many days the stock will last, quick +1 / +5 / +10 buttons, and a history of every stock change (order, cancel, or changed by you).
- **Any kind of shop:** set the shop icon, the three quick questions on the shop page, and the hint in the order notes box.

**Safety built in**
- Prices, stock and totals are always worked out by Python, never by the AI. The AI can't give a wrong price or sell more than the stock.
- Two customers can't buy the same last cake.
- The owner desk needs the password. Five wrong tries lock it for 10 minutes.
- Pages block outside scripts, and uploaded photos are checked.
- Only the phone or browser that placed an order can see it (it keeps a secret tracking code). Finding an order from another phone needs both the order number and the phone number, and tries are limited.
- The owner's + and − stock buttons add to the stock on the server, so they never undo a sale that happened meanwhile.
- The spreadsheet download is protected against formula tricks typed into names or notes.

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
| `static/` | The two pages: HTML, CSS and JavaScript, plus the fonts. `motion.js` adds the shop page's greeting, animations and button effects; it never touches prices, the cart or orders. |
| `test_shop.py`, `test_bot.py`, `test_features.py`, `test_ollama.py` | 86 automatic tests. No keys or internet needed. |
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
3. Run the tests. You should see `86 passed`:
   ```
   python -m pytest -q
   ```
4. Start the shop:
   ```
   python -m uvicorn app:app --port 8000
   ```
5. Open http://localhost:8000 for the shop and http://localhost:8000/owner for the owner desk.

The first start creates `shop.db` with 12 sample items and one sample offer. To start again from the sample shop, stop the server and delete `shop.db`.

**Already have a `shop.db` from an older version?** It's upgraded by itself on the next start. Orders, items and shop details are kept. (Copy `shop.db` somewhere safe first anyway.)

**Show it on your phone:** keep the server running and run `ngrok http 8000` in a second terminal. Open your ngrok address on the phone. Add `/owner` for the owner desk.

## Test with a free AI model on your own computer (Ollama)

Instead of Gemini, the chat can use a model running on your computer with [Ollama](https://ollama.com), like `gemma4:e2b`. No Google key and no cost, but your computer must stay on with Ollama running, so use it for testing, not for a real shop.

1. Download the model once: `ollama pull gemma4:e2b`
2. Add these lines to `.env`:
   ```
   AI_PROVIDER=ollama
   OLLAMA_MODEL=gemma4:e2b
   ```
3. Start the shop as usual. Prices, stock and totals still come from Python. If the model can't place orders (no tool support), it answers questions and sends customers to the cart.

To go back to Gemini, change it to `AI_PROVIDER=gemini` and restart.

## Make it a real shop's website

1. Sign in at `/owner`.
2. **Shop details** tab: change the name, phone, address, hours, delivery fee and notes for the assistant. Pick the shop icon, write the three quick questions customers see, and the hint for the order notes box.
3. **Items** tab: delete the sample items and add the real ones with photos.

No code changes are needed. (`shop_info.txt` and `orders.csv` are from the first version and are no longer used.)

## Before real customers use it

- **Gemini paid tier:** on the free tier, Google may use the chats to improve its products. Real customers' chats should use the paid tier.
- **Always on:** your laptop and ngrok must stay on. A real shop needs the server on a cloud host. **[deploy/DEPLOY.md](deploy/DEPLOY.md)** is the step-by-step guide: domain, server, HTTPS, nightly backups and handover.
- **Backups:** `shop.db` holds every order. `python backup.py` makes a safe copy with the photos (the deploy guide runs it every night).
- **Payments:** customers pay at pickup or delivery. Online payment (UPI) would need a payment company like Razorpay.
- **Privacy:** `shop.db` has customers' names and phone numbers. `.gitignore` keeps it off GitHub. Keep it that way.

## WhatsApp and Instagram (paused)

The code is still here and tested. WhatsApp needs a payment method on Meta's side before replies are delivered. Instagram needs a professional account and a published Meta app. The webhook addresses are `/whatsapp` and `/instagram`.

## Fonts

Baloo Tamma 2 and Hind Mysuru, both made for Kannada and English, under the SIL Open Font License (licences in `static/fonts/`).
