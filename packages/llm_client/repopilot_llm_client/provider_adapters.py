from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ProviderCompletionRequest:
    url: str
    headers: dict[str, str]
    json_payload: dict[str, Any]


def build_completion_request(
    *,
    provider_id: str,
    model: str,
    api_key: str,
    base_url: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float,
    max_tokens: int,
    json_mode: bool = False,
) -> ProviderCompletionRequest:
    provider = provider_id.strip().lower()
    clean_base_url = base_url.rstrip("/")
    if provider == "anthropic":
        url = f"{clean_base_url}/messages" if clean_base_url.endswith("/v1") else f"{clean_base_url}/v1/messages"
        return ProviderCompletionRequest(
            url=url,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "anthropic-version": "2023-06-01",
                "x-api-key": api_key,
            },
            json_payload={
                "model": model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "system": system_prompt,
                "messages": [{"role": "user", "content": [{"type": "text", "text": user_prompt}]}],
            },
        )
    if provider == "google":
        api_root = clean_base_url if clean_base_url.endswith(("/v1", "/v1beta")) else f"{clean_base_url}/v1beta"
        model_path = model if model.startswith("models/") else f"models/{model}"
        generation_config: dict[str, Any] = {"temperature": temperature, "maxOutputTokens": max_tokens}
        if json_mode:
            generation_config["responseMimeType"] = "application/json"
        payload: dict[str, Any] = {
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            "generationConfig": generation_config,
        }
        if system_prompt:
            payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}
        return ProviderCompletionRequest(
            url=f"{api_root}/{model_path}:generateContent",
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "x-goog-api-key": api_key,
            },
            json_payload=payload,
        )

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    return ProviderCompletionRequest(
        url=f"{clean_base_url}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json", "Content-Type": "application/json"},
        json_payload=payload,
    )


def extract_completion_content(*, provider_id: str, payload: Any) -> str:
    provider = provider_id.strip().lower()
    if provider == "anthropic":
        return _extract_anthropic_content(payload)
    if provider == "google":
        return _extract_google_content(payload)
    return _extract_openai_compatible_content(payload)


def extract_completion_usage(*, provider_id: str, payload: Any) -> dict[str, int]:
    if not isinstance(payload, dict):
        return {"prompt": 0, "completion": 0, "total": 0}
    usage = payload.get("usageMetadata") if provider_id.strip().lower() == "google" else payload.get("usage")
    if not isinstance(usage, dict):
        return {"prompt": 0, "completion": 0, "total": 0}
    prompt = int(usage.get("prompt_tokens") or usage.get("input_tokens") or usage.get("promptTokenCount") or 0)
    completion = int(usage.get("completion_tokens") or usage.get("output_tokens") or usage.get("candidatesTokenCount") or 0)
    total = int(usage.get("total_tokens") or usage.get("totalTokenCount") or prompt + completion)
    return {"prompt": prompt, "completion": completion, "total": total}


def _extract_openai_compatible_content(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, dict):
        return ""
    message = first.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str):
            return content
    text = first.get("text")
    return text if isinstance(text, str) else ""


def _extract_anthropic_content(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    content = payload.get("content")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        if isinstance(block, dict):
            text = block.get("text")
            if isinstance(text, str):
                parts.append(text)
        elif isinstance(block, str):
            parts.append(block)
    return "".join(parts)


def _extract_google_content(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        return ""
    first = candidates[0]
    if not isinstance(first, dict):
        return ""
    content = first.get("content")
    if not isinstance(content, dict):
        return ""
    parts = content.get("parts")
    if not isinstance(parts, list):
        return ""
    output: list[str] = []
    for part in parts:
        if isinstance(part, dict) and isinstance(part.get("text"), str):
            output.append(part["text"])
    return "".join(output)
