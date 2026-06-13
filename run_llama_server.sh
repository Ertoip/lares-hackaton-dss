#!/usr/bin/env bash
set -euo pipefail

LLAMA_SERVER_BIN="${LLAMA_SERVER_BIN:-llama-server}"
HF_REPO="${DSS_GGUF_HF_REPO:-NikolayKozloff/Nemotron-Mini-4B-Instruct-Q8_0-GGUF}"
HF_FILE="${DSS_GGUF_HF_FILE:-nemotron-mini-4b-instruct-q8_0.gguf}"
CONTEXT="${DSS_LLAMA_CONTEXT:-2048}"
PORT="${DSS_LLAMA_PORT:-8080}"

exec "$LLAMA_SERVER_BIN" \
  --hf-repo "$HF_REPO" \
  --hf-file "$HF_FILE" \
  -c "$CONTEXT" \
  --host 127.0.0.1 \
  --port "$PORT"
