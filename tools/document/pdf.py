import logging
from pathlib import Path

try:
    from typing import Annotated, Optional
except ImportError:
    from typing_extensions import Annotated, Optional

from langchain_core.tools import tool
from api.monitor import monitor
from api.context import get_session_context
from tools.document.typst_renderer import convert_markdown_to_pdf
from core.paths import resolve_path


@tool
def convert_md_to_pdf(
    md_filename: Annotated[str, "要转换的Markdown文档路径（包含.md后缀）"],
    pdf_filename: Annotated[
        Optional[str], "输出的PDF文件路径（可选，默认与源文件同名）"
    ] = None,
) -> str:
    """
    使用 Typst 模板将 Markdown 文档转换为 PDF。

    支持标题、段落、列表、引用、代码块、链接、图片和表格，且不依赖
    Microsoft Word，可在 Windows、Linux、Docker 和 Daytona 环境运行。
    """
    monitor.report_tool("Typst PDF 生成工具", {"md_filename": md_filename})

    try:
        # 1. 路径预处理
        session_dir = get_session_context()
        md_path = Path(md_filename).with_suffix(".md")
        md_abs_path = Path(resolve_path(str(md_path), session_dir))

        # 2. 检查源文件
        if not md_abs_path.exists():
            return f"错误：文件不存在 {md_abs_path}"

        # 3. 确定输出路径
        if pdf_filename:
            pdf_path = Path(pdf_filename).with_suffix(".pdf")
            pdf_abs_path = Path(resolve_path(str(pdf_path), session_dir))
        else:
            pdf_abs_path = md_abs_path.with_suffix(".pdf")

        # 4. 调用 Typst 渲染器。模板和内容解析与 Tool 层保持分离。
        generated_path = convert_markdown_to_pdf(md_abs_path, pdf_abs_path)
        return f"成功生成 PDF: {generated_path} (Typst 引擎)"

    except Exception as e:
        logging.error(f"转换失败: {e}", exc_info=True)
        return f"转换失败: {str(e)}"


__all__ = ["convert_md_to_pdf"]
