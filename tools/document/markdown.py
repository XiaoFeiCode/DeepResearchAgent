from pathlib import Path
from typing import Annotated

from langchain_core.tools import tool

from api.context import get_session_context
from api.monitor import monitor
from core.paths import resolve_path


@tool
def generate_markdown(
    content: Annotated[str, "要写入 Markdown 文档的文本内容"],
    filename: Annotated[str, "Markdown 文档文件名，可省略 .md 后缀"],
    path: Annotated[str, "文件保存目录"] = "",
) -> str:
    """根据给定内容生成 Markdown 文件。"""
    monitor.report_tool("Markdown文档生成工具", {"写入的文本内容": content})
    if not filename.endswith(".md"):
        filename += ".md"

    session_dir = get_session_context()
    if path and path != ".":
        full_input_path = str(Path(path) / filename)
    else:
        full_input_path = filename
    file_path = Path(resolve_path(full_input_path, session_dir))

    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        return f"Markdown文件 '{file_path}' 已成功生成并保存。"
    except OSError as error:
        return f"生成 Markdown 文件失败: {error}"
