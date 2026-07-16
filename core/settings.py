"""应用配置的统一读取、类型转换与校验入口。"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal
from urllib.parse import quote_plus

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class AppSettings(BaseSettings):
    """从项目根目录的 `.env` 和系统环境变量加载运行配置。"""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
        case_sensitive=False,
    )

    # 主模型配置
    openai_base_url: str | None = None
    openai_api_key: str | None = None
    llm_model: str = "deepseek-v4-pro"

    # 视觉与跨模态模型配置
    vision_base_url: str | None = None
    vision_api_key: str | None = None
    dashscope_api_key: str | None = None
    vision_model: str | None = None
    vision_max_image_mb: float = Field(default=10, gt=0)
    vision_request_timeout_seconds: float = Field(default=90, gt=0, le=600)

    # 长期记忆、Embedding 和 Reranker 配置
    milvus_uri: str = "http://127.0.0.1:19531"
    milvus_token: str | None = None
    milvus_memory_collection: str = "agent_long_term_memory"
    memory_vector_dimension: int = Field(default=512, ge=1)
    memory_min_similarity: float = Field(default=0.12, ge=-1, le=1)
    memory_embedding_provider: Literal["api", "vllm", "hash"] = "api"
    memory_embedding_base_url: str = (
        "https://dashscope.aliyuncs.com/compatible-mode/v1"
    )
    memory_embedding_api_key: str | None = None
    memory_embedding_model: str = "text-embedding-v4"
    memory_reranker_enabled: bool = True
    memory_reranker_provider: (
        Literal["api", "vllm", "none", "off", "disabled"] | None
    ) = None
    memory_reranker_endpoint: str = (
        "https://dashscope.aliyuncs.com/api/v1/services/rerank/"
        "text-rerank/text-rerank"
    )
    memory_reranker_api_key: str | None = None
    memory_reranker_model: str = "gte-rerank-v2"
    memory_inference_timeout_seconds: float = Field(default=30, gt=0, le=600)
    memory_allow_hash_fallback: bool = False
    vllm_embedding_base_url: str = "http://127.0.0.1:8001/v1"
    vllm_embedding_model: str = "BAAI/bge-small-zh-v1.5"
    vllm_embedding_api_key: str = "local-vllm"
    vllm_reranker_base_url: str = "http://127.0.0.1:8002/v1"
    vllm_reranker_model: str = "BAAI/bge-reranker-base"
    vllm_reranker_api_key: str = "local-vllm"
    vllm_inference_timeout_seconds: float = Field(default=30, gt=0, le=600)

    # MySQL 配置
    mysql_host: str = "127.0.0.1"
    mysql_port: int = Field(default=3306, ge=1, le=65535)
    mysql_user: str | None = None
    mysql_password: str | None = None
    mysql_database: str | None = None

    # Redis 短期记忆配置
    redis_checkpoint_url: str = "redis://127.0.0.1:6380"
    redis_checkpoint_ttl_minutes: int = Field(default=10080, ge=1)

    # RAGFlow 配置
    ragflow_api_url: str | None = None
    ragflow_api_key: str | None = None

    # Daytona 沙箱配置
    daytona_api_key: str | None = None
    daytona_api_url: str | None = None
    daytona_target: str | None = None
    daytona_command_timeout_seconds: int = Field(default=1800, ge=1)
    daytona_auto_stop_minutes: int = Field(default=60, ge=1)
    daytona_create_retries: int = Field(default=3, ge=1, le=10)
    daytona_retry_delay_seconds: float = Field(default=1.0, ge=0, le=60)

    # Phoenix 链路观测配置
    phoenix_tracing_enabled: bool = False
    phoenix_collector_endpoint: str = "http://127.0.0.1:6006/v1/traces"
    phoenix_project_name: str = "omniresearch"
    phoenix_capture_content: bool = True
    phoenix_export_timeout_seconds: float = Field(default=10.0, gt=0, le=300)
    app_environment: str = "development"

    # 离线自动评测配置
    evaluation_dataset_path: str = "evaluation/datasets/cases.jsonl"
    evaluation_output_dir: str = "output/evaluation"
    evaluation_user_id: str = "evaluation"
    evaluation_llm_model: str | None = None
    evaluation_llm_base_url: str | None = None
    evaluation_llm_api_key: str | None = None
    evaluation_llm_max_tokens: int = Field(default=8192, ge=256, le=65536)
    evaluation_embedding_model: str | None = None
    evaluation_embedding_base_url: str | None = None
    evaluation_embedding_api_key: str | None = None
    evaluation_phoenix_base_url: str = "http://127.0.0.1:6006"
    evaluation_phoenix_api_key: str | None = None
    evaluation_publish_to_phoenix: bool = False

    # API、联网搜索、Skill 和文档配置
    api_auth_enabled: bool = True
    api_auth_secret: str = "deep-agent-dev-secret-change-me"
    api_token_expire_minutes: int = Field(default=120, ge=1)
    api_admin_username: str = "admin"
    api_admin_password: str = "admin123456"
    api_seed_demo_users: bool = True
    api_rate_limit_requests: int = Field(default=120, ge=1)
    api_rate_limit_window_seconds: int = Field(default=60, ge=1)
    conversation_legacy_user_id: str | None = None
    tavily_api_key: str | None = None
    github_token: str | None = None
    skill_allow_executable_files: bool = False
    typst_font_paths: str = ""

    @field_validator(
        "openai_base_url",
        "vision_base_url",
        "memory_embedding_base_url",
        "memory_reranker_endpoint",
        "vllm_embedding_base_url",
        "vllm_reranker_base_url",
        "ragflow_api_url",
        "daytona_api_url",
        "phoenix_collector_endpoint",
        "evaluation_llm_base_url",
        "evaluation_embedding_base_url",
        "evaluation_phoenix_base_url",
    )
    @classmethod
    def validate_http_url(cls, value: str | None) -> str | None:
        """校验项目中的 HTTP 服务地址，避免把无效地址带到运行阶段。"""
        if value is None:
            return None
        normalized = value.strip().rstrip("/")
        if not normalized.startswith(("http://", "https://")):
            raise ValueError("服务地址必须以 http:// 或 https:// 开头")
        return normalized

    @field_validator("redis_checkpoint_url")
    @classmethod
    def validate_redis_url(cls, value: str) -> str:
        """限制检查点存储使用 Redis 协议。"""
        normalized = value.strip()
        if not normalized.startswith(("redis://", "rediss://")):
            raise ValueError("REDIS_CHECKPOINT_URL 必须使用 redis:// 或 rediss://")
        return normalized

    @field_validator(
        "llm_model",
        "mysql_host",
        "phoenix_project_name",
        "app_environment",
        "evaluation_dataset_path",
        "evaluation_output_dir",
        "evaluation_user_id",
    )
    @classmethod
    def validate_non_empty(cls, value: str) -> str:
        """拒绝关键名称配置为空字符串。"""
        normalized = value.strip()
        if not normalized:
            raise ValueError("配置值不能为空")
        return normalized

    def require_model_credentials(self) -> tuple[str, str, str]:
        """返回主模型配置，并在真正创建模型时检查凭据。"""
        if not self.openai_base_url or not self.openai_api_key:
            raise ValueError("未配置 OPENAI_BASE_URL 或 OPENAI_API_KEY")
        return self.llm_model, self.openai_base_url, self.openai_api_key

    def evaluation_llm_credentials(self) -> tuple[str, str, str]:
        """返回评测裁判模型配置，未单独配置时复用主模型。"""
        model = self.evaluation_llm_model or self.llm_model
        base_url = self.evaluation_llm_base_url or self.openai_base_url
        api_key = self.evaluation_llm_api_key or self.openai_api_key
        if not base_url or not api_key:
            raise ValueError(
                "未配置 EVALUATION_LLM_BASE_URL/EVALUATION_LLM_API_KEY，"
                "且无法复用主模型配置"
            )
        return model, base_url, api_key

    def evaluation_embedding_credentials(self) -> tuple[str, str, str] | None:
        """返回回答相关性评测使用的 Embedding；未配置时跳过该指标。"""
        model = self.evaluation_embedding_model or self.memory_embedding_model
        base_url = self.evaluation_embedding_base_url or self.memory_embedding_base_url
        api_key = (
            self.evaluation_embedding_api_key
            or self.memory_embedding_api_key
            or self.dashscope_api_key
        )
        if not model or not base_url or not api_key:
            return None
        return model, base_url, api_key

    def require_vision_credentials(self) -> tuple[str, str, str]:
        """解析视觉模型配置，并允许复用主模型服务。"""
        if not self.vision_model:
            raise ValueError("未配置 VISION_MODEL")
        base_url = self.vision_base_url or self.openai_base_url
        api_key = self.vision_api_key or self.dashscope_api_key or self.openai_api_key
        if not base_url:
            raise ValueError("未配置 VISION_BASE_URL 或 OPENAI_BASE_URL")
        if not api_key:
            if base_url.startswith(("http://127.0.0.1", "http://localhost")):
                api_key = "local-vllm"
            else:
                raise ValueError("未配置 VISION_API_KEY、DASHSCOPE_API_KEY 或 OPENAI_API_KEY")
        return self.vision_model, base_url, api_key

    def memory_embedding_api_key_value(self) -> str:
        """返回长期记忆向量服务使用的 API 密钥。"""
        return self._first_api_key(
            self.memory_embedding_api_key,
            self.dashscope_api_key,
            self.vision_api_key,
            names="MEMORY_EMBEDDING_API_KEY、DASHSCOPE_API_KEY、VISION_API_KEY",
        )

    def memory_reranker_api_key_value(self) -> str:
        """返回长期记忆重排服务使用的 API 密钥。"""
        return self._first_api_key(
            self.memory_reranker_api_key,
            self.dashscope_api_key,
            self.vision_api_key,
            names="MEMORY_RERANKER_API_KEY、DASHSCOPE_API_KEY、VISION_API_KEY",
        )

    @staticmethod
    def _first_api_key(*values: str | None, names: str) -> str:
        for value in values:
            if value and value.strip():
                return value.strip()
        raise ValueError(f"未配置以下任一 API 密钥：{names}")

    def mysql_url(self) -> str:
        """生成转义后的 SQLAlchemy MySQL 连接地址。"""
        if not self.mysql_user or not self.mysql_password or not self.mysql_database:
            raise ValueError(
                "未配置 MYSQL_USER、MYSQL_PASSWORD 或 MYSQL_DATABASE"
            )
        user = quote_plus(self.mysql_user)
        password = quote_plus(self.mysql_password)
        database = quote_plus(self.mysql_database)
        return (
            f"mysql+mysqlconnector://{user}:{password}@"
            f"{self.mysql_host}:{self.mysql_port}/{database}?charset=utf8mb4"
        )

    def require_ragflow(self) -> tuple[str, str]:
        """返回 RAGFlow 凭据，并在功能启用时检查完整性。"""
        if not self.ragflow_api_key or not self.ragflow_api_url:
            raise ValueError("未配置 RAGFLOW_API_KEY 或 RAGFLOW_API_URL")
        return self.ragflow_api_key, self.ragflow_api_url

    def require_daytona_api_key(self) -> str:
        """返回 Daytona 密钥，并在创建远程沙箱时检查配置。"""
        if not self.daytona_api_key:
            raise ValueError("DAYTONA_API_KEY is not configured")
        return self.daytona_api_key

    def typst_font_directories(self) -> list[Path]:
        """解析当前操作系统格式的 Typst 字体目录列表。"""
        return [
            Path(item).expanduser().resolve()
            for item in self.typst_font_paths.split(os.pathsep)
            if item.strip()
        ]


def get_settings() -> AppSettings:
    """创建配置快照；便于测试时临时覆盖环境变量。"""
    return AppSettings()


__all__ = ["AppSettings", "PROJECT_ROOT", "get_settings"]
