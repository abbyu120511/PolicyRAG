"""用 LangGraph 管理“检索不够时改写查询并重试一次”的 RAG 工作流。

运行（会调用 embedding 和聊天模型）：
    .venv/bin/python -m ragapp.langgraph_rag --question "这份癌症保险的等候期是多久？"
"""

import argparse
from typing import Literal

from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from ragapp.index_markdown import get_vectorstore
from ragapp.rag_chat import (
    PROMPT,
    RAGAnswer,
    format_docs,
    format_references,
    select_evidence,
)


MAX_RETRIEVAL_ATTEMPTS = 2


class RAGState(TypedDict):
    """LangGraph 在每个节点之间传递的共享状态。"""

    original_question: str
    search_query: str
    attempts: int
    documents: list[Document]
    answer: str
    has_sufficient_evidence: bool
    evidence: list[Document]


def build_graph():
    """创建图；构建阶段不发网络请求，真正 invoke 时才调用模型。"""
    # 延迟导入：FastAPI 的 /health 和 /documents 不需要模型配置或网络。
    from llm_setup import get_llm

    retriever = get_vectorstore().as_retriever(search_kwargs={"k": 4})
    answer_chain = PROMPT | get_llm("qwen-plus", temperature=0).with_structured_output(RAGAnswer)
    rewrite_prompt = ChatPromptTemplate.from_messages([
        (
            "system",
            "你负责改写检索查询，不回答问题。将用户问题改成更适合从保险产品资料中"
            "检索事实依据的一句简短查询；不要引入原问题没有的事实。",
        ),
        ("user", "{question}"),
    ])
    rewrite_chain = rewrite_prompt | get_llm("qwen-turbo", temperature=0) | StrOutputParser()

    def retrieve(state: RAGState) -> dict:
        documents = retriever.invoke(state["search_query"])
        return {"documents": documents}

    def answer(state: RAGState) -> dict:
        model_answer = answer_chain.invoke({
            "question": state["original_question"],
            "context": format_docs(state["documents"]),
        })
        final_answer, has_evidence, evidence = select_evidence(
            model_answer, state["documents"]
        )
        return {
            "answer": final_answer,
            "has_sufficient_evidence": has_evidence,
            "evidence": evidence,
        }

    def choose_next(state: RAGState) -> Literal["finalize", "rewrite_query"]:
        if state["has_sufficient_evidence"] or state["attempts"] >= MAX_RETRIEVAL_ATTEMPTS - 1:
            return "finalize"
        return "rewrite_query"

    def rewrite_query(state: RAGState) -> dict:
        rewritten = rewrite_chain.invoke({"question": state["original_question"]}).strip()
        return {"search_query": rewritten, "attempts": state["attempts"] + 1}

    workflow = StateGraph(RAGState)
    workflow.add_node("retrieve", retrieve)
    workflow.add_node("answer", answer)
    workflow.add_node("rewrite_query", rewrite_query)
    workflow.add_edge(START, "retrieve")
    workflow.add_edge("retrieve", "answer")
    workflow.add_conditional_edges(
        "answer",
        choose_next,
        {"finalize": END, "rewrite_query": "rewrite_query"},
    )
    workflow.add_edge("rewrite_query", "retrieve")
    return workflow.compile()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--question", required=True, help="要询问产品资料的问题")
    args = parser.parse_args()

    graph = build_graph()
    result = graph.invoke({
        "original_question": args.question,
        "search_query": args.question,
        "attempts": 0,
    })
    print(f"\n问题：{result['original_question']}")
    print(f"最终检索查询：{result['search_query']}")
    print(f"检索次数：{result['attempts'] + 1}")
    print(f"\n回答：\n{result['answer']}")
    if result["has_sufficient_evidence"]:
        print(f"\n参考资料：\n{format_references(result['evidence'])}")
    else:
        print("\n参考资料：无（没有足够依据时不展示引用）")


if __name__ == "__main__":
    main()
