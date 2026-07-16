"""集中加载主智能体和子智能体提示词配置。"""

from pathlib import Path
from typing import Any

import yaml

PROMPTS_PATH = Path(__file__).resolve().parent.parent / "prompt" / "prompts.yml"


def load_yaml(file_path: Path) -> dict[str, Any]:
    """使用安全加载器读取 YAML 配置文件。"""
    with file_path.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file)


prompts = load_yaml(PROMPTS_PATH)

main_agent_config = prompts["main_agent"]
sub_agent_configs = prompts["sub_agents"]
