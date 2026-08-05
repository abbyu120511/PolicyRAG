"""本地知识库文档的上传、处理、启停与下架管理。"""

import json
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from fastapi import HTTPException, UploadFile

from ragapp.clean_markdown import clean_markdown
from ragapp.index_markdown import build_documents, get_vectorstore, replace_document
from ragapp.pdf_to_markdown import pdf_to_markdown


ROOT = Path(__file__).parent.parent
PRIVATE_DOCS_DIR = ROOT / "private_docs"
STORAGE_DIR = ROOT / "storage"
RAW_MARKDOWN_DIR = STORAGE_DIR / "markdown"
CLEAN_MARKDOWN_DIR = STORAGE_DIR / "cleaned"
REPORT_DIR = STORAGE_DIR / "reports"
CATALOG_PATH = STORAGE_DIR / "document_catalog.sqlite3"
ALLOWED_SUFFIXES = {".pdf", ".md"}


def now() -> str:
    return datetime.now(UTC).isoformat()


def document_key(filename: str) -> str:
    """避免同名 PDF/Markdown 的派生文件互相覆盖。"""
    path = Path(filename)
    safe_stem = re.sub(r"[^\w.-]+", "_", path.stem, flags=re.UNICODE)
    return f"{path.suffix.lstrip('.').lower()}__{safe_stem}"


def connect() -> sqlite3.Connection:
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(CATALOG_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            filename TEXT PRIMARY KEY,
            file_type TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'uploaded',
            page_count INTEGER,
            chunk_count INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            error TEXT
        )
    """)
    return connection


def to_dict(row: sqlite3.Row) -> dict:
    return dict(row) | {"enabled": bool(row["enabled"])}


def source_path(filename: str) -> Path:
    candidate = (PRIVATE_DOCS_DIR / filename).resolve()
    if candidate.parent != PRIVATE_DOCS_DIR.resolve() or candidate.suffix.lower() not in ALLOWED_SUFFIXES:
        raise HTTPException(status_code=404, detail="文档不存在")
    if not candidate.is_file():
        raise HTTPException(status_code=404, detail="文档不存在")
    return candidate


def sync_catalog() -> None:
    """把手动放进 private_docs/ 的文件补进目录；已有清洗结果视为历史已启用资料。"""
    with connect() as connection:
        for path in PRIVATE_DOCS_DIR.iterdir():
            if not path.is_file() or path.suffix.lower() not in ALLOWED_SUFFIXES:
                continue
            key = document_key(path.name)
            # 兼容在引入知识库目录前已经生成的第一份 Markdown。
            cleaned_candidates = [
                CLEAN_MARKDOWN_DIR / f"{key}.md",
                CLEAN_MARKDOWN_DIR / f"{path.stem}.md",  # 兼容早期第一份文档
            ]
            cleaned_path = next((candidate for candidate in cleaned_candidates if candidate.exists()), None)
            historical_enabled = int(cleaned_path is not None)
            connection.execute("""
                INSERT OR IGNORE INTO documents
                (filename, file_type, enabled, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                path.name,
                path.suffix.lstrip(".").lower(),
                historical_enabled,
                "enabled" if historical_enabled else "uploaded",
                now(), now(),
            ))
            # 第一次加入目录前已入库的旧文档，也补齐展示所需的页数/chunk 数。
            if cleaned_path is not None:
                row = connection.execute("SELECT page_count, chunk_count FROM documents WHERE filename = ?", (path.name,)).fetchone()
                if row["page_count"] is None or row["chunk_count"] is None:
                    text = cleaned_path.read_text(encoding="utf-8")
                    pages = len(re.findall(r"<!-- page: \d+ -->", text))
                    chunks = len(build_documents(cleaned_path))
                    connection.execute("UPDATE documents SET page_count = ?, chunk_count = ? WHERE filename = ?", (pages, chunks, path.name))


def list_documents() -> list[dict]:
    sync_catalog()
    with connect() as connection:
        rows = connection.execute("SELECT * FROM documents ORDER BY updated_at DESC").fetchall()
    return [to_dict(row) for row in rows]


def preview_chunks(filename: str) -> list[dict]:
    """读取已清洗 Markdown 的切块预览，不调用 embedding，也不修改 Chroma。"""
    path = source_path(filename)
    key = document_key(filename)
    # 保留早期第一份资料的兼容路径；新上传资料统一使用 document_key 命名。
    cleaned_candidates = [
        CLEAN_MARKDOWN_DIR / f"{key}.md",
        CLEAN_MARKDOWN_DIR / f"{path.stem}.md",
    ]
    cleaned_path = next((candidate for candidate in cleaned_candidates if candidate.exists()), None)
    if cleaned_path is None:
        raise HTTPException(
            status_code=409,
            detail="该资料尚未完成处理；请先启用资料生成切块。",
        )

    documents = build_documents(cleaned_path)
    return [
        {
            "id": document.id,
            "text": document.page_content,
            "metadata": document.metadata,
        }
        for document in documents
    ]


