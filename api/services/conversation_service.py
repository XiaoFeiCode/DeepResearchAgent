import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Column, JSON, Text, delete, inspect, text
from sqlmodel import Field, Session, SQLModel, select

from core.settings import get_settings
from tools.database.mysql import get_engine

logger = logging.getLogger(__name__)


class ConversationAccessError(LookupError):
    """会话不属于当前用户时抛出。"""


def utc_now() -> datetime:
    """生成适合 MySQL DATETIME 保存的 UTC 时间。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Conversation(SQLModel, table=True):
    __tablename__ = "agent_conversations"

    id: str = Field(primary_key=True, max_length=64)
    user_id: str = Field(max_length=64, nullable=False, index=True)
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
            self._migrate_conversation_schema()
            self.initialization_error = None
        except Exception as error:
            self._engine = None
            self.initialization_error = str(error)
            logger.warning("MySQL conversation memory is unavailable: %s", error)

    def create_conversation(
        self,
        thread_id: str,
        user_id: str,
        title: str | None = None,
    ) -> dict:
        engine = self._require_engine()
        with Session(engine) as session:
            conversation = session.get(Conversation, thread_id)
            if conversation is None:
                conversation = Conversation(
                    id=thread_id,
                    user_id=user_id,
                    title=title or "新会话",
                )
                session.add(conversation)
                session.commit()
                session.refresh(conversation)
            elif conversation.user_id != user_id:
                raise ConversationAccessError("Conversation not found")
            return self._conversation_payload(conversation)

    def add_message(
        self,
        thread_id: str,
        user_id: str,
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
                    user_id=user_id,
                    title=self._make_title(content) if role == "user" else "新会话",
                    created_at=now,
                    updated_at=now,
                )
                session.add(conversation)
                session.flush()
            elif conversation.user_id != user_id:
                raise ConversationAccessError("Conversation not found")
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

    def list_messages(self, thread_id: str, user_id: str) -> list[dict]:
        engine = self._require_engine()
        with Session(engine) as session:
            conversation = session.get(Conversation, thread_id)
            if conversation is None or conversation.user_id != user_id:
                raise ConversationAccessError("Conversation not found")
            statement = (
                select(ChatMessage)
                .where(ChatMessage.conversation_id == thread_id)
                .order_by(ChatMessage.created_at, ChatMessage.id)
            )
            return [self._message_payload(message) for message in session.exec(statement).all()]

    def list_conversations(self, user_id: str, limit: int = 50) -> list[dict]:
        engine = self._require_engine()
        with Session(engine) as session:
            statement = (
                select(Conversation)
                .where(Conversation.user_id == user_id)
                .order_by(Conversation.updated_at.desc())
                .limit(limit)
            )
            return [
                self._conversation_payload(conversation)
                for conversation in session.exec(statement).all()
            ]

    def delete_conversation(self, thread_id: str, user_id: str) -> None:
        """删除当前用户的会话及其全部消息。"""
        engine = self._require_engine()
        with Session(engine) as session:
            conversation = session.get(Conversation, thread_id)
            if conversation is None or conversation.user_id != user_id:
                raise ConversationAccessError("Conversation not found")

            session.exec(
                delete(ChatMessage).where(ChatMessage.conversation_id == thread_id)
            )
            session.delete(conversation)
            session.commit()

    def _require_engine(self):
        if not self.available:
            raise RuntimeError(self.initialization_error or "MySQL conversation memory is unavailable")
        return self._engine

    def _migrate_conversation_schema(self) -> None:
        """升级旧版会话表的用户归属和 Unicode 字符集。"""
        engine = self._engine
        if engine is None:
            raise RuntimeError("MySQL conversation memory is unavailable")
        schema = inspect(engine)
        table_names = set(schema.get_table_names())
        if "agent_conversations" not in table_names:
            return

        columns = {column["name"] for column in schema.get_columns("agent_conversations")}
        dialect = engine.dialect.name
        with engine.begin() as connection:
            if "user_id" not in columns:
                settings = get_settings()
                legacy_user = (
                    settings.conversation_legacy_user_id
                    or settings.api_admin_username
                )[:64]
                if dialect == "mysql":
                    connection.execute(
                        text(
                            "ALTER TABLE agent_conversations "
                            "ADD COLUMN user_id VARCHAR(64) NULL"
                        )
                    )
                    connection.execute(
                        text(
                            "UPDATE agent_conversations "
                            "SET user_id = :legacy_user WHERE user_id IS NULL"
                        ),
                        {"legacy_user": legacy_user},
                    )
                    connection.execute(
                        text(
                            "ALTER TABLE agent_conversations "
                            "MODIFY COLUMN user_id VARCHAR(64) NOT NULL"
                        )
                    )
                else:
                    connection.execute(
                        text(
                            "ALTER TABLE agent_conversations "
                            "ADD COLUMN user_id VARCHAR(64) NOT NULL "
                            "DEFAULT 'admin'"
                        )
                    )
                    connection.execute(
                        text("UPDATE agent_conversations SET user_id = :legacy_user"),
                        {"legacy_user": legacy_user},
                    )
                connection.execute(
                    text(
                        "CREATE INDEX ix_agent_conversations_user_id "
                        "ON agent_conversations (user_id)"
                    )
                )

            if dialect == "mysql":
                self._ensure_mysql_utf8mb4(connection, table_names)

    @staticmethod
    def _ensure_mysql_utf8mb4(connection, table_names: set[str]) -> None:
        """仅转换无法保存四字节 Unicode 字符的旧文本列。"""
        # 暂停外键检查后先转换子表再转换父表，避免 MySQL 因临时字符集不一致而拒绝转换。
        managed_tables = ("agent_messages", "agent_conversations")
        incompatible_tables: list[str] = []
        for table_name in managed_tables:
            if table_name not in table_names:
                continue
            incompatible_columns = connection.execute(
                text(
                    "SELECT COUNT(*) FROM information_schema.COLUMNS "
                    "WHERE TABLE_SCHEMA = DATABASE() "
                    "AND TABLE_NAME = :table_name "
                    "AND CHARACTER_SET_NAME IS NOT NULL "
                    "AND CHARACTER_SET_NAME <> 'utf8mb4'"
                ),
                {"table_name": table_name},
            ).scalar_one()
            if incompatible_columns:
                incompatible_tables.append(table_name)

        if not incompatible_tables:
            return

        connection.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        try:
            for table_name in incompatible_tables:
                connection.execute(
                    text(
                        f"ALTER TABLE `{table_name}` CONVERT TO CHARACTER SET utf8mb4 "
                        "COLLATE utf8mb4_unicode_ci"
                    )
                )
        finally:
            connection.execute(text("SET FOREIGN_KEY_CHECKS = 1"))

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
