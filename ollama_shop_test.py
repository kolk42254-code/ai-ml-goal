"""Test a local Ollama model as a dhaba's shop assistant, right on your phone (Termux) or computer.

It sends 4 test questions with the shop's rules and menu, checks every answer by itself,
and prints PASS / FAIL with the time each answer took. Uses only Python's built-in modules.

1. Start Ollama in one Termux session:      ollama serve
   (On Windows, Ollama already runs in the background: skip this step.)
2. In a second session (swipe from the left edge, NEW SESSION), or in PowerShell on Windows, run:
       python ollama_shop_test.py                      (tests qwen3.5:0.8b)
       python ollama_shop_test.py qwen3.5:4b           (tests another model)
"""
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
MODEL = sys.argv[1] if len(sys.argv) > 1 else "qwen3.5:0.8b"

RULES = """You are the AI assistant of Highway Dhaba. Follow these rules:
1. Use ONLY this menu. Never make up dishes or prices. If a dish is not on the menu, say it is not available.
2. Reply in plain text only: no markdown, no ** stars, no # headings.
3. Always reply in the language the customer writes in, including Kannada, Hindi, Tamil and Telugu.
4. (VEG) dishes are vegetarian. (NON-VEG) dishes are not. Offer only (VEG) dishes to vegetarian customers.
5. Keep replies short.

MENU:
#1 Paneer Butter Masala (VEG) Rs 210
#2 Chicken Curry (NON-VEG) Rs 240
#3 Butter Roti (VEG) Rs 20"""

# Your own instructions: edit shop_rules.txt (next to this script) and run the tests again.
# If the file isn't there, the short rules above are used.
RULES_FILE = Path(__file__).with_name("shop_rules.txt")
if RULES_FILE.exists():
    RULES = RULES_FILE.read_text(encoding="utf-8").strip()

MENU_PRICES = {20, 210, 240}
KANNADA_DIGITS = str.maketrans("೦೧೨೩೪೫೬೭೮೯", "0123456789")


def numbers(text):
    """All whole numbers in the answer (Kannada digits and 1,050-style commas count too)."""
    text = text.translate(KANNADA_DIGITS).replace(",", "")
    return {int(n) for n in re.findall(r"\d+", text)}


def has_markdown(text):
    return "**" in text or re.search(r"^\s*#", text, re.M) is not None


def check_kannada(answer):
    problems = []
    if not re.search(r"[ಀ-೿]", answer):
        problems.append("did not reply in Kannada")
    if 280 not in numbers(answer):
        problems.append("total should be 280 (240 + 2 x 20)")
    return problems


def check_not_on_menu(answer):
    problems = []
    low = answer.lower()
    if not re.search(r"\bnot\b|sorry|don't|do not|unavailable|n't have|no mutton|only", low):
        problems.append("did not say mutton biryani is not available")
    invented = numbers(answer) - MENU_PRICES - {1, 2, 3}
    if invented and ("rs" in low or "₹" in answer):
        problems.append(f"may have made up a price: {sorted(invented)}")
    return problems


def check_pure_veg(answer):
    problems = []
    low = answer.lower()
    if "paneer" not in low:
        problems.append("should suggest Paneer Butter Masala")
    if "chicken" in low and not re.search(r"chicken[^.]*\b(non-veg|not veg|not vegetarian|avoid)", low):
        problems.append("mentioned Chicken Curry to a pure-veg customer (read the answer to be sure)")
    return problems


def check_plain_total(answer):
    problems = []
    if 750 not in numbers(answer):
        problems.append("total should be 750 (3 x 210 + 6 x 20)")
    return problems


TESTS = [
    ("Kannada order total", "ಒಂದು ಚಿಕನ್ ಕರಿ ಮತ್ತು ಎರಡು ರೊಟ್ಟಿ ಬೆಲೆ ಎಷ್ಟು?", check_kannada),
    ("Dish not on the menu", "Do you have mutton biryani? How much?", check_not_on_menu),
    ("Pure veg customer", "I am pure veg. Suggest a curry.", check_pure_veg),
    ("Plain text and maths", "What is the total for 3 paneer and 6 roti?", check_plain_total),
]


USE_THINK_SETTING = True                      # turned off by itself for models without a "thinking" mode


def ask(question):
    global USE_THINK_SETTING
    payload = {
        "model": MODEL,
        "messages": [{"role": "system", "content": RULES}, {"role": "user", "content": question}],
        "stream": False,
        "options": {"temperature": 0.2},      # steadier answers for testing
    }
    if USE_THINK_SETTING:
        payload["think"] = False              # answer directly, without long hidden "thinking"
    request = urllib.request.Request(OLLAMA_URL, data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            return json.loads(response.read())["message"]["content"].strip()
    except urllib.error.HTTPError as error:
        message = error.read().decode(errors="replace")
        if USE_THINK_SETTING and "think" in message.lower():   # this model has no thinking mode: ask again without it
            USE_THINK_SETTING = False
            return ask(question)
        raise urllib.error.HTTPError(error.url, error.code, message, error.headers, None) from None


def main():
    for stream in (sys.stdout, sys.stderr):   # Windows terminals: print Kannada instead of crashing on it
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    print(f"Testing model: {MODEL}")
    print(f"Instructions: {RULES_FILE.name if RULES_FILE.exists() else 'built-in short rules'}\n")
    passed = 0
    for number, (name, question, check) in enumerate(TESTS, 1):
        print(f"--- Test {number}: {name}")
        print(f"Customer: {question}")
        start = time.time()
        try:
            answer = ask(question)
        except urllib.error.HTTPError as error:
            sys.exit(f"Ollama said: {error.msg}\n"
                     f"Is the model downloaded? Try: ollama pull {MODEL}")
        except (urllib.error.URLError, ConnectionError, TimeoutError) as error:
            sys.exit(f"Can't reach Ollama ({error}). Start it first in another session: ollama serve")
        seconds = time.time() - start
        print(f"Model ({seconds:.1f} s): {answer}")
        problems = check(answer)
        if has_markdown(answer):
            problems.append("used markdown (** or #), which the rules forbid")
        if problems:
            print("FAIL: " + "; ".join(problems))
        else:
            passed += 1
            print("PASS")
        print()
    print(f"Result: {passed} of {len(TESTS)} passed for {MODEL}")
    if passed < len(TESTS):
        print("Read the FAIL lines above. A bigger model (like qwen3.5:4b) usually does better.")


if __name__ == "__main__":
    main()
