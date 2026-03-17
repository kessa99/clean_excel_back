from langchain_core.language_models.chat_models import BaseChatModel

from .settings import settings


def get_llm() -> BaseChatModel:
    if settings.ANTHROPIC_API_KEY:
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model_name="claude-3-5-sonnet-20241022",
            api_key=settings.ANTHROPIC_API_KEY,
            timeout=None,
            stop=None,
        )

    if settings.OPENAI_API_KEY:
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model="gpt-4o",
            api_key=settings.OPENAI_API_KEY,
        )

    if settings.MISTRAL_API_KEY:
        from langchain_mistralai import ChatMistralAI

        return ChatMistralAI(
            model_name="mistral-large-latest",
            api_key=settings.MISTRAL_API_KEY,
        )

    if settings.GROK_API_KEY:
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model="grok-3",
            api_key=settings.GROK_API_KEY,
            base_url="https://api.x.ai/v1",
        )

    if settings.GEMINI_API_KEY:
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model="gemini-2.0-flash",
            google_api_key=settings.GEMINI_API_KEY,
        )

    if settings.GROQ_API_KEY:
        from langchain_groq import ChatGroq

        return ChatGroq(
            model="llama-3.1-8b-instant",
            api_key=settings.GROQ_API_KEY,
        )

    raise RuntimeError(
        "Aucune clé API disponible. "
        "Définissez au moins une des variables suivantes dans .env : "
        "ANTHROPIC_API_KEY, OPENAI_API_KEY, MISTRAL_API_KEY, GROK_API_KEY, GEMINI_API_KEY"
    )
