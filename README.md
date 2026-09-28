# Kwork Telegram Parser

A lightweight Telegram bot that monitors Kwork public projects and sends matching offers to users based on their filters.

## What this project does

- Parses public Kwork project listings from the page data rather than relying on a broken RSS endpoint.
- Checks projects from the last 7 days.
- Filters offers by user-defined keywords.
- Stores user state locally.
- Sends only relevant matches to Telegram users.
- Keeps the Telegram bot token in macOS Keychain instead of hardcoding it in source files.

## Current status

This project is a local automation prototype for Mac. It is intentionally focused on a single goal: keep a bot running in the background and notify users about new matching Kwork projects.

## Security model

- Telegram token is stored in macOS Keychain.
- Real secrets are never committed to Git.
- Runtime files such as subscriber data and sent-project history are excluded from version control.
- Do not store tokens, chat IDs, or user data in the repository.

## Repository rules

The repository intentionally keeps only:

- source code
- dependency list
- setup instructions
- safe example files

It deliberately excludes runtime state and private data via `.gitignore`.

## Prerequisites

- macOS
- Python 3.11+
- `requests`
- access to the `security` command in Keychain
- a Telegram bot token from BotFather

## Setup

### 1) Create a virtual environment

```bash
cd /Users/ivan/Documents/MF/TG-bot
python3 -m venv .venv
source .venv/bin/activate
```

### 2) Install dependencies

```bash
pip install -r requirements.txt
```

### 3) Save the Telegram token in Keychain

```bash
security add-generic-password \
  -U \
  -a kwork-parser \
  -s kwork-parser.telegram-token \
  -w "YOUR_TELEGRAM_TOKEN"
```

### 4) Run the bot

```bash
python kwork-parser.py
```

## How it works

The bot:

1. loads the Telegram token from Keychain;
2. loads Kwork project data from the public project pages;
3. filters projects by user keywords;
4. prevents duplicate notifications by tracking sent project IDs;
5. sends matching offers to active Telegram users.

## Telegram commands

- `/start` — register the user
- `/help` — view available commands
- `/guide` — display filter instructions
- `/filter ...` — set custom keywords
- `/reset_filter` — restore default behavior
- `/status` — check current filter state
- `/stop` — pause notifications
- `/resume` — resume notifications

## Notes

- This project is designed for local execution on a Mac and can later be adapted for a background service or server deployment.
- The bot is built around the current public Kwork page structure and may need adjustments if the frontend data structure changes.
- The repository is intentionally kept minimal and safe for public hosting.
