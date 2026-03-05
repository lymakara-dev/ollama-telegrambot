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

## Step-by-step setup (for non-technical users)

These steps assume you already cloned the project and opened a terminal in the project folder.

### 1) Check that Python is installed

```bash
python3 --version
```

If your terminal says the command is missing, install Python 3.11+ first, then continue.

### 2) Create and activate a virtual environment

This creates an isolated Python environment so project dependencies do not affect your system globally.

```bash
python3 -m venv .venv
source .venv/bin/activate
```

After activation, your terminal should show `(.venv)` at the beginning of the prompt.

### 3) Install Python dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 4) Create your `.env` configuration file

Copy the template:

```bash
cp .env.example .env
```

Open the file and set your bot token and webhook secret:

```bash
nano .env
```

At minimum, set these values:

```env
TELEGRAM_BOT_TOKEN=<your-token-from-botfather>
TELEGRAM_WEBHOOK_SECRET=<any-random-secret-string>
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=llama3.1
```

Save and exit in `nano`: press `Ctrl+O`, `Enter`, then `Ctrl+X`.

### 5) Install Ollama and pull a model

Start Ollama (in a separate terminal window):

```bash
ollama serve
```

In your project terminal, pull the default model:

```bash
ollama pull llama3.1
```

Optional (only if you want image understanding):

```bash
ollama pull llava
```

### 6) Start the API server

From your project directory (with virtual environment active):

```bash
uvicorn app:app --host 0.0.0.0 --port 8000
```

Keep this terminal running.

### 7) Expose your local server to Telegram (required for webhook)

Telegram cannot call `localhost` directly, so expose your local port with a tunnel tool (example: `ngrok`).

In a new terminal:

```bash
ngrok http 8000
```

Copy the HTTPS URL shown by ngrok, for example:

```text
https://abcd-1234.ngrok-free.app
```

### 8) Register Telegram webhook

Run this command in terminal (replace placeholder values):

```bash
export TELEGRAM_BOT_TOKEN=<your-bot-token>
export TELEGRAM_WEBHOOK_SECRET=<same-secret-as-.env>
export PUBLIC_URL=<your-ngrok-https-url>

curl -X POST "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "'"$PUBLIC_URL"'/telegram/webhook",
    "secret_token": "'"$TELEGRAM_WEBHOOK_SECRET"'"
  }'
```

If successful, Telegram returns JSON with `"ok": true`.

### 9) Confirm local service health

```bash
curl http://127.0.0.1:8000/health
```

You should see a response like:

```json
{"status":"ok","queue_size":0}
```

### 10) Start chatting with your bot

1. Open Telegram.
2. Find your bot username.
3. Send a normal text message.
4. Wait for reply.

If no reply appears, check:
- Uvicorn terminal for errors.
- Ollama terminal is still running.
- ngrok is still running and URL was correctly registered as webhook.

## Local usage tips

- **Reload knowledge base after editing `knowledge_base.md`:**

  ```bash
  curl -X POST http://127.0.0.1:8000/rag/reload
  ```

- **Stop the server:** press `Ctrl+C` in the uvicorn terminal.
- **Deactivate virtual env when done:**

  ```bash
  deactivate
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
