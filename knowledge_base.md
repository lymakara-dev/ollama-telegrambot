# Ollama Telegram Bot Knowledge Base

This file is used for simple retrieval-augmented generation (RAG).

## Product facts
- The backend is built with FastAPI.
- Incoming Telegram updates are processed via `/telegram/webhook`.
- The app can call a local Ollama instance through `/api/chat`.
- The bot supports text, image, audio, voice, and document message handling.

## Operations
- Update this file with your own business/domain knowledge.
- Trigger `POST /rag/reload` after editing to reload chunks in memory.
