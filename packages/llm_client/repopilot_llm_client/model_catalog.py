from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ModelOption:
    id: str
    name: str
    context_window: str
    capabilities: tuple[str, ...]
    reasoning_levels: tuple[str, ...] = ()


@dataclass(frozen=True)
class ModelProviderOption:
    id: str
    name: str
    description: str
    api_key_env: str
    default_base_url: str
    docs_url: str
    models: tuple[ModelOption, ...]


# Curated from official provider docs/API reference pages on 2026-05-24.
MODEL_PROVIDERS: tuple[ModelProviderOption, ...] = (
    ModelProviderOption(
        id="openai",
        name="OpenAI",
        description="Frontier OpenAI models for coding, reasoning, agents, and multimodal text workflows.",
        api_key_env="MODEL_API_KEY",
        default_base_url="https://api.openai.com/v1",
        docs_url="https://developers.openai.com/api/docs/models",
        models=(
            ModelOption("gpt-5.5", "GPT-5.5", "1M", ("reasoning", "tools", "vision"), ("minimal", "low", "medium", "high")),
            ModelOption("gpt-5.4", "GPT-5.4", "1M", ("reasoning", "tools", "vision"), ("minimal", "low", "medium", "high")),
            ModelOption("gpt-5.4-mini", "GPT-5.4 mini", "400K", ("reasoning", "tools", "vision"), ("minimal", "low", "medium", "high")),
            ModelOption("gpt-5.4-nano", "GPT-5.4 nano", "400K", ("reasoning", "low latency"), ("minimal", "low", "medium", "high")),
        ),
    ),
    ModelProviderOption(
        id="anthropic",
        name="Anthropic",
        description="Claude models for long-context coding, planning, and tool-using agents.",
        api_key_env="MODEL_API_KEY",
        default_base_url="https://api.anthropic.com",
        docs_url="https://platform.claude.com/docs/en/about-claude/models/overview",
        models=(
            ModelOption("claude-opus-4-7", "Claude Opus 4.7", "1M", ("reasoning", "vision", "agents"), ("adaptive", "low", "medium", "high", "max")),
            ModelOption("claude-sonnet-4-6", "Claude Sonnet 4.6", "1M", ("reasoning", "vision", "coding"), ("adaptive", "low", "medium", "high", "max")),
            ModelOption("claude-haiku-4-5-20251001", "Claude Haiku 4.5", "200K", ("vision", "low latency")),
        ),
    ),
    ModelProviderOption(
        id="google",
        name="Google Gemini",
        description="Gemini API models for multimodal context, code execution, grounding, and agent workflows.",
        api_key_env="MODEL_API_KEY",
        default_base_url="https://generativelanguage.googleapis.com",
        docs_url="https://ai.google.dev/gemini-api/docs/models",
        models=(
            ModelOption("gemini-3-pro-preview", "Gemini 3 Pro Preview", "1,048,576", ("thinking", "tools", "vision"), ("low", "medium", "high")),
            ModelOption("gemini-3-flash-preview", "Gemini 3 Flash Preview", "1,048,576", ("thinking", "tools", "computer use"), ("low", "medium", "high")),
            ModelOption("gemini-2.5-pro", "Gemini 2.5 Pro", "1,048,576", ("thinking", "tools", "vision"), ("low", "medium", "high")),
            ModelOption("gemini-2.5-flash", "Gemini 2.5 Flash", "1,048,576", ("thinking", "tools", "low latency"), ("low", "medium", "high")),
            ModelOption("gemini-2.5-flash-lite", "Gemini 2.5 Flash-Lite", "1,048,576", ("low cost", "tools", "vision"), ("low", "medium", "high")),
        ),
    ),
    ModelProviderOption(
        id="mistral",
        name="Mistral AI",
        description="Mistral frontier, coding, and small open models through La Plateforme.",
        api_key_env="MODEL_API_KEY",
        default_base_url="https://api.mistral.ai/v1",
        docs_url="https://docs.mistral.ai/models/overview",
        models=(
            ModelOption("mistral-large-2512", "Mistral Large 3", "N/A", ("frontier", "vision", "tools")),
            ModelOption("mistral-medium-3-5", "Mistral Medium 3.5", "N/A", ("coding", "agents", "vision")),
            ModelOption("mistral-small-2603", "Mistral Small 4", "N/A", ("reasoning", "coding", "open")),
            ModelOption("devstral-2512", "Devstral 2", "N/A", ("coding", "software engineering")),
            ModelOption("codestral-2508", "Codestral", "N/A", ("code completion",)),
            ModelOption("ministral-14b-2512", "Ministral 3 14B", "256K", ("open", "vision")),
        ),
    ),
    ModelProviderOption(
        id="cohere",
        name="Cohere",
        description="Command family models for enterprise agents, RAG, tool use, and multilingual generation.",
        api_key_env="MODEL_API_KEY",
        default_base_url="https://api.cohere.com/v2",
        docs_url="https://docs.cohere.com/v2/docs/models",
        models=(
            ModelOption("command-a-plus-05-2026", "Command A+", "128K", ("reasoning", "vision", "agents")),
            ModelOption("command-a-03-2025", "Command A", "256K", ("tools", "RAG", "multilingual")),
            ModelOption("command-a-reasoning-08-2025", "Command A Reasoning", "256K", ("reasoning", "tools", "agents")),
            ModelOption("command-r-plus-08-2024", "Command R+", "128K", ("RAG", "tools", "multilingual")),
            ModelOption("command-r-08-2024", "Command R", "128K", ("RAG", "tools", "low cost")),
            ModelOption("command-r7b-12-2024", "Command R7B", "128K", ("RAG", "low latency", "tools")),
        ),
    ),
    ModelProviderOption(
        id="groq",
        name="Groq",
        description="GroqCloud hosted production and preview open models optimized for very high token throughput.",
        api_key_env="MODEL_API_KEY",
        default_base_url="https://api.groq.com/openai/v1",
        docs_url="https://console.groq.com/docs/models",
        models=(
            ModelOption("llama-3.3-70b-versatile", "Llama 3.3 70B Versatile", "131,072", ("production", "tools")),
            ModelOption("llama-3.1-8b-instant", "Llama 3.1 8B Instant", "131,072", ("production", "low latency")),
            ModelOption("meta-llama/llama-4-scout-17b-16e-instruct", "Llama 4 Scout 17B 16E", "131,072", ("preview", "vision")),
            ModelOption("qwen/qwen3-32b", "Qwen3 32B", "131,072", ("preview", "reasoning")),
            ModelOption("openai/gpt-oss-safeguard-20b", "GPT-OSS Safeguard 20B", "131,072", ("preview", "safety")),
        ),
    ),
    ModelProviderOption(
        id="xai",
        name="xAI",
        description="Grok models for long-context agentic tool calling and structured outputs.",
        api_key_env="MODEL_API_KEY",
        default_base_url="https://api.x.ai/v1",
        docs_url="https://docs.x.ai/developers/models",
        models=(
            ModelOption("grok-4.3", "Grok 4.3", "1M", ("reasoning", "tools", "vision"), ("none", "low", "medium", "high")),
            ModelOption("grok-4.3-latest", "Grok 4.3 Latest", "1M", ("reasoning", "tools", "vision"), ("none", "low", "medium", "high")),
            ModelOption("grok-latest", "Grok Latest", "1M", ("alias", "tools")),
        ),
    ),
    ModelProviderOption(
        id="deepseek",
        name="DeepSeek",
        description="Official DeepSeek API models with OpenAI-compatible and Anthropic-compatible base URLs.",
        api_key_env="MODEL_API_KEY",
        default_base_url="https://api.deepseek.com",
        docs_url="https://api-docs.deepseek.com/quick_start/pricing",
        models=(
            ModelOption("deepseek-v4-flash", "DeepSeek V4 Flash", "1M", ("thinking", "tools", "low cost")),
            ModelOption("deepseek-v4-pro", "DeepSeek V4 Pro", "1M", ("thinking", "tools", "frontier")),
        ),
    ),
    ModelProviderOption(
        id="perplexity",
        name="Perplexity",
        description="Sonar API models with search-grounded responses and reasoning/research variants.",
        api_key_env="MODEL_API_KEY",
        default_base_url="https://api.perplexity.ai",
        docs_url="https://docs.perplexity.ai/api-reference/sonar-post",
        models=(
            ModelOption("sonar", "Sonar", "128K max output", ("search", "grounding")),
            ModelOption("sonar-pro", "Sonar Pro", "128K max output", ("search", "grounding", "complex queries")),
            ModelOption("sonar-reasoning-pro", "Sonar Reasoning Pro", "128K max output", ("reasoning", "search"), ("low", "medium", "high")),
            ModelOption("sonar-deep-research", "Sonar Deep Research", "128K max output", ("research", "search"), ("low", "medium", "high")),
        ),
    ),
    ModelProviderOption(
        id="together",
        name="Together AI",
        description="Serverless open-model inference with chat model metadata available from the Together Models API.",
        api_key_env="MODEL_API_KEY",
        default_base_url="https://api.together.xyz/v1",
        docs_url="https://docs.together.ai/docs/serverless/models",
        models=(
            ModelOption("deepseek-ai/DeepSeek-V4-Pro", "DeepSeek V4 Pro", "512K", ("tools", "structured outputs")),
            ModelOption("moonshotai/Kimi-K2.5", "Kimi K2.5", "N/A", ("reasoning",)),
            ModelOption("openai/gpt-oss-120b", "GPT-OSS 120B", "N/A", ("open weights", "reasoning")),
            ModelOption("MiniMaxAI/MiniMax-M2.7", "MiniMax M2.7", "N/A", ("general purpose",)),
            ModelOption("meta-llama/Llama-3.3-70B-Instruct-Turbo", "Llama 3.3 70B Instruct Turbo", "131,072", ("chat", "tools")),
            ModelOption("Qwen/Qwen3-235B-A22B-Instruct-2507-tput", "Qwen3 235B A22B Instruct", "N/A", ("reasoning", "tools")),
        ),
    ),
    ModelProviderOption(
        id="openrouter",
        name="OpenRouter",
        description="Unified API gateway with dynamic live model catalog, routing metadata, and pricing-aware free model flags.",
        api_key_env="MODEL_API_KEY",
        default_base_url="https://openrouter.ai/api/v1",
        docs_url="https://openrouter.ai/docs/api-reference/models/get-models",
        models=(),
    ),
    ModelProviderOption(
        id="cerebras",
        name="Cerebras",
        description="Cerebras Inference API with OpenAI-compatible high-throughput hosted models.",
        api_key_env="MODEL_API_KEY",
        default_base_url="https://api.cerebras.ai/v1",
        docs_url="https://inference-docs.cerebras.ai/api-reference/models/list-models",
        models=(
            ModelOption("gpt-oss-120b", "GPT-OSS 120B", "N/A", ("reasoning", "high throughput")),
            ModelOption("llama3.1-8b", "Llama 3.1 8B", "N/A", ("low latency",)),
        ),
    ),
)


def provider_catalog() -> dict[str, object]:
    return {"providers": [asdict(provider) for provider in MODEL_PROVIDERS]}


def provider_by_id(provider_id: str) -> ModelProviderOption | None:
    normalized = provider_id.strip().lower()
    return next((provider for provider in MODEL_PROVIDERS if provider.id == normalized), None)


def model_ids_for_provider(provider_id: str) -> set[str]:
    provider = provider_by_id(provider_id)
    if not provider:
        return set()
    return {model.id for model in provider.models}


def model_by_id(provider_id: str, model_id: str) -> ModelOption | None:
    provider = provider_by_id(provider_id)
    if not provider:
        return None
    return next((model for model in provider.models if model.id == model_id), None)
