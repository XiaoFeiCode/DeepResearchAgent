from pathlib import Path
from typing import Annotated

from langchain_core.tools import tool

from api.context import get_session_context
from api.monitor import monitor
from core.paths import resolve_path

# 尝试导入可选依赖，实现按需加载
try:
    import docx
except ImportError:
    docx = None

try:
    import pypdf
except ImportError:
    pypdf = None

try:
    import pandas as pd
except ImportError:
    pd = None


@tool
def read_file_content(
    filename: Annotated[str, "要读取的文件名或路径（支持 .md、.docx、.pdf、.xlsx、.xls）"],
    instruction: Annotated[str, "内容提取要求，例如提取摘要或统计数据"] = "提取全部内容",
) -> str:
    """
    读取指定文件的内容。支持 Markdown(.md)、Word(.docx)、PDF(.pdf) 和 Excel(.xlsx/.xls)。
    对于 Excel 文件，会自动提供数据统计信息（head 和 describe）。
    """
    monitor.report_tool("文件内容读取工具", {"filename": filename, "instruction": instruction})

    session_dir = get_session_context()
    file_path = Path(resolve_path(filename, session_dir))

    if not file_path.exists():
        return f"错误：文件 '{filename}' 不存在 (解析路径: {file_path})。"

    ext = file_path.suffix.lower()

    try:
        if ext in [".md", ".txt"]:
            return file_path.read_text(encoding="utf-8")

        if ext == ".docx":
            if docx is None:
                return "错误：未安装 'python-docx' 库，无法读取 Word 文件。"
            doc = docx.Document(str(file_path))
            full_text = [para.text for para in doc.paragraphs]
            return "\n".join(full_text)

        if ext == ".pdf":
            if pypdf is None:
                return "错误：未安装 'pypdf' 库，无法读取 PDF 文件。"
            reader = pypdf.PdfReader(str(file_path))
            return "\n".join(page.extract_text() or "" for page in reader.pages)

        if ext in [".xlsx", ".xls"]:
            if pd is None:
                return "错误：未安装 'pandas' 库，无法读取 Excel 文件。"

            try:
                df = pd.read_excel(str(file_path))
            except Exception as error:
                return f"读取 Excel 失败: {error}"

            result = [
                f"文件: {filename}",
                f"行数: {len(df)}, 列数: {len(df.columns)}",
                f"列名: {', '.join(df.columns.astype(str))}",
                "\n[前5行数据预览]:",
                df.head().to_string(index=False),
                "\n[统计描述]:",
                df.describe().to_string(),
            ]
            return "\n".join(result)

        try:
            return file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return f"错误：不支持的文件格式 '{ext}'，且无法作为文本读取。"
    except Exception as error:
        return f"读取文件出错: {error}"
