# Make a shop live: step by step

For the person setting up the website for a shop owner (the client). It takes about 2 hours the first time.
Every command is copy-paste. Lines in CAPITALS (like `SERVER_IP` or `SHOPDOMAIN.in`) are the parts you change.

The finished setup: the client's own domain (like `https://ramstores.in`) with the padlock (HTTPS), on a small
server in India, running all the time, restarting by itself after a crash or reboot, with a backup every night.

---

## 1. Before you buy anything

**Agree in writing** (a WhatsApp message is fine) on the price, what's included, who pays the monthly costs,
and how you get paid. Take the advance first.

**Monthly costs, paid by the client in their own name** (rough prices, November 2026. Check the provider's page; Indian bills add 18% GST):

| What | About |
|---|---|
| Server (VPS) in Mumbai or Bangalore, 1 GB RAM or more | ₹350 to ₹700 a month |
| Domain like `shopname.in` | ₹1 to ₹200 the first year on offer, then ₹625 to ₹900 a year plus GST |
| AI chat (Google Gemini, paid plan) | roughly ₹100 to ₹150 per 1,000 customer chat messages |

So about **₹600 to ₹1,200 a month** in total for a small shop.

**Collect from the client:**
- Shop name, phone number, full address, opening and closing time, closed days
- Delivery fee, the order amount for free delivery, delivery area and times
- Every item: name, category, price, how many in stock, a short description, a photo
- A shop icon (one emoji), three questions customers often ask, a hint for the order notes box (like "Size or colour")
- The domain name they want (check it's free on a registrar's site)
- Their Gmail account (for the AI key) and a way to pay for the server and domain (their card or UPI)

## 2. Buy the accounts, in the client's name

Sit with the client and create these with **their** email and **their** payment. Then the website belongs to them,
and you never pay their bills. Write every login down for them.

1. **Domain:** any registrar (Hostinger, GoDaddy, BigRock, Namecheap...). Buy `SHOPDOMAIN.in`.
2. **Server:** any provider with an India region (DigitalOcean Bangalore, AWS Lightsail Mumbai, Vultr Mumbai, Hostinger VPS...).
   Choose **Ubuntu 24.04 LTS** and the smallest plan with **1 GB RAM or more** (512 MB works but is tight).
   Note the server's **IP address** and the **root password** (or add your SSH key).
3. **AI key:** in the client's Google account, open https://aistudio.google.com/api-keys and press **Create API key**.
   Before real customers chat, turn on billing (paid plan): on the free plan Google may use the chats to improve its products.
   In Google Cloud billing, set a **budget alert** (for example ₹500 a month) so nothing surprises the client.

## 3. Point the domain to the server

In the registrar's **DNS settings** for `SHOPDOMAIN.in`, add two records (delete any old "A" records first):

| Type | Name | Value |
|---|---|---|
| A | `@` | `SERVER_IP` |
| A | `www` | `SERVER_IP` |

It usually works within 5 to 60 minutes. Continue with the next steps meanwhile.

## 4. Prepare the server

From your laptop or Termux, log in to the server:

```
ssh root@SERVER_IP
```

Then run these one by one (all as root):

```
timedatectl set-timezone Asia/Kolkata && systemctl restart cron
```
```
apt update && apt upgrade -y
```
```
apt install -y python3-venv unzip caddy
```
```
useradd --create-home --shell /bin/bash shop
```
```
ufw allow OpenSSH && ufw allow 80,443/tcp && ufw --force enable
```

The shop runs as the user `shop`, not as root, so a mistake in the website can't damage the whole server.
**Some providers also have their own firewall in their website** (AWS Lightsail: Networking tab). Open ports 80 and 443 there too.

## 5. Copy the shop to the server and install it

On your laptop or Termux, in the folder with `shop-bot.zip`:

```
scp shop-bot.zip root@SERVER_IP:/home/shop/
```

Back on the server (as root):

```
chown shop:shop /home/shop/shop-bot.zip && sudo -iu shop
```

Now you are the `shop` user. Run:

```
unzip -o shop-bot.zip && cd shop-bot
```
```
python3 -m venv venv && venv/bin/pip install -r requirements.txt
```

Make a strong owner password (write it down for the client):

```
python3 -c "import secrets; print(secrets.token_urlsafe(12))"
```

Create the settings file:

```
nano .env
```

Type these two lines (your password and the client's key), then save with Ctrl+O, Enter, Ctrl+X:

```
OWNER_PASSWORD=THE-PASSWORD-YOU-JUST-MADE
GEMINI_API_KEY=THE-CLIENTS-KEY
```

Lock the file and run the tests:

```
chmod 600 .env && venv/bin/python -m pytest -q
```

You should see `91 passed`. Then go back to root:

```
exit
```

## 6. Start the shop and keep it running

As root:

```
cp /home/shop/shop-bot/deploy/shop.service /etc/systemd/system/shop.service
```
```
systemctl daemon-reload && systemctl enable --now shop
```
```
curl -s http://127.0.0.1:8000/health
```

You should see `{"status":"Shop chatbot is running"}`. From now on the shop starts by itself when the server boots,
and restarts by itself within 3 seconds if it ever stops.

## 7. Turn on HTTPS (the padlock)

As root (change `SHOPDOMAIN.in` to the real domain in the second command):

```
cp /home/shop/shop-bot/deploy/Caddyfile /etc/caddy/Caddyfile
```
```
sed -i 's/example\.in/SHOPDOMAIN.in/g' /etc/caddy/Caddyfile
```
```
systemctl reload caddy
```

Open `https://SHOPDOMAIN.in` on your phone. The first visit can take up to a minute while the free certificate
is issued. Caddy renews it by itself before it expires.

## 8. Nightly backups

As root, back up every night at 2:30 AM (keeps the newest 14):

```
sudo -iu shop bash -c '(crontab -l 2>/dev/null; echo "30 2 * * * cd /home/shop/shop-bot && mkdir -p backups && venv/bin/python backup.py >> backups/backup.log 2>&1") | crontab -'
```

Make the first backup now to check it works:

```
sudo -iu shop bash -c 'cd shop-bot && venv/bin/python backup.py'
```

A backup on the same server doesn't help if the server itself is lost. **Once a week, copy the backups to your
computer** (run this on your laptop):

```
scp 'root@SERVER_IP:/home/shop/shop-bot/backups/shop-backup-*.zip' .
```

## 9. Test, then put in the real shop

1. On your phone, open `https://SHOPDOMAIN.in`. Order something with the cart.
2. Open `https://SHOPDOMAIN.in/owner`, sign in, press **Confirm order**. Within 15 seconds the phone shows "Confirmed".
3. Ask the chat assistant something. If it says the assistant is off, check `GEMINI_API_KEY` in step 5.
4. Start fresh, so the client's earnings start at zero (as root):
   ```
   systemctl stop shop && rm -f /home/shop/shop-bot/shop.db /home/shop/shop-bot/shop.db-wal /home/shop/shop-bot/shop.db-shm /home/shop/shop-bot/uploads/* && systemctl start shop
   ```
5. In the owner desk:
   - **Shop details:** name, phone, address, hours, closed days, delivery, shop icon, quick questions, notes hint,
     and notes for the AI assistant (what customers often ask: brands, sizes, payment, parking). Press **Save**.
   - **Items:** delete the 12 sample items. Add the real items with photos and stock.
6. Order once more from your phone, then cancel it from **My orders**. Check that the stock went back.

## 10. Hand over to the client

Give the client:
- The website address, and the owner desk address (`https://SHOPDOMAIN.in/owner`)
- The owner password, **in person** (not in a group chat). They should keep it private.
- The logins for the domain, the server and Google, all in their name

Show them, on their phone (15 minutes):
- Bookmark the owner desk. Press **Turn on new-order sound**.
- New order → **Confirm order** → **Mark ready** → **Mark picked up / delivered**. Cancel puts stock back.
- **Items:** change prices and stock, add photos, start an offer with a timer.
- **Stock:** +1 / +5 / +10 when new stock arrives, and the history.
- **Earnings:** today, this week, this month; **Download** for their accountant.
- If the website ever doesn't open: call you.

## 11. Get told when the website is down

Make a free account at **UptimeRobot** (or a similar free monitor). Add an HTTP(S) monitor for
`https://SHOPDOMAIN.in/health` every 5 minutes, with alerts to your email or phone.

## 12. Updating the shop later

On your laptop, in the `ai-ml-goal` folder, make a new zip:

```
git archive --format=zip -o shop-bot.zip HEAD shop-bot
```

Copy it and install it (orders, photos, the password and backups are kept):

```
scp shop-bot.zip root@SERVER_IP:/home/shop/
```
```
ssh root@SERVER_IP
```
```
chown shop:shop /home/shop/shop-bot.zip && sudo -iu shop bash -c 'cd ~/shop-bot && venv/bin/python backup.py && cd ~ && unzip -o shop-bot.zip && cd ~/shop-bot && venv/bin/pip install -q -r requirements.txt && venv/bin/python -m pytest -q'
```

If all tests pass, restart: `systemctl restart shop`. If a test fails, don't restart. The old version keeps running until you do.

---

## Bring back a backup

As root. Change `BACKUP-FILE.zip` to the backup you want (see them with `ls /home/shop/shop-bot/backups`):

```
systemctl stop shop && cd /home/shop/shop-bot && rm -f shop.db-wal shop.db-shm
```
```
sudo -u shop unzip -o backups/BACKUP-FILE.zip -d /home/shop/restore && sudo -u shop cp /home/shop/restore/shop.db shop.db
```
```
[ -d /home/shop/restore/uploads ] && sudo -u shop cp -r /home/shop/restore/uploads/. uploads/; rm -rf /home/shop/restore && systemctl start shop
```

## When something is wrong

| What you see | What to check (as root) |
|---|---|
| The website doesn't open at all | `systemctl status shop caddy --no-pager`. Ports 80 and 443 open in the provider's firewall? The domain's A records point to `SERVER_IP`? |
| "Your connection is not private" | The domain doesn't point to the server yet, or port 80/443 is closed. `journalctl -u caddy -n 50 --no-pager`, then `systemctl reload caddy` |
| "502 Bad Gateway" | The shop isn't running: `journalctl -u shop -n 50 --no-pager` |
| Chat says "The assistant is off" | `GEMINI_API_KEY` is missing in `/home/shop/shop-bot/.env`. Add it, then `systemctl restart shop` |
| Chat says "Sorry, I couldn't answer just now" | `journalctl -u shop -n 100 --no-pager \| grep brain` shows Google's reason (wrong key, limit reached...) |
| The owner can't sign in | After 5 wrong passwords it's locked for 10 minutes (or `systemctl restart shop`). Forgotten: change `OWNER_PASSWORD` in `.env`, then `systemctl restart shop` |
| The server feels full | `df -h`. Old backups delete themselves; only the newest 14 are kept |
