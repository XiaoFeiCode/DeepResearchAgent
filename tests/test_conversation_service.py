from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from sqlalchemy import create_engine, inspect, text
from sqlmodel import SQLModel

from api.services.conversation_service import (
    ConversationAccessError,
    ConversationService,
)


class ConversationServiceTests(unittest.TestCase):
    def _create_service(self, database_path: Path) -> ConversationService:
        engine = create_engine(
            f"sqlite:///{database_path.as_posix()}",
            connect_args={"check_same_thread": False},
        )
        SQLModel.metadata.create_all(engine)
        service = ConversationService()
        service._engine = engine
        service.initialization_error = None
        return service

    def test_conversations_and_messages_are_user_scoped(self):
        with TemporaryDirectory() as temporary_root:
            service = self._create_service(Path(temporary_root) / "conversations.db")
            try:
                service.create_conversation("thread-1", "alice", "Alice conversation")
                service.add_message("thread-1", "alice", "user", "hello")

                self.assertEqual(len(service.list_conversations("alice")), 1)
                self.assertEqual(service.list_conversations("bob"), [])
                self.assertEqual(service.list_messages("thread-1", "alice")[0]["content"], "hello")

                with self.assertRaises(ConversationAccessError):
                    service.list_messages("thread-1", "bob")
                with self.assertRaises(ConversationAccessError):
                    service.create_conversation("thread-1", "bob")
                with self.assertRaises(ConversationAccessError):
                    service.add_message("thread-1", "bob", "user", "unauthorized")

                service.delete_conversation("thread-1", "alice")
                self.assertEqual(service.list_conversations("alice"), [])
                with self.assertRaises(ConversationAccessError):
                    service.list_messages("thread-1", "alice")
            finally:
                service._engine.dispose()

    def test_migrates_legacy_conversations_to_configured_user(self):
        with TemporaryDirectory() as temporary_root:
            database_path = Path(temporary_root) / "legacy.db"
            engine = create_engine(f"sqlite:///{database_path.as_posix()}")
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "CREATE TABLE agent_conversations ("
                        "id VARCHAR(64) PRIMARY KEY, "
                        "title VARCHAR(255) NOT NULL, "
                        "created_at DATETIME NOT NULL, "
                        "updated_at DATETIME NOT NULL)"
                    )
                )
                connection.execute(
                    text(
                        "INSERT INTO agent_conversations "
                        "(id, title, created_at, updated_at) "
                        "VALUES ('legacy-thread', 'Legacy', :now, :now)"
                    ),
                    {"now": now},
                )

            service = ConversationService()
            service._engine = engine
            service.initialization_error = None
            with patch.dict(
                "os.environ",
                {"CONVERSATION_LEGACY_USER_ID": "legacy-owner"},
            ):
                service._migrate_conversation_schema()

            try:
                columns = {
                    column["name"]
                    for column in inspect(engine).get_columns("agent_conversations")
                }
                self.assertIn("user_id", columns)
                self.assertEqual(
                    service.list_conversations("legacy-owner")[0]["id"],
                    "legacy-thread",
                )
                self.assertEqual(service.list_conversations("other-user"), [])
            finally:
                engine.dispose()

    def test_mysql_charset_migration_converts_only_incompatible_tables(self):
        connection = Mock()
        first_result = Mock()
        first_result.scalar_one.return_value = 1
        second_result = Mock()
        second_result.scalar_one.return_value = 0
        connection.execute.side_effect = [
            first_result,
            second_result,
            Mock(),
            Mock(),
            Mock(),
        ]

        ConversationService._ensure_mysql_utf8mb4(
            connection,
            {"agent_conversations", "agent_messages", "unmanaged_table"},
        )

        statements = [str(call.args[0]) for call in connection.execute.call_args_list]
        self.assertEqual(len(statements), 5)
        self.assertIn("information_schema.COLUMNS", statements[0])
        self.assertIn("information_schema.COLUMNS", statements[1])
        self.assertEqual(statements[2], "SET FOREIGN_KEY_CHECKS = 0")
        self.assertIn("ALTER TABLE `agent_messages`", statements[3])
        self.assertEqual(statements[4], "SET FOREIGN_KEY_CHECKS = 1")
        self.assertFalse(any("unmanaged_table" in statement for statement in statements))


if __name__ == "__main__":
    unittest.main()
