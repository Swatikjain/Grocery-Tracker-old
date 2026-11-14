# Grocery Tracker

A mobile-first receipt tracker built with FastAPI, SQLite/SQLAlchemy, and the official Google Gen AI Python SDK. Receipt photos are processed in memory and are not saved unless image storage is deliberately enabled.

## Project structure

```text
.
├── main.py             # FastAPI app and API routes
├── database.py         # SQLite/SQLAlchemy setup
├── models.py           # Receipt and item tables
├── schemas.py          # API validation schemas
├── receipt_reader.py   # Image resizing and Gemini structured extraction
├── static/             # Plain HTML, CSS, and JavaScript frontend
├── tests/
├── .env.example
└── requirements.txt
```

## Database schema

- `receipts`: `id`, `store_name`, `purchase_date`, `total_amount`, and `created_at`.
- `items`: `id`, `receipt_id` (foreign key), `name`, `quantity`, `unit_price`, and `total_price`.
- An optional `image_data` column on receipts is used only when image storage is enabled. It is empty by default.

## Setup

Requires Python 3.11 or newer.

1. Create and activate a virtual environment:

   ```sh
   python3.11 -m venv .venv
   source .venv/bin/activate
   ```

2. Install dependencies:

   ```sh
   pip install -r requirements.txt
   ```

3. Create a Gemini API key:

   - Open [Google AI Studio](https://aistudio.google.com/).
   - Sign in with your Google account and choose **Get API key**.
   - Create a key (the free tier is subject to Google's availability and rate limits).

4. Configure the app:

   ```sh
   cp .env.example .env
   ```

   Put the key in `.env` as `GEMINI_API_KEY`. `GEMINI_MODEL` defaults to `gemini-2.5-flash`; change it there if needed. Keep `.env` private.

5. Start the server:

   ```sh
   uvicorn main:app --reload
   ```

   Open [http://127.0.0.1:8000](http://127.0.0.1:8000) on your computer or phone. For phone access, the phone and computer should share a network; run Uvicorn with `--host 0.0.0.0` and visit the computer's local IP.

## Using the app

Choose **Scan receipt** to open the camera on supported phones or select an image. Check and edit the extracted store, date, items, and prices, then save. A missing date defaults to today and is flagged for confirmation. History is sorted by purchase date, and the Items page supports search and a monthly receipt-spending total.

Use the **Keep receipt image** checkbox on the home screen to opt in to retaining the original photo for that scan. The server must also be configured with `STORE_RECEIPT_IMAGES=true` in `.env`; image retention is off unless explicitly enabled. Restart the server after changing `.env`.

The app sends a resized copy (maximum 1600 pixels per side) to Gemini. If the free-tier limit is reached, it shows a retry option and a friendly wait-a-minute message.

## Tests

```sh
pytest
```
