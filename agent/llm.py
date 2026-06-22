from dotenv import load_dotenv, find_dotenv
import os
from langchain.chat_models import init_chat_model

load_dotenv(find_dotenv())

model = init_chat_model(
    model=os.getenv("LLM_MODEL", "deepseek-v4-pro"),
    model_provider="openai"
)
