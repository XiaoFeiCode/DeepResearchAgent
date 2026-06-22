import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Column, JSON, Text
from sqlmodel import Field, Session, SQLModel, select

from tools.database.mysql import get_engine

logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    """生成适合 MySQL DATETIME 保存的 UTC 时间。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Conversation(SQLModel, table=True):
    __tablename__ = "agent_conversations"

    id: str = Field(primary_key=True, max_length=64)
    title: str = Field(default="新会话", max_length=255)
    created_at: datetime = Field(default_factory=utc_now, nullable=False)
    updated_at: datetime = Field(default_factory=utc_now, nullable=False, index=True)


class ChatMessage(SQLModel, table=True):
    __tablename__ = "agent_messages"

    id: int | None = Field(default=None, primary_key=True)
    conversation_id: str = Field(
        foreign_key="agent_conversations.id",
        max_length=64,
        index=True,
    )
    role: str = Field(max_length=20)
    content: str = Field(sa_column=Column(Text, nullable=False))
    message_metadata: dict[str, Any] | None = Field(
        default=None,
        sa_column=Column(JSON, nullable=True),
    )
    created_at: datetime = Field(default_factory=utc_now, nullable=False, index=True)


class ConversationService:
    """使用 MySQL 保存前端可恢复的会话和聊天消息。"""

    def __init__(self) -> None:
        self._engine = None
        self.initialization_error: str | None = None

    @property
    def available(self) -> bool:
        return self._engine is not None and self.initialization_error is None

    def initialize(self) -> None:
        """连接 MySQL 并自动创建聊天记录表。"""
        try:
            self._engine = get_engine()
            SQLModel.metadata.create_all(self._engine)
            self.initialization_error = None
        except Exception as error:
            self._engine = None
            self.initialization_error = str(error)
            logger.warning("MySQL conversation memory is unavailable: %s", error)

    def create_conversation(self, thread_id: str, title: str | None = None) -> dict:
        engine = self._require_engine()
        with Session(engine) as session:
            conversation = session.get(Conversation, thread_id)
            if conversation is None:
                conversation = Conversation(id=thread_id, title=title or "新会话")
                session.add(conversation)
                session.commit()
                session.refresh(conversation)
            return self._conversation_payload(conversation)

    def add_message(
        self,
        thread_id: str,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict:
        engine = self._require_engine()
        now = utc_now()
        with Session(engine) as session:
            conversation = session.get(Conversation, thread_id)
            if conversation is None:
                conversation = Conversation(
                    id=thread_id,
                    title=self._make_title(content) if role == "user" else "新会话",
                    created_at=now,
                    updated_at=now,
                )
                session.add(conversation)
                session.flush()
            elif role == "user" and conversation.title == "新会话":
                conversation.title = self._make_title(content)

            conversation.updated_at = now
            message = ChatMessage(
                conversation_id=thread_id,
                role=role,
                content=content,
                message_metadata=metadata,
                created_at=now,
            )
            session.add(message)
            session.add(conversation)
            session.commit()
            session.refresh(message)
            return self._message_payload(message)

    def list_messages(self, thread_id: str) -> list[dict]:
        engine = self._require_engine()
        with Session(engine) as session:
            statement = (
                select(ChatMessage)
                .where(ChatMessage.conversation_id == thread_id)
                .order_by(ChatMessage.created_at, ChatMessage.id)
            )
            return [self._message_payload(message) for message in session.exec(statement).all()]

    def list_conversations(self, limit: int = 50) -> list[dict]:
        engine = self._require_engine()
        with Session(engine) as session:
            statement = select(Conversation).order_by(Conversation.updated_at.desc()).limit(limit)
            return [
                self._conversation_payload(conversation)
                for conversation in session.exec(statement).all()
            ]

    def _require_engine(self):
        if not self.available:
            raise RuntimeError(self.initialization_error or "MySQL conversation memory is unavailable")
        return self._engine

    @staticmethod
    def _make_title(content: str) -> str:
        compact = " ".join(content.strip().split())
        return compact[:80] or "新会话"

    @staticmethod
    def _conversation_payload(conversation: Conversation) -> dict:
        return {
            "id": conversation.id,
            "title": conversation.title,
            "created_at": conversation.created_at.isoformat(),
            "updated_at": conversation.updated_at.isoformat(),
        }

    @staticmethod
    def _message_payload(message: ChatMessage) -> dict:
        timestamp = message.created_at.replace(tzinfo=timezone.utc).timestamp() * 1000
        return {
            "id": message.id,
            "role": message.role,
            "content": message.content,
            "metadata": message.message_metadata,
            "timestamp": int(timestamp),
        }
