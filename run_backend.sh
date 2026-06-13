#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

export DSS_LLAMACPP_BASE_URL="${DSS_LLAMACPP_BASE_URL:-http://127.0.0.1:8080}"
export DSS_LLM_MODEL="${DSS_LLM_MODEL:-NikolayKozloff/Nemotron-Mini-4B-Instruct-Q8_0-GGUF}"

exec .venv/bin/python -m uvicorn dss_backend.main:app --host 0.0.0.0 --port 8001
