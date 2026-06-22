from pydantic import BaseModel, Field


class ConversationCreateRequest(BaseModel):
    """显式创建新会话时的请求参数。"""

    thread_id: str = Field(min_length=1, max_length=64)
    title: str | None = Field(default=None, max_length=255)
