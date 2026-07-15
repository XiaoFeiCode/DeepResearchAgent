from pathlib import Path

from image_knowledge.embedding import MultimodalEmbeddingClient
from image_knowledge.store import ImageKnowledgeStore

PROJECT_ROOT = Path(__file__).resolve().parent.parent
image_knowledge_store = ImageKnowledgeStore(PROJECT_ROOT)

__all__ = [
    "ImageKnowledgeStore",
    "MultimodalEmbeddingClient",
    "image_knowledge_store",
]
