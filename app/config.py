from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    github_token: str = ""
    github_webhook_secret: str = ""
    host: str = "0.0.0.0"
    port: int = 8000

    # LLM — ollama (local), nvidia, openai, groq, etc.
    llm_provider: str = "ollama"
    llm_api_key: str = ""
    llm_base_url: str = "http://localhost:11434/v1"
    llm_model: str = "llama3.2:1b"
    llm_max_tokens: int = 4096

    # Legacy env names still work
    openai_api_key: str = ""
    openai_model: str = ""

    @property
    def effective_api_key(self) -> str:
        if self.llm_api_key:
            return self.llm_api_key
        if self.openai_api_key:
            return self.openai_api_key
        return "ollama" if self.llm_provider == "ollama" else ""

    @property
    def effective_model(self) -> str:
        return self.openai_model or self.llm_model


settings = Settings()
