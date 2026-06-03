# LLM Client Package

Status: reusable LLM catalog package. The provider/model catalog now lives in `packages/llm_client/repopilot_llm_client`, and `apps/api/app/services/model_catalog.py` remains a compatibility re-export for existing API call sites. The current mock-first `ModelGateway` still lives in `apps/api/app/services/model_gateway.py` because it persists API-specific traces and run budget data.

The API is provider-agnostic today and records model names plus LLM trace metadata for planning. `/settings/readiness` now reports `MODEL_PROVIDER=mock` as a production blocker so local deterministic behavior is not mistaken for live LLM behavior. The API gateway and eval harness share pure OpenAI-compatible, Anthropic Messages, and Gemini GenerateContent request/response adapters from this package; API-specific trace persistence remains in `apps/api`.

Current and expected responsibilities:

- Provider/model catalog shared by settings, readiness, and verification screens.
- Model-provider routing and pure provider request/response adapters.
- Structured-output validation.
- Prompt hashing.
- Retry handling.
- Token accounting.
- Cost and latency tracking.

Business logic must stay in services such as planning, implementation, security, CI analysis, and evals so provider changes do not alter the safety model.
