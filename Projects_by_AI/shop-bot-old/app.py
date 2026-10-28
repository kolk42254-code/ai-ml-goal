"""The web server. Meta sends every new WhatsApp and Instagram message here (this is a "webhook").
Start it with:  uvicorn app:app --port 8000"""
import json
from collections import deque

from fastapi import BackgroundTasks, FastAPI, Request, Response
from fastapi.responses import PlainTextResponse

import config
import platforms
from brain import ShopBrain

app = FastAPI(title="Shop chatbot")
brain = None                    # the AI brain is created when the first message arrives
seen_ids = deque(maxlen=1000)   # Meta may send the same message twice, so we remember recent IDs
TEXT_ONLY = "Sorry, I can only read text messages for now. Please type your question 🙂"

if not config.VERIFY_TOKEN:
    print("[setup] VERIFY_TOKEN is empty in .env, so Meta can't verify your webhook yet.")
if not (config.WHATSAPP_APP_SECRET and config.INSTAGRAM_APP_SECRET):
    print("[setup] An app secret is empty, so some webhook signatures are NOT checked. OK only for testing.")


@app.get("/")
def home():
    return {"status": "Shop chatbot is running"}


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
    global brain
    if msg["text"]:
        try:
            if brain is None:
                brain = ShopBrain()
            reply = brain.reply(platform, msg["user_id"], msg["text"], msg["name"])
        except RuntimeError as error:       # for example, GEMINI_API_KEY is missing
            print(f"[bot] {error}")
            return
    else:
        reply = TEXT_ONLY                   # photo, voice note, sticker...
    send = platforms.send_whatsapp if platform == "whatsapp" else platforms.send_instagram
    send(msg["user_id"], reply)
