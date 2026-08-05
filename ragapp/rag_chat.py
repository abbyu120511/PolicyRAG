"""第一条 LangChain RAG 链：检索资料、让模型基于资料回答、附上真实页码引用。

运行（会将问题和检索到的资料发送给已配置的聊天模型）：
    .venv/bin/python -m ragapp.rag_chat --question "这份癌症保险的等候期是多久？"
"""

import argparse

from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda, RunnablePassthrough
from pydantic import BaseModel, Field

from ragapp.index_markdown import get_vectorstore


class RAGAnswer(BaseModel):
    """模型必须返回的结构；这比让模型随意输出一段文本更容易被程序检查。"""

    answer: str = Field(description="基于资料得出的简洁回答")
    has_sufficient_evidence: bool = Field(
        description="资料是否明确支持回答；资料不足时必须为 false"
    )
    evidence_chunk_ids: list[str] = Field(
        description="支持答案的 chunk ID；只能从提供的资料中挑选，资料不足时为空列表"
    )


def format_docs(documents: list[Document]) -> str:
    """将检索结果整理成模型可读的上下文，并保留每段的来源标签。"""
    return "\n\n".join(
        "[chunk_id: {id}｜来源：{source}，第 {page} 页，chunk {chunk}]\n{text}".format(
            id=document.id,
            source=document.metadata["source_file"],
            page=document.metadata["page"],
            chunk=document.metadata["chunk_index"],
            text=document.page_content,
        )
        for document in documents
    )


def format_references(documents: list[Document]) -> str:
    """引用由 metadata 生成，而不是让模型凭空编造。"""
    references: list[str] = []
    seen: set[tuple[str, int]] = set()
    for document in documents:
        key = (document.metadata["source_file"], document.metadata["page"])
        if key not in seen:
            seen.add(key)
            references.append(f"- {key[0]}，第 {key[1]} 页")
    return "\n".join(references)


def select_evidence(
    model_answer: RAGAnswer, retrieved_documents: list[Document]
) -> tuple[str, bool, list[Document]]:
    """只接受模型从本次检索结果中选择的证据，拒绝幻觉 chunk ID。"""
    retrieved_by_id = {document.id: document for document in retrieved_documents}
    evidence = [
        retrieved_by_id[chunk_id]
        for chunk_id in model_answer.evidence_chunk_ids
        if chunk_id in retrieved_by_id
    ]

    # 任何“资料不足”、没有引用，或引用了不存在 chunk 的结果都不能正常回答。
    if not model_answer.has_sufficient_evidence or not evidence:
        return "现有知识库没有足够依据回答这个问题。", False, []
    return model_answer.answer, True, evidence


PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        "你是保险产品资料助手。只能使用提供的资料回答，不得补充外部知识或猜测。"
        "如果资料无法明确支持答案，请直接说：『现有知识库没有足够依据回答这个问题。』"
        "回答简洁、准确。不要在正文中写文件名、页码、‘资料来源’或任何引用；"
        "调用程序会在回答后统一附上真实的 metadata 引用。"
        "你必须从资料中给出的 chunk_id 选择支持答案的证据；不得编造 chunk_id。"
        "若资料不足，has_sufficient_evidence 必须为 false，evidence_chunk_ids 必须为空列表。"
        "\n\n资料：\n{context}",
    ),
    ("user", "{question}"),
])


def build_rag_chain():
    """组合成一个 LCEL 链，输出 answer 和实际命中的 documents。"""
    # 延迟导入：只查看 API 健康状态时不应初始化模型供应商配置。
    from llm_setup import get_llm

    retriever = get_vectorstore().as_retriever(search_kwargs={"k": 4})
    retrieve = RunnableLambda(
        lambda question: {
            "question": question,
            "documents": retriever.invoke(question),
        }
    )
    add_context = RunnablePassthrough.assign(
        context=lambda values: format_docs(values["documents"]),
    )
    structured_llm = get_llm("qwen-plus", temperature=0).with_structured_output(RAGAnswer)
    answer = PROMPT | structured_llm
    return retrieve | add_context | RunnablePassthrough.assign(answer=answer)


def ask(question: str) -> tuple[str, bool, list[Document]]:
    """给前端/API 使用的稳定入口。"""
    result = build_rag_chain().invoke(question)
    return select_evidence(result["answer"], result["documents"])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--question", required=True, help="要询问产品资料的问题")
    args = parser.parse_args()

    answer, has_evidence, evidence = ask(args.question)
    print(f"\n问题：{args.question}\n\n回答：\n{answer}")
    if has_evidence:
        print(f"\n参考资料（由检索 metadata 生成）：\n{format_references(evidence)}")
    else:
        print("\n参考资料：无（没有足够依据时不展示引用）")


if __name__ == "__main__":
    main()
