"""Pretend to be Meta: send one fake WhatsApp message to YOUR bot on this laptop.
Useful before the Meta app is published. The bot's reply goes to your real WhatsApp.

Run (bot server must be running):
    python fake_whatsapp_message.py 91XXXXXXXXXX "Price of 1 kg red velvet cake?"
The first value is your WhatsApp number with country code (no + or spaces)."""
import sys
import time

import requests

if len(sys.argv) < 3:
    raise SystemExit('Usage: python fake_whatsapp_message.py 91XXXXXXXXXX "your message"')

phone, text = sys.argv[1], " ".join(sys.argv[2:])
payload = {"object": "whatsapp_business_account", "entry": [{"id": "test", "changes": [{
    "field": "messages",
    "value": {
        "messaging_product": "whatsapp",
        "metadata": {"display_phone_number": "test", "phone_number_id": "test"},
        "contacts": [{"profile": {"name": "Test customer"}, "wa_id": phone}],
        "messages": [{"from": phone, "id": f"wamid.fake{time.time_ns()}",   # new ID every time
                      "timestamp": str(int(time.time())), "type": "text", "text": {"body": text}}],
    }}]}]}

response = requests.post("http://localhost:8000/whatsapp", json=payload, timeout=10)
print("Bot server said:", response.status_code, response.text)
print("Now check WhatsApp on your phone for the reply (and Terminal 1 for any [send] error).")
