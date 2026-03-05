# Ollama Telegram Bot Backend

A FastAPI backend that connects Telegram Bot API updates to a local Ollama instance.

## Features

- Receives Telegram updates via webhook.
- Handles text, voice, image, audio, and document uploads.
- Performs content extraction for supported text documents and vision analysis for images.
- Supports basic tool/function calling (calculator + UTC time).
- Streams long replies with typing indicator and progressive message edits.
- Maintains per-chat conversation memory for contextual replies.
- Adds local RAG retrieval from `knowledge_base.md`.
- Adds safety controls: blocked-term moderation, prompt truncation, and per-chat rate limiting.
- Adds background queued processing for webhook reliability.
- Adds observability metrics and admin stats APIs.
- Adds model routing (fast/reasoning/vision) by request shape.

## Project structure

```text
.
├── app.py                  # compatibility entrypoint (`from bot.main import app`)
├── bot/
│   ├── config.py           # environment configuration
│   ├── jobs.py             # async queue worker
│   ├── main.py             # FastAPI routes + startup/shutdown
│   ├── memory.py           # per-chat in-memory history
│   ├── metrics.py          # in-process counters
│   ├── ollama_client.py    # Ollama API client
│   ├── rag.py              # local knowledge retrieval logic
│   ├── router.py           # model routing strategy
│   ├── safety.py           # moderation + rate limiting
│   ├── service.py          # core orchestration logic
│   ├── telegram_client.py  # Telegram API client
│   └── tools.py            # tool-calling definitions + execution
└── knowledge_base.md       # editable RAG source document
```

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

# Core
OLLAMA_MODEL=llama3.1
OLLAMA_VISION_MODEL=llava
OLLAMA_FAST_MODEL=llama3.1
OLLAMA_REASONING_MODEL=llama3.1
LONG_PROMPT_THRESHOLD=800

# Context / RAG
CHAT_MEMORY_TURNS=12
MAX_TEXT_EXTRACT_CHARS=4000
MAX_PROMPT_CHARS=6000
KNOWLEDGE_BASE_PATH=knowledge_base.md
RAG_TOP_K=3
RAG_CHUNK_SIZE=700

# UX
STREAM_CHUNK_CHARS=320

# Safety / abuse
BLOCKED_TERMS=
RATE_LIMIT_COUNT=12
RATE_LIMIT_WINDOW_SECONDS=60

# Admin
ADMIN_CHAT_IDS=
ADMIN_API_TOKEN=
```

3. Run Ollama locally and pull models:

```bash
ollama serve
ollama pull llama3.1
# if using vision routing:
ollama pull llava
```

4. Run server:

```bash
uvicorn app:app --host 0.0.0.0 --port 8000
```

## Endpoints

- `POST /telegram/webhook` enqueue incoming update for background processing.
- `GET /health` service + queue size.
- `POST /rag/reload` reloads `knowledge_base.md` chunks.
- `GET /admin/stats` returns in-process metrics (requires `X-Admin-Token`).

## RAG usage

1. Edit `knowledge_base.md` with your domain content.
2. Reload knowledge chunks:

```bash
curl -X POST http://127.0.0.1:8000/rag/reload
```

## Telegram webhook

```bash
curl -X POST "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://<YOUR_PUBLIC_URL>/telegram/webhook",
    "secret_token": "'$TELEGRAM_WEBHOOK_SECRET'"
  }'
```
