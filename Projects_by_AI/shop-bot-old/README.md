# Sweet Crumbs Bot: an AI chatbot for WhatsApp and Instagram (demo)

A Python bot for a **made-up bakery**. It answers customers on **WhatsApp** and **Instagram DMs** with Google's **Gemini** AI, and it **takes cake orders** and saves them in `orders.csv`.

Use it to learn, and to show shop owners what an AI assistant can do. For a real shop, you only change `shop_info.txt`.

## What the bot does

- Answers questions about the shop: prices, timings, delivery, payment.
- Takes orders: asks for the details, repeats the order with the total, and saves it after the customer says yes.
- Says it is an AI assistant, and talks only about the shop (needed for WhatsApp's rules).
- Replies in the customer's language.
- Shares the shop's phone number when it doesn't know something or the customer wants a human.

## How it works

```
Customer ─► WhatsApp / Instagram ─► Meta ─► your server (app.py)
                                                 │
                                   brain.py ─► Gemini AI + shop_info.txt
                                                 │
Customer ◄─ WhatsApp / Instagram ◄─ Meta ◄─ platforms.py sends the reply
```

| File | What it does |
|---|---|
| `app.py` | The web server. Meta sends every new message here. |
| `brain.py` | Talks to Gemini, remembers each chat, saves orders. |
| `platforms.py` | Reads WhatsApp/Instagram messages and sends the replies. |
| `config.py` | Reads your keys from `.env`. |
| `shop_info.txt` | The shop's details. **Edit this for a real shop.** |
| `try_in_terminal.py` | Chat with the bot in your terminal. No Meta setup needed. |
| `connect_instagram.py` | Turns on Instagram DM webhooks for your account (Step 5). |
| `test_bot.py` | 18 automatic tests with fake messages. |

## Rules to know first (checked 21 Oct 2026)

1. **WhatsApp bans "ask me anything" AI bots** on its business platform since 15 Jan 2026. Bots that serve a business's own customers (questions, orders, bookings) are allowed. This bot only talks about the shop.
2. **Use only official APIs**, like this project does. Tools that control a personal WhatsApp or Instagram account break their rules and can get the account banned.
3. **The customer must message first.** After that, the bot can reply for 24 hours on both apps.
4. **WhatsApp replies are free** inside that 24-hour window.
5. **Gemini's free tier:** Google may use the chats to improve its products. Fine for a demo. For a real shop with real customers, use the paid tier (for `gemini-3.5-flash-lite`: $0.30 per 1 million input tokens and $2.50 per 1 million output tokens).

---

## Step 0: Install (5 minutes)

You need **Python 3.10 or newer**. Open a terminal in the `shop-bot` folder.

**Windows**
```
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

**Ubuntu**
```
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```
(If `venv` fails on Ubuntu, run `sudo apt install python3-venv` first.)

Open `.env` and change `VERIFY_TOKEN` to any secret word you like.

## Step 1: Run the tests (1 minute)

```
python -m pytest -q
```
You should see `18 passed`. This checks the code without any keys or internet.

## Step 2: Free Gemini key + chat in the terminal (10 minutes)

1. Open https://aistudio.google.com/apikey, sign in with Google and click **Create API key**.
2. Paste the key in `.env` after `GEMINI_API_KEY=`.
3. Run `python try_in_terminal.py` and act like a customer. Try:
   - `Are you open now?`
   - `Price of 1 kg red velvet, eggless?`
   - `I want to order a pineapple cake for Saturday`
   - `What is the capital of France?` (it should politely say it only helps with the shop)
4. Confirm an order, then open `orders.csv`. Your order is there.

## Step 3: Put your server online with ngrok (free)

Meta must be able to reach your laptop. ngrok gives it a public `https://` address.

1. Sign up at https://ngrok.com (free plan), install ngrok, and run the `ngrok config add-authtoken ...` command shown in your ngrok dashboard.
2. **Terminal 1:** `uvicorn app:app --port 8000`
3. **Terminal 2:** `ngrok http 8000`. Copy the `https://...` address it shows. The free plan gives you one fixed address, so it stays the same next time.
4. Open that address in your browser. ngrok first shows a warning page; click **Visit Site**. You should see `{"status":"Shop chatbot is running"}`.

Keep both terminals open while testing. **After you change `.env`, stop the server (Ctrl+C) and start it again.**

## Step 4: Connect WhatsApp (free test number)

1. Go to https://developers.facebook.com/apps and click **Create App**.
2. Choose the use case **Connect with customers through WhatsApp**, pick or create a business portfolio, and create the app.
3. Click **Start using the API**. On the **API Setup** page:
   - Connect or create a WhatsApp Business account if it asks.
   - Click **Generate access token** and copy it to `WHATSAPP_TOKEN`.
   - Copy the test number's **Phone number ID** to `WHATSAPP_PHONE_NUMBER_ID`.
   - In the **To** box, choose **Manage phone number list**, add your own WhatsApp number and type the code you receive. (The test number can message up to 5 numbers.)
   - Click **Send message**. A "hello world" message arrives on your WhatsApp.
4. Open **App settings → Basic → App secret → Show** and copy it to `WHATSAPP_APP_SECRET`.
5. Restart the server.
6. Open **WhatsApp → Configuration**. Callback URL: `https://YOUR-NGROK-ADDRESS/whatsapp`. Verify token: your `VERIFY_TOKEN` word. Click **Verify and save**, then subscribe to the **messages** field.
7. On your phone, reply to the test number: `Hi, do you have eggless cakes?` The bot answers.

**Token note:** the token from step 3 expires quickly. For longer testing, make a permanent one: Business Settings → **System users** → add a system user → **Assign assets** (your app and your WhatsApp account, full control) → **Generate token** with `business_management`, `whatsapp_business_messaging` and `whatsapp_business_management`.

## Step 5: Connect Instagram

You need:
- An Instagram **professional account** (Business or Creator) for the shop. You can switch an account to professional in the Instagram app's settings.
- A second Instagram account to act as the customer.

1. In your Meta app, add **Instagram** and open **Instagram → API setup with Instagram login**. (Meta renames menus often. If a name is different, pick the closest one.)
2. Under **Generate access tokens**, click **Add account**, log in with the professional account, then **Generate token**. Copy it to `INSTAGRAM_TOKEN`. Allow `instagram_business_basic` and `instagram_business_manage_messages`. Tokens made here last 60 days.
3. Copy **App settings → Basic → App secret** to `INSTAGRAM_APP_SECRET` (the same value as WhatsApp if it is the same app).
4. Restart the server.
5. Under **Configure webhooks**: Callback URL `https://YOUR-NGROK-ADDRESS/instagram`, Verify token = your word. Click **Verify and save**, then subscribe to **messages**.
6. Run `python connect_instagram.py`. It shows which account the token belongs to and turns on DM webhooks for it.
7. Switch the app to **Live** (top of the dashboard). Meta sends Instagram webhooks only to Live apps. First fill in **App settings → Basic**: display name, contact email, app icon, category, app purpose and a Terms of Service link (a simple public page you write).
8. From your second Instagram account, send a DM to the shop account. The bot answers.

**Access note:** without Meta's App Review your app has "Standard Access". Meta says that is enough for Instagram professional accounts you own or manage, so it's fine for this demo. If you later run the bot for other people's shop accounts, Meta asks for "Advanced Access" (App Review and business verification).

## Step 6: Make it real

- **Real shop:** put their menu, prices, timings and phone in `shop_info.txt`. No code changes needed.
- **Orders:** `orders.csv` opens in Excel or Google Sheets.
- **Always on:** laptop + ngrok works only while your laptop is on. A real shop needs the bot on a cloud server.
- **Real number:** a real shop connects its own business number instead of the test number.
- **Privacy:** use Gemini's paid tier for real customers' chats.

---

## Troubleshooting

| Problem | What to check |
|---|---|
| Meta can't verify the callback URL | Are the server and ngrok both running? Is the word the same in `.env` and Meta? Did you restart the server after editing `.env`? Does the address end with `/whatsapp` or `/instagram`? |
| The server log shows `401` for a POST | Wrong app secret in `.env`. For Instagram, if the App secret doesn't work, try the "Instagram app secret" on the API setup page. |
| `[send] Meta said 401` | The token expired or is wrong. Make a new one. |
| The bot says "Sorry, I couldn't answer just now" | Read the `[brain] Gemini error` line in the server log. `429` means the free limit is used up for now, so wait a little. `404` usually means a wrong `GEMINI_MODEL` name. |
| WhatsApp message gets no reply | Is your number in the test number's list? Did you subscribe to **messages**? |
| Instagram DM gets no reply | Is the app Live? Did `connect_instagram.py` say "Done"? Are you sending from a different account than the shop's? |

## A note about the Gemini library

Google's docs now also show a newer "Interactions API". This project uses the chat API (`client.chats`), which Google says is still fully supported.

## What you practise with this project

- **Webhooks and REST APIs:** how apps send data to each other.
- **JSON, `.env` secrets and background tasks** in FastAPI.
- **AI function calling:** Gemini decides when to run your Python function `save_order`. This is the main idea behind AI agents.

## Sources

- WhatsApp Cloud API, get started: https://developers.facebook.com/documentation/business-messaging/whatsapp/get-started
- WhatsApp webhook setup: https://developers.facebook.com/documentation/business-messaging/whatsapp/webhooks/set-up-whatsapp-echo-bot
- Instagram, send messages: https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/messaging-api
- Instagram webhooks setup: https://developers.facebook.com/documentation/instagram-platform/webhooks/setup
- Instagram, get started (account ID, 60-day tokens): https://developers.facebook.com/documentation/instagram-platform/instagram-api-with-instagram-login/get-started
- Fields needed before going Live: https://developers.facebook.com/documentation/development/create-an-app/app-dashboard/basic-settings
- Graph API versions (v26.0): https://developers.facebook.com/docs/graph-api/changelog
- WhatsApp's 2026 AI chatbot policy: https://respond.io/blog/whatsapp-general-purpose-chatbots-ban
- Free WhatsApp service conversations: https://guides.clickatell.com/release-notes/release-notes-archive/2025-release-notes/q4-2025/channel-updates/whatsapp-free-service-conversations
- Gemini models: https://ai.google.dev/gemini-api/docs/models
- Gemini pricing and free tier: https://ai.google.dev/gemini-api/docs/pricing
- ngrok free plan: https://ngrok.com/docs/pricing-limits/free-plan-limits
