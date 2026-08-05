"""把本地 PDF 转成保留页码边界的 Markdown。

这不是 OCR，也不尝试还原 PDF 的复杂视觉版式（表格、图片位置等）。
它适用于已有文字层的 PDF：每页提取出的文本会被写到一个 Markdown 分节中，
让后续 RAG 切块时始终知道内容来自哪一页。

运行：
    .venv/bin/python -m ragapp.pdf_to_markdown
"""

from pathlib import Path

import pymupdf


ROOT = Path(__file__).parent.parent
PRIVATE_DOCS_DIR = ROOT / "private_docs"
MARKDOWN_DIR = ROOT / "storage" / "markdown"


def pdf_to_markdown(pdf_path: Path, output_path: Path) -> int:
    """提取 PDF 的每一页文字，写入带页码标记的 Markdown，返回页数。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with pymupdf.open(pdf_path) as pdf:
        page_count = len(pdf)  # 离开 with 后 PDF 会自动关闭，页数要提前保存。
        lines = [
            "---",
            f"source_file: {pdf_path.name}",
            f"page_count: {page_count}",
            "---",
            "",
            f"# {pdf_path.stem}",
            "",
        ]

        for page_number, page in enumerate(pdf, start=1):
            # 这个 HTML 注释会被保留在 Markdown 中，后续切块程序可读取 page_number。
            text = page.get_text("text").strip()
            lines.extend([
                f"<!-- page: {page_number} -->",
                f"## 第 {page_number} 页",
                "",
                text if text else "[本页没有可提取的原生文本]",
                "",
            ])

    output_path.write_text("\n".join(lines), encoding="utf-8")
    return page_count


def main() -> None:
    # MVP 先只处理这一份产品指南。以后接入上传页面时，调用 pdf_to_markdown 即可。
    pdf_path = PRIVATE_DOCS_DIR / "SunHealth Cancer Shield_Product Guide CHI 20200917.pdf"
    output_path = MARKDOWN_DIR / f"{pdf_path.stem}.md"

    if not pdf_path.exists():
        raise FileNotFoundError(f"找不到私有 PDF：{pdf_path}")

    pages = pdf_to_markdown(pdf_path, output_path)
    print(f"已转换 {pages} 页：{output_path}")


if __name__ == "__main__":
    main()
