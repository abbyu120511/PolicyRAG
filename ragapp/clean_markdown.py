"""清洗由 pdf_to_markdown.py 生成的、带页码边界的 Markdown。

设计原则：
1. 原始 Markdown 永远不修改；
2. 只做可解释的格式清洗，不用 LLM 改写保险原文；
3. 每页的清洗结果和删除项都写进 JSON 报告，方便人工复核。

运行：
    .venv/bin/python -m ragapp.clean_markdown
"""

import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).parent.parent
RAW_MARKDOWN_DIR = ROOT / "storage" / "markdown"
CLEAN_MARKDOWN_DIR = ROOT / "storage" / "cleaned"
REPORT_DIR = ROOT / "storage" / "reports"

PAGE_PATTERN = re.compile(
    r"<!-- page: (?P<number>\d+) -->\n## 第 \d+ 页\n\n(?P<content>.*?)(?=<!-- page: |\Z)",
    re.DOTALL,
)
BULLET_PATTERN = re.compile(r"^(?:[-*•]|\d+[.)、])\s*")
PAGE_NUMBER_PATTERN = re.compile(r"^(?:第\s*)?\d+(?:\s*/\s*\d+)?(?:\s*頁|\s*页)?$")
# 即使这类文字出现在每一页的页脚，也可能是合规或分发限制，不能自动删除。
PROTECTED_BOUNDARY_KEYWORDS = ("只供", "不得", "保密", "免責", "免责", "責任", "责任", "警告")


@dataclass
class Page:
    number: int
    content: str


def normalize_line(line: str) -> str:
    """统一空白字符；不改变中文、数字或保险术语本身。"""
    line = line.replace("\u00a0", " ").replace("\u200b", "")
    return re.sub(r"[ \t]+", " ", line).strip()


def parse_pages(markdown: str) -> list[Page]:
    """从带 HTML 页码注释的 Markdown 中取出每一页的正文。"""
    pages = [
        Page(number=int(match["number"]), content=match["content"].strip())
        for match in PAGE_PATTERN.finditer(markdown)
    ]
    if not pages:
        raise ValueError("没有找到页码标记；请先用 pdf_to_markdown.py 转换 PDF。")
    return pages


def frontmatter_value(markdown: str, key: str) -> str | None:
    """读取转换文件顶部 YAML 中的一个简单字段。"""
    match = re.search(rf"^{re.escape(key)}: (.+)$", markdown, re.MULTILINE)
    return match.group(1).strip() if match else None


def boundary_candidates(pages: list[Page]) -> set[str]:
    """找出经常出现在每页开头或结尾的短行，作为页眉/页脚候选。"""
    counts: Counter[str] = Counter()
    for page in pages:
        lines = [normalize_line(line) for line in page.content.splitlines()]
        lines = [line for line in lines if line]
        # 只观察每页边界，避免把正文中重复出现的关键条款误删。
        for line in set(lines[:4] + lines[-4:]):
            if 2 <= len(line) <= 100 and not PAGE_NUMBER_PATTERN.fullmatch(line):
                counts[line] += 1

    # 至少出现在 45% 的页面才会自动移除；其余候选只会留在原文中。
    minimum_pages = max(3, int(len(pages) * 0.45))
    return {
        line
        for line, count in counts.items()
        if count >= minimum_pages
        and not any(keyword in line for keyword in PROTECTED_BOUNDARY_KEYWORDS)
    }


def should_join(current: str, following: str) -> bool:
    """判断相邻两行是否像同一段被 PDF 强制换行的文本。"""
    if not current or not following:
        return False
    if BULLET_PATTERN.match(following) or following.startswith("#"):
        return False
    if current.endswith(("。", "！", "？", "；", "：", ":", ";", ".", "!", "?")):
        return False
    # 很短的独立标题不与下一行合并。
    if len(current) <= 18 and not BULLET_PATTERN.match(current):
        return False
    return True


def join_lines(lines: list[str]) -> list[str]:
    """仅合并明显由版面造成的断行，保留段落和列表的边界。"""
    result: list[str] = []
    for line in lines:
        if not line:
            if result and result[-1] != "":
                result.append("")
            continue

        if result and result[-1] and should_join(result[-1], line):
            # 两侧都是英文/数字时补一个空格；中文紧接时不插入空格。
            separator = " " if result[-1][-1].isascii() and line[0].isascii() else ""
            result[-1] = f"{result[-1]}{separator}{line}"
        else:
            result.append(line)
    return result


def clean_page(page: Page, repeated_boundary_lines: set[str]) -> tuple[str, dict]:
    """清洗一页，并返回清洗后的正文和供报告使用的统计信息。"""
    raw_lines = page.content.splitlines()
    normalized = [normalize_line(line) for line in raw_lines]
    removed: list[str] = []
    suspected_page_numbers: list[str] = []
    kept: list[str] = []
    for line in normalized:
        # 产品费率表中也可能有大量单独的数字。没有版面坐标时，不能把它们
        # 自动认定为页码；只记录到报告中，留给人工确认。
        if PAGE_NUMBER_PATTERN.fullmatch(line):
            suspected_page_numbers.append(line)
            kept.append(line)
        elif line in repeated_boundary_lines:
            removed.append(line)
        else:
            kept.append(line)

    cleaned_lines = join_lines(kept)
    cleaned = "\n".join(cleaned_lines).strip()
    report = {
        "page": page.number,
        "raw_characters": len(page.content),
        "cleaned_characters": len(cleaned),
        "removed_lines": removed,
        "suspected_page_number_lines": suspected_page_numbers,
    }
    return cleaned, report


def clean_markdown(input_path: Path, output_path: Path, report_path: Path) -> dict:
    """清洗 Markdown 并写出 Markdown + JSON 报告。"""
    raw = input_path.read_text(encoding="utf-8")
    pages = parse_pages(raw)
    repeated_boundary_lines = boundary_candidates(pages)
    source_file = frontmatter_value(raw, "source_file") or input_path.name

    output: list[str] = [
        "---",
        f"source_file: {source_file}",
        f"source_markdown: {input_path.name}",
        f"page_count: {len(pages)}",
        "cleaning_version: 1",
        "---",
        "",
        f"# {input_path.stem}",
        "",
    ]
    page_reports = []
    for page in pages:
        cleaned, page_report = clean_page(page, repeated_boundary_lines)
        output.extend([
            f"<!-- page: {page.number} -->",
            f"## 第 {page.number} 页",
            "",
            cleaned if cleaned else "[本页清洗后没有可用文本]",
            "",
        ])
        page_reports.append(page_report)

    report = {
        "source_markdown": input_path.name,
        "page_count": len(pages),
        "cleaning_version": 1,
        "removed_repeated_boundary_lines": sorted(repeated_boundary_lines),
        "note": "数字行仅作为疑似页码记录，未自动删除，避免误删费率表数据。",
        "pages": page_reports,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(output), encoding="utf-8")
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report


def main() -> None:
    source_name = "SunHealth Cancer Shield_Product Guide CHI 20200917"
    input_path = RAW_MARKDOWN_DIR / f"{source_name}.md"
    output_path = CLEAN_MARKDOWN_DIR / f"{source_name}.md"
    report_path = REPORT_DIR / f"{source_name}.json"

    if not input_path.exists():
        raise FileNotFoundError(f"找不到原始 Markdown：{input_path}")

    report = clean_markdown(input_path, output_path, report_path)
    print(f"已清洗 {report['page_count']} 页：{output_path}")
    print(f"清洗报告：{report_path}")


if __name__ == "__main__":
    main()
