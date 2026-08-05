"""把清洗后的 Markdown 按页切块，并可选择写入 Chroma 向量库。

默认是 dry-run：只打印即将入库的 chunks，不会读取 API Key，也不会把任何
私有文本发送到 embedding 服务。确认资料可以发送到模型供应商后，再加 --index。

运行：
    # 本地检查切块和页码，不访问网络
    .venv/bin/python -m ragapp.index_markdown

    # 真正生成 embedding 并写入本地 Chroma
    .venv/bin/python -m ragapp.index_markdown --index
"""

import argparse
import hashlib
import re
from pathlib import Path

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from ragapp.clean_markdown import Page, parse_pages


ROOT = Path(__file__).parent.parent
CLEAN_MARKDOWN_DIR = ROOT / "storage" / "cleaned"
CHROMA_DIR = ROOT / "storage" / "chroma"
COLLECTION_NAME = "insurance_knowledge"
CHUNK_SIZE = 700
CHUNK_OVERLAP = 100
# 这类每页重复的分发标记仍保留在清洗后的 Markdown 中，但不会参与语义检索。
# 它不是回答产品问题的证据，反而会稀释真正条款的向量表示。
NON_RETRIEVAL_BOILERPLATE = {"只供內部傳閱，不得派發予公眾、客戶或準客戶。"}


def frontmatter_value(markdown: str, key: str) -> str | None:
    match = re.search(rf"^{re.escape(key)}: (.+)$", markdown, re.MULTILINE)
    return match.group(1).strip() if match else None


def build_documents(markdown_path: Path) -> list[Document]:
    """按页切块；每块永远只继承一个 PDF 页码。"""
    markdown = markdown_path.read_text(encoding="utf-8")
    pages: list[Page] = parse_pages(markdown)
    source_file = frontmatter_value(markdown, "source_file") or markdown_path.name
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", "。", "，", " ", ""],
    )

    documents: list[Document] = []
    for page in pages:
        retrieval_text = "\n".join(
            line for line in page.content.splitlines()
            if line.strip() not in NON_RETRIEVAL_BOILERPLATE
        )
        page_chunks = splitter.split_text(retrieval_text)
        for chunk_index, chunk in enumerate(page_chunks, start=1):
            # 此 ID 可复现：同一文件、同一清洗版本、同一页和 chunk 会得到同一个 ID。
            raw_id = f"{source_file}|v1|p{page.number}|c{chunk_index}"
            chunk_id = hashlib.sha256(raw_id.encode()).hexdigest()[:16]
            documents.append(Document(
                id=chunk_id,
                page_content=chunk,
                metadata={
                    "source_file": source_file,
                    "page": page.number,
                    "chunk_index": chunk_index,
                    "cleaning_version": 1,
                    "boilerplate_excluded_from_embedding": True,
                },
            ))
    return documents


def get_vectorstore() -> Chroma:
    """打开本地持久化 Chroma；embedding 只在真正入库/查询时会被调用。"""
    # 延迟导入：dry-run 不会初始化模型供应商相关配置。
    from llm_setup import get_embeddings

    return Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=get_embeddings(),
        persist_directory=str(CHROMA_DIR),
    )


def replace_document(vectorstore: Chroma, documents: list[Document]) -> None:
    """同一来源文件重新入库前，先按 metadata 删除旧 chunks，避免版本混杂。"""
    source_file = documents[0].metadata["source_file"]
    existing = vectorstore.get(where={"source_file": source_file})
    if existing["ids"]:
        vectorstore.delete(ids=existing["ids"])
        print(f"已删除 {len(existing['ids'])} 个旧 chunks")

    vectorstore.add_documents(documents, ids=[document.id for document in documents])
    print(f"已写入 {len(documents)} 个 chunks 到 {CHROMA_DIR}")


def print_preview(documents: list[Document]) -> None:
    """让学习者先肉眼确认：切块内容和页码确实绑定正确。"""
    pages = sorted({document.metadata["page"] for document in documents})
    print(f"共 {len(documents)} 个 chunks，覆盖 {len(pages)} 页：{pages[0]}–{pages[-1]}")
    for document in documents[:3]:
        print(
            f"\n[{document.metadata['source_file']} 第 {document.metadata['page']} 页 "
            f"chunk {document.metadata['chunk_index']}]\n{document.page_content[:240]}..."
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--index",
        action="store_true",
        help="调用 embedding 接口并写入本地 Chroma；默认只做本地预览。",
    )
    args = parser.parse_args()

    markdown_path = CLEAN_MARKDOWN_DIR / "SunHealth Cancer Shield_Product Guide CHI 20200917.md"
    if not markdown_path.exists():
        raise FileNotFoundError(f"找不到清洗后的 Markdown：{markdown_path}")

    documents = build_documents(markdown_path)
    print_preview(documents)
    if not args.index:
        print("\n这是 dry-run：没有调用 embedding 服务，也没有写入 Chroma。")
        return

    replace_document(get_vectorstore(), documents)


if __name__ == "__main__":
    main()
