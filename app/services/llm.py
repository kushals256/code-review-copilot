from openai import AsyncOpenAI

from app.config import settings


def get_llm_client() -> AsyncOpenAI:
    """OpenAI-compatible client — works with OpenAI, Ollama, Groq, etc."""
    kwargs: dict = {"api_key": settings.effective_api_key or "ollama"}
    if settings.llm_base_url:
        kwargs["base_url"] = settings.llm_base_url
    return AsyncOpenAI(**kwargs)


def llm_extra_kwargs() -> dict:
    """Extra kwargs for chat.completions.create."""
    kwargs: dict = {
        "max_tokens": settings.llm_max_tokens,
        "top_p": 0.7,
    }
    if settings.llm_provider == "openai" and settings.effective_api_key not in ("", "ollama"):
        kwargs["response_format"] = {"type": "json_object"}
    return kwargs
