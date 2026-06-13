import json
import logging
import os
from pathlib import Path
from typing import Any

from llama_cpp import Llama


logger = logging.getLogger(__name__)


def _to_str_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [value]
    return [str(item) for item in value]

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_MODEL_PATH = _PROJECT_ROOT / "models" / "nemotron-mini-4b-instruct-q8_0.gguf"

MODEL_PATH = Path(os.getenv("DSS_GGUF_MODEL_PATH", str(_DEFAULT_MODEL_PATH)))
LLM_REPORT_MAX_TOKENS = int(os.getenv("DSS_LLM_REPORT_MAX_TOKENS", "500"))
LLM_TEMPERATURE = float(os.getenv("DSS_LLM_TEMPERATURE", "0.1"))
LLM_TOP_P = float(os.getenv("DSS_LLM_TOP_P", "0.9"))
LLM_N_CTX = int(os.getenv("DSS_LLAMA_CONTEXT", "4096"))
LLM_N_GPU_LAYERS = int(os.getenv("DSS_LLAMA_GPU_LAYERS", "-1"))  # -1 = all layers on GPU
# ~2 chars/token for JSON; reserve tokens for prompt templates + response
_MAX_FACTS_CHARS = (LLM_N_CTX - LLM_REPORT_MAX_TOKENS - 500) * 2


class LLMReportBuilder:
    def __init__(self) -> None:
        self.enabled = True
        if not MODEL_PATH.exists():
            raise FileNotFoundError(f"GGUF model not found at {MODEL_PATH}. Set DSS_GGUF_MODEL_PATH to override.")
        logger.info("Loading llama.cpp model from %s (gpu_layers=%d) ...", MODEL_PATH, LLM_N_GPU_LAYERS)
        self._llm = Llama(
            model_path=str(MODEL_PATH),
            n_ctx=LLM_N_CTX,
            n_gpu_layers=LLM_N_GPU_LAYERS,
            verbose=False,
        )
        logger.info("llama.cpp model loaded.")

    def build_report(self, report_input: dict[str, Any]) -> dict[str, Any]:
        system_prompt, user_prompt = self._build_report_messages(report_input)
        try:
            text = self._generate_text(system_prompt, user_prompt)
            return self._parse_json_or_fallback(text, report_input)
        except Exception as exc:
            logger.warning("DSS llm report generation failed; using fallback: %s", exc)
            return self._fallback_report(report_input)

    def build_chat_response(self, user_message: str, context: dict[str, Any]) -> dict[str, Any]:
        system_prompt, user_prompt = self._build_chat_messages(user_message, context)
        try:
            text = self._generate_text(system_prompt, user_prompt)
            return self._parse_chat_json_or_fallback(text)
        except Exception as exc:
            logger.warning("DSS llm chat generation failed: %s", exc)
            return {
                "body": "The local model could not answer this message.",
                "referenced_event_ids": [],
                "referenced_vehicle_ids": [],
            }

    def _generate_text(self, system_prompt: str, user_prompt: str) -> str:
        response = self._llm.create_chat_completion(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=LLM_REPORT_MAX_TOKENS,
            temperature=LLM_TEMPERATURE,
            top_p=LLM_TOP_P,
        )
        return response["choices"][0]["message"]["content"]

    def _build_report_messages(self, report_input: dict[str, Any]) -> tuple[str, str]:
        facts = json.dumps(report_input, default=str, ensure_ascii=True)[:_MAX_FACTS_CHARS]
        system_prompt = (
            "You are the mission report layer of a maritime Decision Support System. "
            "You summarize recent anomalies/events for a single human operator. "
            "You must not invent events, vehicles, contacts, facts, commands, or mission state. "
            "You must not create action recommendations or vehicle commands. "
            "You may refer only to the provided events/anomalies. "
            "Keep the report short, operational, and prioritized. "
            "Output valid JSON only. No markdown. No extra commentary."
        )
        user_prompt = (
            "Return JSON with fields: title, summary, situation, why_it_matters, "
            "operator_focus, assumptions, urgency. "
            "Allowed urgency values: low, medium, high, critical. "
            f"Provided facts: {facts}"
        )
        return system_prompt, user_prompt

    def _build_chat_messages(self, user_message: str, context: dict[str, Any]) -> tuple[str, str]:
        facts = json.dumps(context, default=str, ensure_ascii=True)[:_MAX_FACTS_CHARS]
        system_prompt = (
            "You are the chat layer of a maritime Decision Support System. "
            "Answer the operator's question using only the provided DSS state. "
            "Do not invent vehicles, events, contacts, telemetry, commands, or mission facts. "
            "Do not suggest vehicle commands or operational actions. "
            "If the provided state does not contain enough information, say that the DSS state does not contain that information. "
            "Be concise and factual. "
            "Output valid JSON only. No markdown. No extra commentary."
        )
        user_prompt = (
            "Return JSON with fields: body, referenced_event_ids, referenced_vehicle_ids. "
            f"DSS state: {facts}\n"
            f"Operator message: {user_message}"
        )
        return system_prompt, user_prompt

    def _parse_json_or_fallback(self, text: str, report_input: dict[str, Any]) -> dict[str, Any]:
        try:
            start = text.index("{")
            end = text.rindex("}") + 1
            parsed = json.loads(text[start:end])
            return {
                "title": str(parsed.get("title") or "Operator attention required"),
                "summary": str(parsed.get("summary") or "Recent anomalies exceeded the configured severity threshold."),
                "situation": _to_str_list(parsed.get("situation")),
                "why_it_matters": _to_str_list(parsed.get("why_it_matters")),
                "operator_focus": _to_str_list(parsed.get("operator_focus")),
                "assumptions": _to_str_list(parsed.get("assumptions")),
                "urgency": str(parsed.get("urgency") or "high"),
            }
        except Exception:
            return self._fallback_report(report_input)

    def _parse_chat_json_or_fallback(self, text: str) -> dict[str, Any]:
        try:
            start = text.index("{")
            end = text.rindex("}") + 1
            parsed = json.loads(text[start:end])
            return {
                "body": str(parsed.get("body") or "The DSS state does not contain enough information to answer that."),
                "referenced_event_ids": list(parsed.get("referenced_event_ids") or []),
                "referenced_vehicle_ids": list(parsed.get("referenced_vehicle_ids") or []),
            }
        except Exception:
            return {
                "body": "The DSS state does not contain enough information to answer that.",
                "referenced_event_ids": [],
                "referenced_vehicle_ids": [],
            }

    def _fallback_report(self, report_input: dict[str, Any]) -> dict[str, Any]:
        events = report_input.get("events") or []
        situation = [
            f"{event.get('severity', 'unknown')} {event.get('event_kind', 'event')} for {event.get('vehicle_id', 'unknown_vehicle')}: {event.get('description', 'No description')}"
            for event in events
        ]
        return {
            "title": "Operator attention required",
            "summary": "Recent anomalies exceeded the configured severity threshold.",
            "situation": situation or ["Recent active DSS events exceeded the reporting threshold."],
            "why_it_matters": ["Mission risk increased due to recent anomaly accumulation."],
            "operator_focus": ["Review the highlighted events on the map."],
            "assumptions": ["This report is generated from current DSS event state."],
            "urgency": "high",
        }


_report_builder: LLMReportBuilder | None = None


def get_report_builder() -> LLMReportBuilder:
    global _report_builder
    if _report_builder is None:
        _report_builder = LLMReportBuilder()
    return _report_builder


def initialize_report_builder() -> LLMReportBuilder:
    return get_report_builder()
