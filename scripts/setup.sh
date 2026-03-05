#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$PROJECT_ROOT/.venv"
ENV_FILE="$PROJECT_ROOT/.env"
ENV_EXAMPLE_FILE="$PROJECT_ROOT/.env.example"

usage() {
  cat <<'USAGE'
Usage: ./scripts/setup.sh [options]

Bootstrap the project after cloning:
- Creates .venv and installs dependencies
- Creates .env from .env.example when missing
- Verifies Ollama availability and pulls model(s)
- Optionally sets Telegram webhook

Options:
  --bot-token <token>         Telegram bot token (written to .env)
  --webhook-secret <secret>   Telegram webhook secret (written to .env)
  --public-url <https-url>    Public HTTPS URL for webhook setup (e.g., ngrok URL)
  --model <name>              Ollama text model to pull (default: from .env or llama3.1)
  --vision-model <name>       Optional Ollama vision model to pull (e.g., llava)
  --skip-ollama-pull          Skip pulling Ollama model(s)
  --skip-webhook              Skip Telegram webhook registration
  --help                      Show this message
USAGE
}

log() { printf '\n[%s] %s\n' "$(date '+%H:%M:%S')" "$*"; }
warn() { printf '\n[WARN] %s\n' "$*"; }
err() { printf '\n[ERROR] %s\n' "$*"; exit 1; }

BOT_TOKEN=""
WEBHOOK_SECRET=""
PUBLIC_URL=""
MODEL=""
VISION_MODEL=""
SKIP_OLLAMA_PULL=0
SKIP_WEBHOOK=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --bot-token)
      BOT_TOKEN="${2:-}"; shift 2 ;;
    --webhook-secret)
      WEBHOOK_SECRET="${2:-}"; shift 2 ;;
    --public-url)
      PUBLIC_URL="${2:-}"; shift 2 ;;
    --model)
      MODEL="${2:-}"; shift 2 ;;
    --vision-model)
      VISION_MODEL="${2:-}"; shift 2 ;;
    --skip-ollama-pull)
      SKIP_OLLAMA_PULL=1; shift ;;
    --skip-webhook)
      SKIP_WEBHOOK=1; shift ;;
    --help|-h)
      usage; exit 0 ;;
    *)
      err "Unknown option: $1. Use --help for usage." ;;
  esac
done

command -v python3 >/dev/null 2>&1 || err "python3 not found. Install Python 3.11+ and retry."

log "Creating virtual environment (.venv) if needed"
if [[ ! -d "$VENV_DIR" ]]; then
  python3 -m venv "$VENV_DIR"
fi

# shellcheck source=/dev/null
source "$VENV_DIR/bin/activate"

log "Installing Python dependencies"
python -m pip install --upgrade pip
python -m pip install -r "$PROJECT_ROOT/requirements.txt"

if [[ ! -f "$ENV_FILE" ]]; then
  log "Creating .env from .env.example"
  cp "$ENV_EXAMPLE_FILE" "$ENV_FILE"
else
  log ".env already exists, keeping existing values"
fi

update_env_key() {
  local key="$1"
  local value="$2"
  [[ -z "$value" ]] && return 0

  if grep -q "^${key}=" "$ENV_FILE"; then
    sed -i "s|^${key}=.*|${key}=${value}|" "$ENV_FILE"
  else
    printf '\n%s=%s\n' "$key" "$value" >> "$ENV_FILE"
  fi
}

update_env_key "TELEGRAM_BOT_TOKEN" "$BOT_TOKEN"
update_env_key "TELEGRAM_WEBHOOK_SECRET" "$WEBHOOK_SECRET"

if [[ -z "$MODEL" ]]; then
  MODEL="$(grep '^OLLAMA_MODEL=' "$ENV_FILE" 2>/dev/null | cut -d'=' -f2- || true)"
fi
MODEL="${MODEL:-llama3.1}"
update_env_key "OLLAMA_MODEL" "$MODEL"

if [[ "$SKIP_OLLAMA_PULL" -eq 0 ]]; then
  if command -v ollama >/dev/null 2>&1; then
    log "Checking Ollama service"
    if ! ollama list >/dev/null 2>&1; then
      warn "Could not reach Ollama. Start it with: ollama serve"
    fi

    log "Pulling Ollama model: $MODEL"
    ollama pull "$MODEL"

    if [[ -n "$VISION_MODEL" ]]; then
      log "Pulling vision model: $VISION_MODEL"
      ollama pull "$VISION_MODEL"
    fi
  else
    warn "Ollama CLI not found. Install Ollama first: https://ollama.com/download"
  fi
else
  log "Skipping Ollama model pull as requested"
fi

if [[ "$SKIP_WEBHOOK" -eq 0 ]]; then
  if [[ -n "$BOT_TOKEN" && -n "$WEBHOOK_SECRET" && -n "$PUBLIC_URL" ]]; then
    log "Registering Telegram webhook"
    curl -fsS -X POST "https://api.telegram.org/bot${BOT_TOKEN}/setWebhook" \
      -H "Content-Type: application/json" \
      -d "{\"url\":\"${PUBLIC_URL%/}/telegram/webhook\",\"secret_token\":\"${WEBHOOK_SECRET}\"}" \
      | python -m json.tool
  else
    warn "Skipping webhook setup. Provide --bot-token, --webhook-secret and --public-url to auto-register it."
  fi
else
  log "Skipping Telegram webhook setup as requested"
fi

cat <<NEXT

Setup complete.

Next steps:
1) Start Ollama (if not running):
   ollama serve

2) Start API server:
   source .venv/bin/activate
   uvicorn app:app --host 0.0.0.0 --port 8000

3) Health check:
   curl http://127.0.0.1:8000/health
NEXT
