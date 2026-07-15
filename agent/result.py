from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentRunResult:
    """Final Agent text plus structured artifacts that must survive refresh."""

    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
