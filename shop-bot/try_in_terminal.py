"""Chat with the shop bot right here in your terminal. Only GEMINI_API_KEY is needed in .env.
Run:  python try_in_terminal.py"""
from brain import ShopBrain

try:
    bot = ShopBrain()
except RuntimeError as error:
    raise SystemExit(error)

print("You are now a customer of the shop. Type a message and press Enter. Type 'quit' to stop.\n")
while True:
    text = input("You: ").strip()
    if text.lower() in ("quit", "exit"):
        break
    if text:
        print("Bot:", bot.reply("terminal", "me", text), "\n")
