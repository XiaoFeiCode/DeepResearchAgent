from pydantic import BaseModel, Field


class RagflowDocumentRequest(BaseModel):
    """解析或删除 RAGFlow 文档时的请求参数。"""

    dataset_name_or_id: str = Field(min_length=1)
    document_names_or_ids: str = Field(min_length=1)
