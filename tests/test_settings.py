import unittest
from unittest.mock import patch

from pydantic import ValidationError

from core.settings import AppSettings


class SettingsTests(unittest.TestCase):
    def test_mysql_url_escapes_credentials(self):
        with patch.dict("os.environ", {}, clear=True):
            settings = AppSettings(
                _env_file=None,
                mysql_user="root@local",
                mysql_password="p:a/ss",
                mysql_database="agent data",
            )

        self.assertEqual(
            settings.mysql_url(),
            "mysql+mysqlconnector://root%40local:p%3Aa%2Fss@"
            "127.0.0.1:3306/agent+data?charset=utf8mb4",
        )

    def test_invalid_redis_url_is_rejected(self):
        with self.assertRaises(ValidationError):
            AppSettings(_env_file=None, redis_checkpoint_url="http://localhost:6379")

    def test_environment_variables_override_defaults(self):
        with patch.dict(
            "os.environ",
            {
                "REDIS_CHECKPOINT_TTL_MINUTES": "60",
                "PHOENIX_TRACING_ENABLED": "true",
                "MYSQL_PORT": "3307",
            },
            clear=True,
        ):
            settings = AppSettings(_env_file=None)

        self.assertEqual(settings.redis_checkpoint_ttl_minutes, 60)
        self.assertTrue(settings.phoenix_tracing_enabled)
        self.assertEqual(settings.mysql_port, 3307)

    def test_optional_service_credentials_are_checked_on_demand(self):
        with patch.dict("os.environ", {}, clear=True):
            settings = AppSettings(_env_file=None)

        with self.assertRaisesRegex(ValueError, "RAGFLOW_API_KEY"):
            settings.require_ragflow()
        with self.assertRaisesRegex(ValueError, "DAYTONA_API_KEY"):
            settings.require_daytona_api_key()

    def test_evaluation_models_fall_back_to_main_model_configuration(self):
        settings = AppSettings(
            _env_file=None,
            llm_model="judge-model",
            openai_base_url="https://model.example.com/v1",
            openai_api_key="secret",
            memory_embedding_model="embedding-model",
            memory_embedding_base_url="https://embedding.example.com/v1",
            memory_embedding_api_key="embedding-secret",
        )

        self.assertEqual(
            settings.evaluation_llm_credentials(),
            ("judge-model", "https://model.example.com/v1", "secret"),
        )
        self.assertEqual(
            settings.evaluation_embedding_credentials(),
            (
                "embedding-model",
                "https://embedding.example.com/v1",
                "embedding-secret",
            ),
        )


if __name__ == "__main__":
    unittest.main()
