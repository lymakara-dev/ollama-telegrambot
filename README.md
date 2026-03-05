# Ollama Telegram Bot Backend

A FastAPI backend that connects Telegram Bot API updates to a local Ollama instance.

## Features

- Receives Telegram updates via webhook.
- Handles text, voice, image, audio, and document uploads.
- Sends LLM text reply from local Ollama.
- Responds with the same media type where possible (echoes back media using Telegram `file_id`).

## Setup

1. Install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Configure env vars:

```bash
cp .env.example .env
```

3. Run Ollama locally and pull a model:

```bash
ollama serve
ollama pull llama3.1
```

4. Run server:

```bash
uvicorn app:app --host 0.0.0.0 --port 8000
```

## Telegram webhook

Expose your local server using ngrok or cloudflared then register webhook:

```bash
curl -X POST "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://<YOUR_PUBLIC_URL>/telegram/webhook",
    "secret_token": "'$TELEGRAM_WEBHOOK_SECRET'"
  }'
```

## Health check

```bash
curl http://127.0.0.1:8000/health
```
