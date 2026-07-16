from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentRunResult:
    """Agent 最终文本和需要跨页面刷新保留的结构化元数据。"""

    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
