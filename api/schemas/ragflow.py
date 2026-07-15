from pydantic import BaseModel, Field


class RagflowDocumentRequest(BaseModel):
    """解析或删除 RAGFlow 文档时的请求参数。"""

    dataset_name_or_id: str = Field(min_length=1)
    document_names_or_ids: str = Field(min_length=1)


class RagflowImageSearchRequest(BaseModel):
    """检索 RAGFlow 文档中解析出的图片。"""

    query: str = Field(min_length=1, max_length=4000)
    dataset_name_or_id: str = Field(min_length=1)
    document_name_or_id: str = Field(default="", max_length=1000)
    limit: int = Field(default=8, ge=1, le=20)
