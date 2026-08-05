"""本地 RAG 后端 API。

运行：
    .venv/bin/uvicorn ragapp.api:app --reload

浏览器打开 http://127.0.0.1:8000/docs 可以查看并手动测试接口。
"""

from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ragapp.document_manager import (
    delete_document,
    disable_document,
    enable_document,
    list_documents as list_managed_documents,
    preview_chunks,
    save_upload,
)
from ragapp.langgraph_rag import build_graph


ROOT = Path(__file__).parent.parent
PRIVATE_DOCS_DIR = ROOT / "private_docs"

app = FastAPI(
    title="PolicyRAG Studio API",
    description="本地运行的保险产品资料 RAG 后端。",
    version="0.1.0",
)
# MVP 的 React 前端会在 localhost 的另一个端口运行；生产环境应改成明确的前端域名。
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1_000, description="用户问题")


class Reference(BaseModel):
    source_file: str
    page: int
    document_url: str
    file_type: str


class ChatResponse(BaseModel):
    answer: str
    has_sufficient_evidence: bool
    retrieval_attempts: int
    references: list[Reference]


class ManagedDocument(BaseModel):
    filename: str
    file_type: str
    enabled: bool
    status: str
    page_count: int | None = None
    chunk_count: int | None = None
    created_at: str
    updated_at: str
    error: str | None = None


class ChunkPreview(BaseModel):
    id: str
    text: str
    metadata: dict[str, Any]


class ChunkPreviewResponse(BaseModel):
    filename: str
    chunks: list[ChunkPreview]


@lru_cache(maxsize=1)
def get_graph():
    """进程内复用已编译的图，避免每个 HTTP 请求重复组装工作流。"""
    return build_graph()


def safe_document_path(filename: str) -> Path:
    """只允许访问 private_docs/ 目录内的 PDF/Markdown，防止路径穿越。"""
    candidate = (PRIVATE_DOCS_DIR / filename).resolve()
    if candidate.parent != PRIVATE_DOCS_DIR.resolve() or candidate.suffix.lower() not in {".pdf", ".md"}:
        raise HTTPException(status_code=404, detail="文档不存在")
    if not candidate.is_file():
        raise HTTPException(status_code=404, detail="文档不存在")
    return candidate


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/documents", response_model=list[ManagedDocument])
def list_documents() -> list[dict]:
    return list_managed_documents()


@app.post("/documents/upload", response_model=ManagedDocument)
async def upload_document(file: UploadFile) -> dict:
    """保存 PDF/MD；上传后默认不启用，避免资料未经处理就参与问答。"""
    return await save_upload(file)


@app.post("/documents/{filename}/enable", response_model=ManagedDocument)
def enable_knowledge_document(filename: str) -> dict:
    return enable_document(filename)


@app.post("/documents/{filename}/disable", response_model=ManagedDocument)
def disable_knowledge_document(filename: str) -> dict:
    return disable_document(filename)


@app.delete("/documents/{filename}", status_code=204)
def delete_knowledge_document(filename: str) -> None:
    delete_document(filename)


@app.get("/documents/{filename}/chunks", response_model=ChunkPreviewResponse)
def get_document_chunks(filename: str) -> ChunkPreviewResponse:
    """供知识库管理页核查已生成的 chunk 与 metadata。"""
    return ChunkPreviewResponse(filename=filename, chunks=preview_chunks(filename))


@app.get("/documents/{filename}")
def get_document(filename: str) -> FileResponse:
    path = safe_document_path(filename)
    media_type = "application/pdf" if path.suffix.lower() == ".pdf" else "text/markdown; charset=utf-8"
    return FileResponse(path, media_type=media_type)


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    """运行 LangGraph RAG；引用只在证据充分时从 metadata 生成。"""
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=422, detail="问题不能为空")

    result = get_graph().invoke({
        "original_question": question,
        "search_query": question,
        "attempts": 0,
    })
    references = []
    if result["has_sufficient_evidence"]:
        seen: set[tuple[str, int]] = set()
        for document in result["evidence"]:
            key = (document.metadata["source_file"], document.metadata["page"])
            if key not in seen:
                seen.add(key)
                references.append(Reference(
                    source_file=key[0],
                    page=key[1],
                    document_url=f"/documents/{key[0]}",
                    file_type=Path(key[0]).suffix.lstrip(".").lower(),
                ))

    return ChatResponse(
        answer=result["answer"],
        has_sufficient_evidence=result["has_sufficient_evidence"],
        retrieval_attempts=result["attempts"] + 1,
        references=references,
    )
