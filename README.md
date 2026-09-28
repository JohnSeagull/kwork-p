# Kwork Telegram Parser

This project monitors public Kwork projects and sends matching offers to Telegram users.

## Security

- Telegram token is kept in macOS Keychain.
- Do not commit real secrets.
- Keep local runtime data such as `subscribers.json` and `seen_tasks.txt` out of Git.

## Local setup

1. Create a virtual environment:
   python3 -m venv .venv
   source .venv/bin/activate
2. Install dependencies:
   pip install -r requirements.txt
3. Create the bot token in Keychain:
   security add-generic-password -U -a kwork-parser -s kwork-parser.telegram-token -w "YOUR_TELEGRAM_TOKEN"
4. Run the bot:
   python kwork-parser.py

## Keychain access

The script reads the Telegram token from Keychain using the service name:

- kwork-parser.telegram-token

## Git

This repository intentionally excludes local runtime data and secrets via `.gitignore`.

## Notes

- The project is designed for local development and background execution on a Mac.
- A real public GitHub repository should only contain code, not tokens or runtime data.
