"""使用 Typst 把 Markdown 报告渲染为 PDF。"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import unquote, urlparse

import typst
from markdown_it import MarkdownIt
from markdown_it.tree import SyntaxTreeNode

from core.settings import get_settings


TEMPLATE_PATH = Path(__file__).with_name("templates") / "report.typ"


class TypstRenderError(RuntimeError):
    """Markdown 报告无法转换为有效 PDF 时抛出。"""


def _typst_string(value: str) -> str:
    """返回经过安全转义的 Typst 字符串字面量。"""
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\n", "\\n")
        .replace("\t", "\\t")
    )
    return f'"{escaped}"'


class MarkdownTypstRenderer:
    """把 markdown-it 语法树转换为安全的 Typst 标记。"""

    def __init__(self, source_dir: Path) -> None:
        self.source_dir = source_dir.resolve()
        self.parser = MarkdownIt("commonmark", {"html": False}).enable("table")

    def render(self, markdown_text: str, fallback_title: str) -> str:
        root = SyntaxTreeNode(self.parser.parse(markdown_text))
        title = self._document_title(root) or fallback_title
        body = self._render_children(root)
        template = TEMPLATE_PATH.read_text(encoding="utf-8")
        return template.replace(
            "{{DOCUMENT_TITLE}}",
            _typst_string(title),
        ).replace("{{DOCUMENT_CONTENT}}", body)

    def _document_title(self, root: SyntaxTreeNode) -> str:
        for node in root.children:
            if node.type == "heading" and node.tag == "h1":
                return self._plain_text(node).strip()
        return ""

    def _plain_text(self, node: SyntaxTreeNode) -> str:
        if node.type in {"text", "code_inline", "code_block", "fence"}:
            return node.content
        return "".join(self._plain_text(child) for child in node.children)

    def _render_children(self, node: SyntaxTreeNode) -> str:
        rendered = [self._render_node(child) for child in node.children]
        return "\n\n".join(part for part in rendered if part.strip())

    def _render_inline_children(self, node: SyntaxTreeNode) -> str:
        return "".join(self._render_inline(child) for child in node.children)

    def _render_inline(self, node: SyntaxTreeNode) -> str:
        node_type = node.type
        if node_type in {"text", "text_special"}:
            return f"#text({_typst_string(node.content)})"
        if node_type == "inline":
            return self._render_inline_children(node)
        if node_type == "strong":
            return f"#strong[{self._render_inline_children(node)}]"
        if node_type == "em":
            return f"#emph[{self._render_inline_children(node)}]"
        if node_type in {"s", "del"}:
            return f"#strike[{self._render_inline_children(node)}]"
        if node_type == "code_inline":
            return (
                '#box(fill: rgb("#F2F4F7"), inset: (x: 4pt, y: 1pt), '
                f"radius: 3pt)[#raw({_typst_string(node.content)})]"
            )
        if node_type == "link":
            href = str(node.attrs.get("href", ""))
            return f"#link({_typst_string(href)})[{self._render_inline_children(node)}]"
        if node_type == "image":
            return self._render_image(node)
        if node_type == "softbreak":
            return " "
        if node_type == "hardbreak":
            return "#linebreak()"
        if node.children:
            return self._render_inline_children(node)
        if node.content:
            return f"#text({_typst_string(node.content)})"
        return ""

    def _render_node(self, node: SyntaxTreeNode) -> str:
        node_type = node.type
        if node_type == "inline":
            return self._render_inline_children(node)
        if node_type == "paragraph":
            return self._render_children_or_inline(node)
        if node_type == "heading":
            level = int(node.tag.removeprefix("h") or "1")
            return f"#heading(level: {level})[{self._render_children_or_inline(node)}]"
        if node_type == "bullet_list":
            return self._render_list(node, ordered=False)
        if node_type == "ordered_list":
            return self._render_list(node, ordered=True)
        if node_type == "blockquote":
            return f"#quote(block: true, quotes: false)[{self._render_children(node)}]"
        if node_type in {"fence", "code_block"}:
            language = node.info.strip().split(maxsplit=1)[0] if node.info else ""
            language_arg = f", lang: {_typst_string(language)}" if language else ""
            return (
                '#block(width: 100%, fill: rgb("#F6F7F9"), '
                "inset: 10pt, radius: 5pt, breakable: true)"
                f"[#raw({_typst_string(node.content)}, block: true{language_arg})]"
            )
        if node_type == "table":
            return self._render_table(node)
        if node_type == "hr":
            return '#line(length: 100%, stroke: 0.6pt + rgb("#D9DDE3"))'
        if node_type in {"html_block", "html_inline"}:
            return f"#raw({_typst_string(node.content)}, block: true)"
        if node.children:
            return self._render_children(node)
        if node.content:
            return f"#text({_typst_string(node.content)})"
        return ""

    def _render_children_or_inline(self, node: SyntaxTreeNode) -> str:
        if len(node.children) == 1 and node.children[0].type == "inline":
            return self._render_inline_children(node.children[0])
        return self._render_children(node)

    def _render_list(self, node: SyntaxTreeNode, *, ordered: bool) -> str:
        items = [child for child in node.children if child.type == "list_item"]
        rendered_items = []
        for item in items:
            content = self._render_children(item)
            rendered_items.append(f"  [{content}]")
        function_name = "enum" if ordered else "list"
        return f"#{function_name}(\n" + ",\n".join(rendered_items) + "\n)"

    def _render_table(self, node: SyntaxTreeNode) -> str:
        header_rows: list[list[SyntaxTreeNode]] = []
        body_rows: list[list[SyntaxTreeNode]] = []
        for section in node.children:
            target = header_rows if section.type == "thead" else body_rows
            for row in section.children:
                if row.type == "tr":
                    target.append(
                        [cell for cell in row.children if cell.type in {"th", "td"}]
                    )

        rows = header_rows + body_rows
        column_count = max((len(row) for row in rows), default=1)

        def render_cell(cell: SyntaxTreeNode, *, header: bool = False) -> str:
            content = self._render_children_or_inline(cell)
            if header:
                content = f"#strong[{content}]"
            return f"[{content}]"

        table_parts = [
            "#table(",
            f"  columns: {column_count},",
            "  inset: (x: 7pt, y: 6pt),",
            '  stroke: 0.6pt + rgb("#D9DDE3"),',
            '  fill: (x, y) => if y == 0 { rgb("#F3F5F8") } else { none },',
            "  align: left + top,",
        ]
        if header_rows:
            header_cells = [
                render_cell(cell, header=True) for row in header_rows for cell in row
            ]
            table_parts.append(
                "  table.header(\n    " + ",\n    ".join(header_cells) + "\n  ),"
            )
        body_cells = [render_cell(cell) for row in body_rows for cell in row]
        if body_cells:
            table_parts.append("  " + ",\n  ".join(body_cells) + ",")
        table_parts.append(")")
        return "\n".join(table_parts)

    def _render_image(self, node: SyntaxTreeNode) -> str:
        source = unquote(str(node.attrs.get("src", "")))
        alt_text = self._plain_text(node).strip() or str(node.attrs.get("alt", "图片"))
        parsed = urlparse(source)
        if parsed.scheme in {"http", "https"}:
            return f"#link({_typst_string(source)})[#emph[{self._text(alt_text)}]]"

        image_path = (self.source_dir / source).resolve()
        if not image_path.is_file() or (
            image_path != self.source_dir and self.source_dir not in image_path.parents
        ):
            return f"#emph[{self._text(f'[图片不可用: {alt_text}]')}]"
        relative_path = image_path.relative_to(self.source_dir).as_posix()
        return (
            "#figure(\n"
            f"  image({_typst_string(relative_path)}, width: 88%),\n"
            f"  caption: [{self._text(alt_text)}],\n"
            ")"
        )

    @staticmethod
    def _text(value: str) -> str:
        return f"#text({_typst_string(value)})"


def convert_markdown_to_pdf(md_path: Path, pdf_path: Path) -> Path:
    """使用共享 Typst 报告模板把 Markdown 文件渲染为 PDF。"""
    md_path = md_path.resolve()
    pdf_path = pdf_path.resolve()
    if not md_path.is_file():
        raise TypstRenderError(f"Markdown 文件不存在: {md_path}")

    markdown_text = md_path.read_text(encoding="utf-8")
    renderer = MarkdownTypstRenderer(md_path.parent)
    typst_source = renderer.render(markdown_text, fallback_title=md_path.stem)
    pdf_path.parent.mkdir(parents=True, exist_ok=True)

    compile_options: dict[str, object] = {
        "input": typst_source.encode("utf-8"),
        "output": str(pdf_path),
        "root": str(md_path.parent),
    }
    configured_font_paths = get_settings().typst_font_directories()
    if configured_font_paths:
        compile_options["font_paths"] = [str(path) for path in configured_font_paths]

    try:
        typst.compile(**compile_options)
    except Exception as error:
        raise TypstRenderError(f"Typst 编译失败: {error}") from error

    if not pdf_path.is_file() or pdf_path.stat().st_size < 5:
        raise TypstRenderError(f"Typst 未生成有效 PDF: {pdf_path}")
    if not pdf_path.read_bytes().startswith(b"%PDF"):
        raise TypstRenderError(f"Typst 输出不是有效 PDF: {pdf_path}")
    return pdf_path
