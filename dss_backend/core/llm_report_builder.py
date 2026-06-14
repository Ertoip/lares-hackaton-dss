import json
import logging
import os
from typing import Any

from openai import AsyncOpenAI, OpenAI


logger = logging.getLogger(__name__)

LLM_MODEL = os.getenv("DSS_LLM_MODEL", "gpt-4o-mini")
LLM_REPORT_MAX_TOKENS = int(os.getenv("DSS_LLM_REPORT_MAX_TOKENS", "500"))
LLM_TEMPERATURE = float(os.getenv("DSS_LLM_TEMPERATURE", "0.1"))
LLM_MAX_CONTEXT_CHARS = int(os.getenv("DSS_LLM_MAX_CONTEXT_CHARS", "12000"))


def _to_str_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [value]
    return [str(item) for item in value]


class LLMReportBuilder:
    def __init__(self) -> None:
        api_key = os.getenv("OPENAI_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_KEY env var not set")
        self._client = OpenAI(api_key=api_key)
        self._async_client = AsyncOpenAI(api_key=api_key)
        self.enabled = True
        logger.info("DSS LLM using OpenAI model %s", LLM_MODEL)

    def build_report(self, report_input: dict[str, Any]) -> dict[str, Any]:
        system_prompt, user_prompt = self._build_report_messages(report_input)
        try:
            text = self._generate(system_prompt, user_prompt)
            return self._parse_report(text, report_input)
        except Exception as exc:
            logger.warning("DSS LLM report failed: %s", exc)
            return self._fallback_report(report_input)

    def build_chat_response(self, user_message: str, context: dict[str, Any]) -> dict[str, Any]:
        system_prompt, user_prompt = self._build_chat_messages(user_message, context)
        try:
            text = self._generate(system_prompt, user_prompt)
            return self._parse_chat(text)
        except Exception as exc:
            logger.warning("DSS LLM chat failed: %s", exc)
            return {
                "body": "Could not reach the LLM at this time.",
                "referenced_event_ids": [],
                "referenced_vehicle_ids": [],
            }

    def _generate(self, system_prompt: str, user_prompt: str) -> str:
        response = self._client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=LLM_REPORT_MAX_TOKENS,
            temperature=LLM_TEMPERATURE,
            response_format={"type": "json_object"},
        )
        return response.choices[0].message.content

    async def stream_chat_response(self, user_message: str, context: dict[str, Any]):
        facts = json.dumps(context, default=str, ensure_ascii=True)[:LLM_MAX_CONTEXT_CHARS]
        stream = await self._async_client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are the chat layer of a maritime Decision Support System. "
                        "Answer using only the provided DSS state. "
                        "Do not invent vehicles, events, contacts, telemetry, or commands. "
                        "Be concise and factual. Answer in plain text."
                    ),
                },
                {
                    "role": "user",
                    "content": f"DSS state: {facts}\nOperator question: {user_message}",
                },
            ],
            max_tokens=LLM_REPORT_MAX_TOKENS,
            temperature=LLM_TEMPERATURE,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta

    def _build_report_messages(self, report_input: dict[str, Any]) -> tuple[str, str]:
        facts = json.dumps(report_input, default=str, ensure_ascii=True)[:LLM_MAX_CONTEXT_CHARS]
        system_prompt = (
            "You are the mission report layer of a maritime Decision Support System. "
            "Summarize recent anomalies for the operator. "
            "Do not invent events, vehicles, commands, or facts. "
            "Be short, operational, and prioritized. "
            "Output valid JSON only."
        )
        user_prompt = (
            "Return JSON with fields: title, summary, situation (list), why_it_matters (list), "
            "operator_focus (list), assumptions (list), urgency (low|medium|high|critical). "
            f"Facts: {facts}"
        )
        return system_prompt, user_prompt

    def _build_chat_messages(self, user_message: str, context: dict[str, Any]) -> tuple[str, str]:
        facts = json.dumps(context, default=str, ensure_ascii=True)[:LLM_MAX_CONTEXT_CHARS]
        system_prompt = (
            "You are the chat layer of a maritime Decision Support System. "
            "Answer using only the provided DSS state. "
            "Do not invent vehicles, events, contacts, telemetry, or commands. "
            "Be concise and factual. Output valid JSON only."
        )
        user_prompt = (
            "Return JSON with fields: body, referenced_event_ids (list), referenced_vehicle_ids (list). "
            f"DSS state: {facts}\n"
            f"Operator message: {user_message}"
        )
        return system_prompt, user_prompt

    def _parse_report(self, text: str, report_input: dict[str, Any]) -> dict[str, Any]:
        try:
            parsed = json.loads(text)
            return {
                "title": str(parsed.get("title") or "Operator attention required"),
                "summary": str(parsed.get("summary") or "Recent anomalies exceeded the severity threshold."),
                "situation": _to_str_list(parsed.get("situation")),
                "why_it_matters": _to_str_list(parsed.get("why_it_matters")),
                "operator_focus": _to_str_list(parsed.get("operator_focus")),
                "assumptions": _to_str_list(parsed.get("assumptions")),
                "urgency": str(parsed.get("urgency") or "high"),
            }
        except Exception:
            return self._fallback_report(report_input)

    def _parse_chat(self, text: str) -> dict[str, Any]:
        try:
            parsed = json.loads(text)
            return {
                "body": str(parsed.get("body") or "The DSS state does not contain enough information."),
                "referenced_event_ids": list(parsed.get("referenced_event_ids") or []),
                "referenced_vehicle_ids": list(parsed.get("referenced_vehicle_ids") or []),
            }
        except Exception:
            return {
                "body": "The DSS state does not contain enough information.",
                "referenced_event_ids": [],
                "referenced_vehicle_ids": [],
            }

    def _fallback_report(self, report_input: dict[str, Any]) -> dict[str, Any]:
        events = report_input.get("events") or []
        situation = [
            f"{e.get('severity', 'unknown')} {e.get('event_kind', 'event')} on {e.get('vehicle_id', 'unknown')}: {e.get('description', '')}"
            for e in events
        ]
        return {
            "title": "Operator attention required",
            "summary": "Recent anomalies exceeded the configured severity threshold.",
            "situation": situation or ["Active DSS events exceeded the reporting threshold."],
            "why_it_matters": ["Mission risk increased due to anomaly accumulation."],
            "operator_focus": ["Review highlighted events on the map."],
            "assumptions": ["Report generated from current DSS state."],
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
