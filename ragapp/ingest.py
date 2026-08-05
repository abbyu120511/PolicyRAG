"""入库流水线:PDF → 按页解析 → 切分 → 向量化 → 持久化 Chroma。

核心设计:每一块文本都带着 {source: 文件名, page: 页码} 元数据入库。
检索命中后,这两个字段就是「引用具体到页」的数据来源——阶段 3 的
点击跳转 PDF 页,靠的全是现在存进去的 metadata。

运行测试: uv run python -m ragapp.ingest
"""

from pathlib import Path

import pymupdf
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from llm_setup import get_embeddings
from ragapp.config import CHROMA_DIR, CHUNK_OVERLAP, CHUNK_SIZE, DOCS_DIR


def get_vectorstore() -> Chroma:
    """打开(或创建)持久化向量库。数据落在磁盘,重启不丢。"""
    return Chroma(
        collection_name="knowledge",  # Chroma 要求名字至少 3 个字符
        embedding_function=get_embeddings(),
        persist_directory=str(CHROMA_DIR),
    )


def ingest_pdf(pdf_path: Path) -> int:
    """把一份 PDF 解析、切分、入库。返回入库的块数。"""
    # 用 PyMuPDF 逐页取文本,自己构造 Document(一页一个)。
    # metadata 里的 source 和 page,就是之后「引用具体到页」的数据来源。
    pages = []
    with pymupdf.open(pdf_path) as pdf:  # with: 用完自动关闭文件
        for i, page in enumerate(pdf, start=1):
            text = page.get_text().strip()
            if not text:
                continue  # 跳过空页(纯图片页需要 OCR,阶段 4 再说)
            pages.append(Document(
                page_content=text,
                metadata={"source": pdf_path.name, "page": i},
            ))

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP
    )
    chunks = splitter.split_documents(pages)  # 切分时 metadata 自动带到每块上

    vs = get_vectorstore()
    # 同名文件重新上传 = 更新:先删旧块,再入新块,避免新旧版本混着被检索到
    delete_doc(pdf_path.name)
    vs.add_documents(chunks)
    return len(chunks)


def delete_doc(filename: str) -> None:
    """按文件名删除该文档在向量库里的所有块。"""
    vs = get_vectorstore()
    vs._collection.delete(where={"source": filename})


def list_docs() -> dict[str, int]:
    """返回 {文件名: 块数},用于知识库管理页。"""
    data = get_vectorstore()._collection.get(include=["metadatas"])
    counts: dict[str, int] = {}
    for meta in data["metadatas"]:
        counts[meta["source"]] = counts.get(meta["source"], 0) + 1
    return counts


# ═══ 直接运行本文件时:把 docs/ 目录下所有 PDF 入库,并做一次检索测试 ═══
if __name__ == "__main__":
    for pdf in sorted(DOCS_DIR.glob("*.pdf")):  # glob: 按通配符找文件
        n = ingest_pdf(pdf)
        print(f"入库 {pdf.name}: {n} 块")

    print("\n当前知识库:", list_docs())

    print("\n【检索测试】问:重疾险的等待期是多久?")
    vs = get_vectorstore()
    # similarity_search_with_score 额外返回相似度距离(越小越相似)
    for doc, score in vs.similarity_search_with_score("重疾险的等待期是多久?", k=3):
        print(f"  [{doc.metadata['source']} 第{doc.metadata['page']}页] "
              f"距离={score:.3f} | {doc.page_content[:30]}...")