async def save_upload(file: UploadFile) -> dict:
    filename = Path(file.filename or "").name
    suffix = Path(filename).suffix.lower()
    if not filename or suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(status_code=415, detail="仅支持 PDF 或 Markdown 文件")
    destination = PRIVATE_DOCS_DIR / filename
    if destination.exists():
        raise HTTPException(status_code=409, detail="同名文件已存在；请先下架旧文件或更改文件名")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=422, detail="上传的文件为空")
    destination.write_bytes(content)

    with connect() as connection:
        connection.execute("""
            INSERT INTO documents (filename, file_type, enabled, status, created_at, updated_at)
            VALUES (?, ?, 0, 'uploaded', ?, ?)
        """, (filename, suffix.lstrip("."), now(), now()))
        row = connection.execute("SELECT * FROM documents WHERE filename = ?", (filename,)).fetchone()
    return to_dict(row)


def markdown_from_upload(path: Path, output_path: Path) -> int:
    """为上传的 Markdown 补齐 RAG 所需的来源与页码边界。"""
    text = path.read_text(encoding="utf-8").strip()
    if "<!-- page:" in text:
        if not text.startswith("---"):
            text = f"---\nsource_file: {path.name}\n---\n\n{text}"
        output_path.write_text(text, encoding="utf-8")
        return len(re.findall(r"<!-- page: \d+ -->", text))

    output_path.write_text(
        "\n".join([
            "---", f"source_file: {path.name}", "page_count: 1", "---", "",
            f"# {path.stem}", "", "<!-- page: 1 -->", "## 第 1 页", "", text,
        ]),
        encoding="utf-8",
    )
    return 1


def enable_document(filename: str) -> dict:
    path = source_path(filename)
    key = document_key(filename)
    raw_markdown = RAW_MARKDOWN_DIR / f"{key}.md"
    cleaned_markdown = CLEAN_MARKDOWN_DIR / f"{key}.md"
    report = REPORT_DIR / f"{key}.json"

    with connect() as connection:
        connection.execute("UPDATE documents SET status = 'processing', error = NULL, updated_at = ? WHERE filename = ?", (now(), filename))

    try:
        if path.suffix.lower() == ".pdf":
            pages = pdf_to_markdown(path, raw_markdown)
        else:
            raw_markdown.parent.mkdir(parents=True, exist_ok=True)
            pages = markdown_from_upload(path, raw_markdown)

        clean_markdown(raw_markdown, cleaned_markdown, report)
        documents = build_documents(cleaned_markdown)
        replace_document(get_vectorstore(), documents)
        with connect() as connection:
            connection.execute("""
                UPDATE documents
                SET enabled = 1, status = 'enabled', page_count = ?, chunk_count = ?, updated_at = ?, error = NULL
                WHERE filename = ?
            """, (pages, len(documents), now(), filename))
            row = connection.execute("SELECT * FROM documents WHERE filename = ?", (filename,)).fetchone()
        return to_dict(row)
    except Exception as error:
        with connect() as connection:
            connection.execute("UPDATE documents SET enabled = 0, status = 'failed', error = ?, updated_at = ? WHERE filename = ?", (str(error), now(), filename))
        raise HTTPException(status_code=500, detail="文档处理失败，请查看文档状态") from error


def disable_document(filename: str) -> dict:
    source_path(filename)
    vectorstore = get_vectorstore()
    existing = vectorstore.get(where={"source_file": filename})
    if existing["ids"]:
        vectorstore.delete(ids=existing["ids"])
    with connect() as connection:
        connection.execute("UPDATE documents SET enabled = 0, status = 'disabled', updated_at = ? WHERE filename = ?", (now(), filename))
        row = connection.execute("SELECT * FROM documents WHERE filename = ?", (filename,)).fetchone()
    return to_dict(row)


def delete_document(filename: str) -> None:
    path = source_path(filename)
    disable_document(filename)
    key = document_key(filename)
    for artifact in (
        RAW_MARKDOWN_DIR / f"{key}.md",
        CLEAN_MARKDOWN_DIR / f"{key}.md",
        REPORT_DIR / f"{key}.json",
    ):
        artifact.unlink(missing_ok=True)
    path.unlink()
    with connect() as connection:
        connection.execute("DELETE FROM documents WHERE filename = ?", (filename,))
