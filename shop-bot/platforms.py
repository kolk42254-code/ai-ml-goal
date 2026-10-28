"""WhatsApp and Instagram: reading the messages Meta sends us, and sending replies back."""
import hashlib
import hmac
import textwrap

import requests

import config

WHATSAPP_MAX_BYTES = 4096     # we split anything longer into parts (bot replies are short anyway)
INSTAGRAM_MAX_BYTES = 1000    # Instagram allows at most 1000 bytes of text in one message


def signature_is_valid(raw_body: bytes, signature_header: str, secret: str) -> bool:
    """Meta signs every webhook with your App Secret. A wrong signature means it's not from Meta."""
    if not secret:
        return True                  # no secret set yet (early testing), so we can't check
    expected = "sha256=" + hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header or "")


def read_whatsapp(payload: dict) -> list[dict]:
    """Pick out customer messages from a WhatsApp webhook. Status updates (sent, read) are skipped."""
    messages = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            names = {c.get("wa_id"): c.get("profile", {}).get("name", "") for c in value.get("contacts", [])}
            for msg in value.get("messages", []):
                messages.append({
                    "id": msg.get("id"),
                    "user_id": msg.get("from"),
                    "name": names.get(msg.get("from"), ""),
                    "text": msg.get("text", {}).get("body", "") if msg.get("type") == "text" else "",
                })
    return messages


def read_instagram(payload: dict) -> list[dict]:
    """Pick out customer DMs from an Instagram webhook. Echoes of our own replies are skipped."""
    messages = []
    for entry in payload.get("entry", []):
        for event in entry.get("messaging", []):
            msg = event.get("message")
            if not msg or msg.get("is_echo"):
                continue             # a reaction, a "seen" receipt, or a message WE sent
            messages.append({
                "id": msg.get("mid"),
                "user_id": event.get("sender", {}).get("id"),
                "name": "",
                "text": msg.get("text", ""),
            })
    return messages


def split_message(text: str, max_bytes: int) -> list[str]:
    """Cut a long reply into parts that fit the app's size limit."""
    if len(text.encode("utf-8")) <= max_bytes:
        return [text]
    # one character uses at most 4 bytes, so parts of (max_bytes // 4) characters always fit
    return textwrap.wrap(text, width=max_bytes // 4, replace_whitespace=False)


def send_whatsapp(to: str, text: str) -> None:
    url = f"https://graph.facebook.com/{config.GRAPH_API_VERSION}/{config.WHATSAPP_PHONE_NUMBER_ID}/messages"
    for part in split_message(text, WHATSAPP_MAX_BYTES):
        _post(url, config.WHATSAPP_TOKEN, {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "text",
            "text": {"body": part},
        })


def send_instagram(to: str, text: str) -> None:
    url = f"https://graph.instagram.com/{config.GRAPH_API_VERSION}/me/messages"
    for part in split_message(text, INSTAGRAM_MAX_BYTES):
        _post(url, config.INSTAGRAM_TOKEN, {"recipient": {"id": to}, "message": {"text": part}})


def _post(url: str, token: str, body: dict) -> None:
    """Send one message to Meta, and print the reason if Meta refuses it."""
    try:
        response = requests.post(url, json=body, headers={"Authorization": f"Bearer {token}"}, timeout=15)
    except requests.RequestException as error:
        print(f"[send] Could not reach Meta: {error}")
        return
    if not response.ok:
        print(f"[send] Meta said {response.status_code}: {response.text[:300]}")
