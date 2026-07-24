# MnlicksTrade Bot

A Telegram subscription bot for **MnlicksGang | TRADE** — a paid community for EA Sports FC coin trading tips and signals. It handles the full member lifecycle: onboarding, plan selection, payment, access provisioning, and expiry — with no manual admin work required.

## What it does

- **Onboarding** — `/start` greets new users with a welcome message and photo, editable live by admins without touching code.
- **Plan selection & payment** — offers a Standard and an Ultimate subscription tier, each payable by card (via a Telegram deep link to the operator) or USDT (TRC-20) through [aiosend](https://github.com/aiosend/aiosend)'s CryptoBot integration, with live invoice polling.
- **Access management** — on successful payment, the bot generates a single-use, time-limited invite link to the private community chat and records the subscription (plan, expiry, invite link) in SQLite.
- **Automatic expiry** — a background task periodically scans for expired subscriptions, bans and unbans the member (removing them from the chat while leaving the door open to rejoin later), and notifies them with a renewal prompt.
- **Member reviews carousel** — a "Reviews" button opens a native, swipeable Telegram slideshow (Bot API 10.2 Rich Messages) built from a folder of review screenshots, letterboxed to fit the slideshow's portrait frame without cropping.
- **Chat hygiene** — automatically deletes Telegram's service messages (join/leave/pin/etc.) in the community chat to keep it clean.
- **Admin tools**:
  - `/grant <user_id> <plan>` — manually grant access to a user (e.g. for support cases or off-platform payments).
  - `/setwelcome <text>` — update the welcome message's text (HTML formatting supported) on the fly, persisted in the database.
  - `/getid` — resolve a chat's ID, usable in both DMs and channel posts.

## Stack

- [aiogram 3](https://github.com/aiogram/aiogram) — async Telegram Bot API framework, including its Rich Messages support for the review slideshow.
- [aiosend](https://github.com/aiosend/aiosend) — crypto invoicing and payment polling via CryptoBot.
- SQLite — subscriptions and runtime settings (e.g. welcome text), no external database required.
