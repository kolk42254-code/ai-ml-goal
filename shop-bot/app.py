"""The web server for the AI shop.
    Customer shop:   http://localhost:8000/
    Owner page:      http://localhost:8000/owner   (needs OWNER_PASSWORD in .env)
    WhatsApp/Instagram webhooks (paused for now): /whatsapp and /instagram
Start it with:  python -m uvicorn app:app --port 8000"""
import base64
import binascii
import hmac
import json
import re
import secrets
import threading
import time
import uuid
from collections import deque
from datetime import timedelta
from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import config
import database
import platforms
from brain import ShopBrain

STATIC_DIR = config.BASE_DIR / "static"
config.UPLOADS_DIR.mkdir(exist_ok=True)

app = FastAPI(title="AI shop", docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/uploads", StaticFiles(directory=config.UPLOADS_DIR), name="uploads")

brain = None                    # the AI brain is created when the first chat message arrives
brain_lock = threading.Lock()
seen_ids = deque(maxlen=1000)   # Meta may send the same WhatsApp message twice, so we remember recent IDs
TEXT_ONLY = "Sorry, I can only read text messages for now. Please type your question 🙂"

if not config.OWNER_PASSWORD:
    print("[setup] OWNER_PASSWORD is empty in .env, so the owner page is locked. Add one to use /owner.")


@app.middleware("http")
async def safety_headers(request, call_next):
    """Extra browser protection: only our own scripts may run on our pages."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' data: blob:; style-src 'self'; script-src 'self'; "
        "font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
    return response


def get_brain():
    global brain
    with brain_lock:
        if brain is None:
            brain = ShopBrain()
        return brain


def client_ip(request):
    return request.client.host if request.client else "unknown"


_hits = {}


def allowed(key, limit, seconds):
    """Simple speed limit: at most `limit` requests per `seconds` for one key (a device or a chat)."""
    now = time.monotonic()
    if len(_hits) > 10_000:                  # forget devices that have been quiet for an hour
        for old in [k for k, v in _hits.items() if not v or now - v[-1] > 3600]:
            del _hits[old]
    hits = _hits.setdefault(key, deque())
    while hits and now - hits[0] > seconds:
        hits.popleft()
    if len(hits) >= limit:
        return False
    hits.append(now)
    return True


# ===================== Pages =====================

@app.get("/", include_in_schema=False)
def shop_page():
    return FileResponse(STATIC_DIR / "shop.html")


@app.get("/owner", include_in_schema=False)
def owner_page():
    return FileResponse(STATIC_DIR / "owner.html")


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    """The little cupcake icon in the browser tab."""
    return FileResponse(STATIC_DIR / "favicon.svg", media_type="image/svg+xml")


@app.get("/health")
def health():
    return {"status": "Shop chatbot is running"}


# ===================== Customer API =====================

def public_shop(settings):
    keys = ("shop_name", "tagline", "phone", "address", "open_time", "close_time", "closed_days",
            "delivery_fee", "free_delivery_above", "delivery_area")
    return {key: settings[key] for key in keys}


@app.get("/api/shop")
def shop_data():
    """Everything the customer page shows: shop details, open/closed, the live menu and the server time."""
    settings = database.get_settings()
    at = database.now()
    return {"shop": public_shop(settings), "status": database.shop_status(settings, at),
            "products": database.list_products(at=at), "server_now": at.isoformat(timespec="seconds")}


class CartItem(BaseModel):
    product_id: int
    quantity: int = Field(ge=1, le=database.MAX_QUANTITY)


class OrderIn(BaseModel):
    customer_name: str = Field(max_length=60)
    phone: str = Field(max_length=20)
    fulfilment: str = Field(max_length=10)
    address: str = Field(default="", max_length=200)
    wanted_at: str = Field(default="", max_length=60)
    notes: str = Field(default="", max_length=300)
    items: list[CartItem] = Field(max_length=30)


@app.post("/api/orders")
def create_order(data: OrderIn, request: Request):
    """Checkout from the cart."""
    if not allowed(f"order:{client_ip(request)}", 10, 600):
        raise HTTPException(429, "Too many orders from this device. Please call the shop.")
    try:
        order = database.place_order("cart", data.customer_name, data.phone, data.fulfilment, data.address,
                                     data.wanted_at, data.notes, [(i.product_id, i.quantity) for i in data.items])
    except database.OrderError as problem:
        raise HTTPException(400, str(problem)) from None
    return {"order": order}


class ChatIn(BaseModel):
    chat_id: str = Field(pattern=r"^[A-Za-z0-9_-]{8,64}$")
    message: str = Field(min_length=1, max_length=500)


@app.post("/api/chat")
def chat(data: ChatIn, request: Request):
    """One message to the AI assistant. It may also place an order."""
    if not (allowed(f"chat-ip:{client_ip(request)}", 40, 300) and allowed(f"chat:{data.chat_id}", 20, 300)):
        raise HTTPException(429, "You're sending messages very fast. Please wait a minute.")
    try:
        bot = get_brain()
    except RuntimeError as error:            # for example, GEMINI_API_KEY is missing
        print(f"[bot] {error}")
        raise HTTPException(503, "The assistant is off right now. You can still order with the cart.") from None
    answer, orders = bot.chat("web", data.chat_id, data.message.strip())
    return {"reply": answer, "orders": orders}


# ===================== Owner sign-in =====================

SESSION_LIFETIME = timedelta(hours=12)
owner_sessions = {}             # secret session token -> when it expires
login_failures = {}             # device -> times of wrong passwords


def owner_signed_in(request):
    token = request.cookies.get("owner_session", "")
    expires = owner_sessions.get(token)
    if expires is None or expires < database.now():
        owner_sessions.pop(token, None)
        return False
    return True


def require_owner(request: Request):
    if not owner_signed_in(request):
        raise HTTPException(401, "Please sign in again.")


class LoginIn(BaseModel):
    password: str = Field(max_length=200)


@app.get("/api/owner/me")
def owner_me(request: Request):
    return {"signed_in": owner_signed_in(request), "password_set": bool(config.OWNER_PASSWORD)}


@app.post("/api/owner/login")
def owner_login(data: LoginIn, request: Request, response: Response):
    if not config.OWNER_PASSWORD:
        raise HTTPException(503, "Owner sign-in is off. Add OWNER_PASSWORD to the .env file and restart the server.")
    failures = login_failures.setdefault(client_ip(request), deque())
    now = time.monotonic()
    while failures and now - failures[0] > 600:
        failures.popleft()
    if len(failures) >= 5:
        raise HTTPException(429, "Too many wrong passwords. Wait 10 minutes, then try again.")
    if not hmac.compare_digest(data.password.encode(), config.OWNER_PASSWORD.encode()):
        failures.append(now)
        left = 5 - len(failures)
        raise HTTPException(401, f"Wrong password. {left} {'try' if left == 1 else 'tries'} left." if left
                            else "Too many wrong passwords. Wait 10 minutes, then try again.")
    failures.clear()
    token = secrets.token_urlsafe(32)
    owner_sessions[token] = database.now() + SESSION_LIFETIME
    response.set_cookie("owner_session", token, max_age=int(SESSION_LIFETIME.total_seconds()), httponly=True,
                        samesite="strict", secure=request.url.scheme == "https", path="/")
    return {"ok": True}


@app.post("/api/owner/logout")
def owner_logout(request: Request, response: Response):
    owner_sessions.pop(request.cookies.get("owner_session", ""), None)
    response.delete_cookie("owner_session", path="/")
    return {"ok": True}


# ===================== Owner API (sign-in needed) =====================

owner_only = [Depends(require_owner)]


def not_found(what="That item"):
    return HTTPException(404, f"{what} doesn't exist any more. Refresh the page.")


@app.get("/api/owner/orders", dependencies=owner_only)
def owner_orders():
    at = database.now()
    return {"orders": database.list_orders(), "stats": database.order_stats(at),
            "server_now": at.isoformat(timespec="seconds")}


class StatusIn(BaseModel):
    status: str = Field(max_length=20)


@app.post("/api/owner/orders/{order_id}/status", dependencies=owner_only)
def owner_set_status(order_id: int, data: StatusIn):
    try:
        return {"order": database.update_order_status(order_id, data.status)}
    except KeyError:
        raise not_found("That order") from None
    except ValueError as problem:           # OrderError is a kind of ValueError
        raise HTTPException(400, str(problem)) from None


@app.get("/api/owner/products", dependencies=owner_only)
def owner_products():
    at = database.now()
    return {"products": database.list_products(include_hidden=True, at=at),
            "server_now": at.isoformat(timespec="seconds")}


class ProductIn(BaseModel):
    name: str = Field(max_length=60)
    category: str = Field(max_length=30)
    description: str = Field(default="", max_length=160)
    emoji: str = Field(default="🧁", max_length=8)
    price: int
    stock: int = 0
    visible: bool = True


class ProductPatch(BaseModel):
    name: str | None = Field(default=None, max_length=60)
    category: str | None = Field(default=None, max_length=30)
    description: str | None = Field(default=None, max_length=160)
    emoji: str | None = Field(default=None, max_length=8)
    price: int | None = None
    stock: int | None = None
    visible: bool | None = None


@app.post("/api/owner/products", dependencies=owner_only)
def owner_add_product(data: ProductIn):
    try:
        return {"product": database.create_product(data.model_dump())}
    except ValueError as problem:
        raise HTTPException(400, str(problem)) from None


@app.patch("/api/owner/products/{product_id}", dependencies=owner_only)
def owner_edit_product(product_id: int, data: ProductPatch):
    try:
        return {"product": database.update_product(product_id, data.model_dump(exclude_none=True))}
    except KeyError:
        raise not_found() from None
    except ValueError as problem:
        raise HTTPException(400, str(problem)) from None


@app.delete("/api/owner/products/{product_id}", dependencies=owner_only)
def owner_delete_product(product_id: int):
    try:
        remove_photo_file(database.delete_product(product_id))
    except KeyError:
        raise not_found() from None
    return {"ok": True}


class OfferIn(BaseModel):
    offer_price: int
    preset: str = Field(default="closing", pattern=r"^(1h|3h|closing|midnight|custom)$")
    ends_at: str = Field(default="", max_length=40)


@app.put("/api/owner/products/{product_id}/offer", dependencies=owner_only)
def owner_start_offer(product_id: int, data: OfferIn):
    try:
        return {"product": database.set_offer(product_id, data.offer_price, data.preset, data.ends_at)}
    except KeyError:
        raise not_found() from None
    except ValueError as problem:
        raise HTTPException(400, str(problem)) from None


@app.delete("/api/owner/products/{product_id}/offer", dependencies=owner_only)
def owner_end_offer(product_id: int):
    try:
        return {"product": database.end_offer(product_id)}
    except KeyError:
        raise not_found() from None


class PhotoIn(BaseModel):
    image: str = Field(max_length=4_000_000)     # a photo sent as a "data:image/...;base64," text


PHOTO_TYPES = {"jpeg": b"\xff\xd8\xff", "png": b"\x89PNG\r\n\x1a\n", "webp": b"RIFF"}


def remove_photo_file(image_path):
    if image_path and image_path.startswith("/uploads/"):
        (config.UPLOADS_DIR / Path(image_path).name).unlink(missing_ok=True)


@app.put("/api/owner/products/{product_id}/photo", dependencies=owner_only)
def owner_set_photo(product_id: int, data: PhotoIn):
    match = re.fullmatch(r"data:image/(jpeg|png|webp);base64,([A-Za-z0-9+/=]+)", data.image)
    if not match:
        raise HTTPException(400, "Choose a JPG, PNG or WEBP photo.")
    kind = match.group(1)
    try:
        raw = base64.b64decode(match.group(2), validate=True)
    except binascii.Error:
        raise HTTPException(400, "That photo couldn't be read. Try another one.") from None
    if len(raw) > 2_500_000:
        raise HTTPException(400, "That photo is too big. Choose one under 2.5 MB.")
    if not raw.startswith(PHOTO_TYPES[kind]) or (kind == "webp" and raw[8:12] != b"WEBP"):
        raise HTTPException(400, "That file isn't a real photo.")
    name = f"{uuid.uuid4().hex}.{'jpg' if kind == 'jpeg' else kind}"
    (config.UPLOADS_DIR / name).write_bytes(raw)
    try:
        remove_photo_file(database.set_product_image(product_id, f"/uploads/{name}"))
    except KeyError:
        (config.UPLOADS_DIR / name).unlink(missing_ok=True)
        raise not_found() from None
    return {"product": database.get_product(product_id)}


@app.delete("/api/owner/products/{product_id}/photo", dependencies=owner_only)
def owner_remove_photo(product_id: int):
    try:
        remove_photo_file(database.set_product_image(product_id, ""))
    except KeyError:
        raise not_found() from None
    return {"product": database.get_product(product_id)}


class SettingsIn(BaseModel):
    shop_name: str | None = Field(default=None, max_length=60)
    tagline: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, max_length=20)
    address: str | None = Field(default=None, max_length=160)
    open_time: str | None = Field(default=None, max_length=5)
    close_time: str | None = Field(default=None, max_length=5)
    closed_days: list[str] | None = Field(default=None, max_length=7)
    delivery_fee: int | None = None
    free_delivery_above: int | None = None
    delivery_area: str | None = Field(default=None, max_length=200)
    assistant_notes: str | None = Field(default=None, max_length=1500)


@app.get("/api/owner/settings", dependencies=owner_only)
def owner_settings():
    return {"settings": database.get_settings()}


@app.put("/api/owner/settings", dependencies=owner_only)
def owner_save_settings(data: SettingsIn):
    try:
        return {"settings": database.update_settings(data.model_dump(exclude_none=True))}
    except ValueError as problem:
        raise HTTPException(400, str(problem)) from None


# ===================== WhatsApp and Instagram (paused for now) =====================

@app.get("/whatsapp")
@app.get("/instagram")
def verify_webhook(request: Request):
    """Meta calls this once when you save the webhook URL, to check the server is yours."""
    params = request.query_params
    if (config.VERIFY_TOKEN
            and params.get("hub.mode") == "subscribe"
            and params.get("hub.verify_token") == config.VERIFY_TOKEN):
        return PlainTextResponse(params.get("hub.challenge", ""))
    return Response(status_code=403)


@app.post("/whatsapp")
async def whatsapp_webhook(request: Request, background: BackgroundTasks):
    return await receive(request, background, "whatsapp", platforms.read_whatsapp, config.WHATSAPP_APP_SECRET)


@app.post("/instagram")
async def instagram_webhook(request: Request, background: BackgroundTasks):
    return await receive(request, background, "instagram", platforms.read_instagram, config.INSTAGRAM_APP_SECRET)


async def receive(request, background, platform, reader, secret):
    """Check the message really came from Meta, then answer it in the background.
    Meta wants a quick "OK", so the slow AI part runs after we say OK."""
    raw = await request.body()
    if not platforms.signature_is_valid(raw, request.headers.get("X-Hub-Signature-256", ""), secret):
        return Response(status_code=401)
    try:
        payload = json.loads(raw)
    except ValueError:
        return Response(status_code=400)
    if not isinstance(payload, dict):
        return Response(status_code=400)
    for msg in reader(payload):
        if msg["id"] in seen_ids:
            continue                        # already answered this exact message
        seen_ids.append(msg["id"])
        background.add_task(answer, platform, msg)
    return {"ok": True}


def answer(platform, msg):
    """Runs after Meta got its OK: ask the brain, then send the reply on the same app."""
    if msg["text"]:
        try:
            reply = get_brain().reply(platform, msg["user_id"], msg["text"], msg["name"])
        except RuntimeError as error:       # for example, GEMINI_API_KEY is missing
            print(f"[bot] {error}")
            return
    else:
        reply = TEXT_ONLY                   # photo, voice note, sticker...
    send = platforms.send_whatsapp if platform == "whatsapp" else platforms.send_instagram
    send(msg["user_id"], reply)
