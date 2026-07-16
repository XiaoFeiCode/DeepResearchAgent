import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from pypdf import PdfReader

from tools.document.pdf import convert_md_to_pdf
from tools.document.typst_renderer import MarkdownTypstRenderer, convert_markdown_to_pdf


SAMPLE_MARKDOWN = """# 库存报告

当前库存充足，汇总如下。

## 商品信息

| 项目 | 详情 |
| --- | --- |
| 通用名 | 阿莫西林胶囊 |
| 规格 | 0.25g x 24粒 |

## 批次明细

| 批次号 | 仓库位置 | 库存数量 | 有效期至 |
| --- | --- | ---: | --- |
| MY-250101-A | 北京一号库-A区 | 5,000盒 | 2027-01-01 |
| MY-250615-B | 北京二号库-B区 | 8,000盒 | 2027-06-14 |

- 库存状态正常
- 建议优先出库临近有效期批次

> 数据仅供内部库存核对。

```sql
SELECT * FROM medicines;
```
"""


class TypstDocumentTests(unittest.TestCase):
    def test_markdown_renderer_maps_structured_elements(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source_dir = Path(temp_dir)
            Image.new("RGB", (40, 24), color="white").save(source_dir / "chart.png")
            source = SAMPLE_MARKDOWN + "\n\n![库存图](chart.png)\n"

            rendered = MarkdownTypstRenderer(source_dir).render(source, "报告")

        self.assertIn('#heading(level: 1)[#text("库存报告")]', rendered)
        self.assertIn("#table(", rendered)
        self.assertIn("#list(", rendered)
        self.assertIn("#quote(block: true", rendered)
        self.assertIn('#raw("SELECT * FROM medicines;\\n"', rendered)
        self.assertIn('image("chart.png", width: 88%)', rendered)

    def test_typst_compiles_markdown_to_valid_pdf(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            md_path = root / "库存报告.md"
            pdf_path = root / "库存报告.pdf"
            Image.new("RGB", (120, 72), color="#E8EEF7").save(root / "stock.png")
            md_path.write_text(
                SAMPLE_MARKDOWN + "\n\n![库存趋势图](stock.png)\n",
                encoding="utf-8",
            )

            result = convert_markdown_to_pdf(md_path, pdf_path)

            self.assertEqual(result, pdf_path.resolve())
            self.assertTrue(pdf_path.read_bytes().startswith(b"%PDF"))
            self.assertGreaterEqual(len(PdfReader(str(pdf_path)).pages), 1)

    def test_langchain_tool_keeps_existing_interface(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "report.md").write_text(SAMPLE_MARKDOWN, encoding="utf-8")

            with patch(
                "tools.document.pdf.get_session_context", return_value=str(root)
            ):
                result = convert_md_to_pdf.invoke({"md_filename": "report.md"})

            self.assertIn("Typst 引擎", result)
            self.assertTrue((root / "report.pdf").is_file())


if __name__ == "__main__":
    unittest.main()
