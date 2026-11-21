# Run the shop on an Android phone (Termux)

Use Termux from F-Droid or GitHub. The old Play Store version can't install packages any more.

## Once: set it up

1. Install Python and the tools:
   ```
   pkg update && pkg upgrade -y
   ```
   ```
   pkg install -y python python-pip python-cryptography unzip
   ```
   (Don't run `pip install --upgrade pip` in Termux. Termux blocks it, because pip comes from `pkg`.)

2. Let Termux open your Downloads folder, then tap **Allow**:
   ```
   termux-setup-storage
   ```

3. Unpack the shop into Termux's own home folder:
   ```
   cd ~ && unzip -o ~/storage/downloads/shop-bot.zip && cd ~/shop-bot
   ```
   Keep it in the home folder, not in Downloads: the shop's database file doesn't work reliably on shared phone storage.
   If the download got another name (like `shop-bot (1).zip`), see the name with `ls ~/storage/downloads`.

4. Install the shop's libraries. The extra address gives ready-made Android builds of `pydantic-core`,
   so nothing heavy has to be compiled on the phone (it needs Python 3.13 or 3.14; check with `python --version`):
   ```
   python -m pip install --extra-index-url https://termux-user-repository.github.io/pypi/ "pydantic==2.12.5" -r requirements.txt
   ```
   If it stops while building something (like `cffi` or `websockets`), install the build tools and run step 4 again:
   ```
   pkg install -y clang make libffi openssl
   ```

5. Set the owner password (and your Gemini key, if you want the chat assistant to answer):
   ```
   echo "OWNER_PASSWORD=choose-a-long-password" > .env
   ```
   ```
   echo "GEMINI_API_KEY=your-key" >> .env
   ```

## Every time: run it

```
cd ~/shop-bot
```
```
python -m pytest -q
```
You should see `81 passed`. Then start the shop:
```
termux-wake-lock
```
```
python -m uvicorn app:app --port 8000
```
Open **http://127.0.0.1:8000** in Chrome on the same phone. The owner desk is **http://127.0.0.1:8000/owner**.

- `termux-wake-lock` stops Android from pausing Termux when the screen turns off. `termux-wake-unlock` undoes it.
- Stop the shop with **Ctrl + C** (on the Termux keyboard row: tap CTRL, then C).
- The first start creates `shop.db` with 12 sample items. To start again from the sample shop, stop it and run `rm shop.db`.
- A phone is fine for testing. Real customers need the shop on a cloud server that stays on (see README.md).
