from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    ANTHROPIC_API_KEY: SecretStr | None = None
    OPENAI_API_KEY: SecretStr | None = None
    MISTRAL_API_KEY: SecretStr | None = None
    GROK_API_KEY: SecretStr | None = None
    GEMINI_API_KEY: SecretStr | None = None
    GROQ_API_KEY: SecretStr | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )


settings = Settings()
