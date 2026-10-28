"""Run this once after you put INSTAGRAM_TOKEN in .env (Step 5 in the README).
It shows which Instagram account the token belongs to, and turns on DM webhooks for it.
Run:  python connect_instagram.py"""
import requests

import config


def main():
    if not config.INSTAGRAM_TOKEN:
        raise SystemExit("INSTAGRAM_TOKEN is missing. Put it in your .env file first.")
    base = f"https://graph.instagram.com/{config.GRAPH_API_VERSION}"
    token = {"access_token": config.INSTAGRAM_TOKEN}

    me = requests.get(f"{base}/me", params={"fields": "user_id,username", **token}, timeout=15).json()
    if "error" in me:
        raise SystemExit(f"Meta said: {me['error'].get('message')}")
    account = me["data"][0] if "data" in me else me          # works with both reply shapes
    print(f"Token belongs to @{account.get('username')} (account ID {account.get('user_id')})")

    result = requests.post(f"{base}/{account['user_id']}/subscribed_apps",
                           params={"subscribed_fields": "messages", **token}, timeout=15).json()
    if result.get("success"):
        print("Done! Instagram will now send this account's DMs to your server.")
    else:
        print(f"Meta said: {result}")


if __name__ == "__main__":
    main()
