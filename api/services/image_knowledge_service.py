from fastapi import UploadFile

from image_knowledge import ImageKnowledgeStore, image_knowledge_store


class ImageKnowledgeService:
    """Coordinate uploads and searches for the multimodal image knowledge base."""

    def __init__(self, store: ImageKnowledgeStore = image_knowledge_store) -> None:
        self.store = store

    def upload_images(
        self,
        *,
        user_id: str,
        files: list[UploadFile],
        description: str = "",
    ) -> list[dict]:
        images = []
        for upload in files:
            filename = upload.filename or "image.png"
            content = upload.file.read()
            images.append(
                self.store.add_image(
                    user_id=user_id,
                    filename=filename,
                    content=content,
                    description=description,
                )
            )
        return images

    def search(
        self,
        *,
        user_id: str,
        query: str = "",
        file: UploadFile | None = None,
        limit: int = 6,
    ) -> list[dict]:
        image_content = file.file.read() if file is not None else None
        image_filename = (file.filename or "query.png") if file is not None else "query.png"
        return self.store.search(
            user_id=user_id,
            query_text=query,
            image_content=image_content,
            image_filename=image_filename,
            limit=limit,
        )
