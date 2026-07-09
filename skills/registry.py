"""Native DeepAgents skill source registry."""

import hashlib
from pathlib import Path

REMOTE_SKILLS_ROOT = "/home/daytona/skill-sources"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
INSTALLED_SKILLS_ROOT = PROJECT_ROOT / "runtime" / "installed_skills"

SKILL_TARGETS = {
    "main": "main",
    "database": "database",
    "ragflow": "ragflow",
    "internet": "internet",
}


def user_skill_storage_key(user_id: str) -> str:
    """Map a user identity to a filesystem-safe, non-identifying directory key."""
    return hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:24]


def skill_source(group: str) -> str:
    """Return a Daytona-backed source containing skill subdirectories."""
    return f"{REMOTE_SKILLS_ROOT}/{group}/"


SKILL_ASSIGNMENTS = {
    "main": [
        "structured-data-query",
        "ragflow-knowledge-base",
        "web-research",
        "document-generation",
        "long-term-memory",
    ],
    "database": ["database-query"],
    "ragflow": ["ragflow-knowledge-base"],
    "internet": ["web-research"],
}

MAIN_AGENT_SKILLS = [skill_source("main")]
DATABASE_AGENT_SKILLS = [skill_source("database")]
RAGFLOW_AGENT_SKILLS = [skill_source("ragflow")]
INTERNET_AGENT_SKILLS = [skill_source("internet")]


__all__ = [
    "DATABASE_AGENT_SKILLS",
    "INTERNET_AGENT_SKILLS",
    "INSTALLED_SKILLS_ROOT",
    "MAIN_AGENT_SKILLS",
    "PROJECT_ROOT",
    "RAGFLOW_AGENT_SKILLS",
    "REMOTE_SKILLS_ROOT",
    "SKILL_ASSIGNMENTS",
    "SKILL_TARGETS",
    "skill_source",
    "user_skill_storage_key",
]
