"""Native DeepAgents skill source registry."""

REMOTE_SKILLS_ROOT = "/home/daytona/skill-sources"


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
    "MAIN_AGENT_SKILLS",
    "RAGFLOW_AGENT_SKILLS",
    "REMOTE_SKILLS_ROOT",
    "SKILL_ASSIGNMENTS",
    "skill_source",
]
