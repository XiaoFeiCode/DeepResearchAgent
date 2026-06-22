from pydantic import BaseModel, Field


class TaskRequest(BaseModel):
    """启动智能体任务时的请求参数。"""

    query: str = Field(min_length=1)
    thread_id: str | None = None
