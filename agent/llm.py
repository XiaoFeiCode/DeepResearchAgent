from langchain.chat_models import init_chat_model

from core.settings import get_settings

settings = get_settings()
model_name, base_url, api_key = settings.require_model_credentials()

model = init_chat_model(
    model=model_name,
    model_provider="openai",
    base_url=base_url,
    api_key=api_key,
)
