"""Reads every setting from the .env file, so secret keys never sit inside the code."""
import os
from datetime import timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent        # the shop-bot folder
load_dotenv(BASE_DIR / ".env")          # copies the values in .env into the environment

# ---- AI (Google Gemini) ----
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")

# ---- Webhook safety ----
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "")                 # your own secret word, also typed into Meta
WHATSAPP_APP_SECRET = os.getenv("WHATSAPP_APP_SECRET", "")   # App settings > Basic > App secret
INSTAGRAM_APP_SECRET = os.getenv("INSTAGRAM_APP_SECRET", "")

# ---- WhatsApp Cloud API ----
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")

# ---- Instagram API with Instagram Login ----
INSTAGRAM_TOKEN = os.getenv("INSTAGRAM_TOKEN", "")

# ---- Other ----
GRAPH_API_VERSION = os.getenv("GRAPH_API_VERSION", "v26.0")
SHOP_INFO_FILE = BASE_DIR / os.getenv("SHOP_INFO_FILE", "shop_info.txt")
ORDERS_FILE = BASE_DIR / os.getenv("ORDERS_FILE", "orders.csv")
SHOP_TIMEZONE = timezone(timedelta(hours=5, minutes=30))     # India time (IST has no daylight saving)
