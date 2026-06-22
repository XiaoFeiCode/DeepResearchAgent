from pathlib import Path


def load_project_skills() -> str:
    """
    加载项目内的 SKILL.md 文件，并拼成可注入主智能体的提示词。

    这里实现的是项目自己的轻量 Skill 机制：
    - skills/<skill-name>/SKILL.md 存放提示词式能力说明。
    - 启动主智能体时统一加载。
    """
    skills_root = Path(__file__).resolve().parent
    skill_files = sorted(skills_root.glob("*/SKILL.md"))
    sections = []

    for skill_file in skill_files:
        text = skill_file.read_text(encoding="utf-8").strip()
        if not text:
            continue

        sections.append(
            f"【项目 Skill: {skill_file.parent.name}】\n"
            f"{text}"
        )

    if not sections:
        return ""

    return "\n\n".join(
        [
            "以下是本项目内置的 Skill 说明。遇到匹配任务时，优先按照对应 Skill 的流程执行。",
            *sections,
        ]
    )


__all__ = ["load_project_skills"]
