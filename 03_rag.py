"""
第 3 课:RAG —— 检索增强生成

你熟悉的流程:文档 → 切分 → 向量化 → 入库 → 检索 → 拼进提示词 → 生成。
这一课看 LangChain 怎么把每一步变成标准组件,最后用第 2 课的 | 拼成一条链。

知识库素材:data/handbook.md(虚构公司的员工手册)。
"""

from llm_setup import get_llm, get_embeddings

# ═══ 第 1 步:加载文档 ═══════════════════════════════════════════
# LangChain 有上百种 Loader(PDF、网页、数据库…),接口统一:返回 Document 列表。
# Document = 一段文本(page_content) + 一包元数据(metadata,如来源文件名)
from langchain_community.document_loaders import TextLoader

docs = TextLoader("data/handbook.md", encoding="utf-8").load()
print(f"【加载】{len(docs)} 个文档,共 {len(docs[0].page_content)} 字")

# ═══ 第 2 步:切分 ══════════════════════════════════════════════
# RecursiveCharacterTextSplitter 是最常用的切分器:优先按段落切,切不动
# 再按句子、字符,尽量不把完整语义拦腰砍断。
from langchain_text_splitters import RecursiveCharacterTextSplitter

splitter = RecursiveCharacterTextSplitter(
    chunk_size=200,     # 每块约 200 字(演示用,真实项目常用 500-1000)
    chunk_overlap=40,   # 相邻块重叠 40 字,防止关键句恰好被切断
)
chunks = splitter.split_documents(docs)
print(f"【切分】{len(chunks)} 块。第 3 块预览: {chunks[2].page_content[:50]}...")

# ═══ 第 3 步:向量化 + 入库 ══════════════════════════════════════
# Embedding 模型把文本变成向量(一串数字),语义相近的文本向量距离近。
# FAISS 是内存向量库,做练习最方便;生产中换 Milvus/pgvector 等,接口不变。
from langchain_community.vectorstores import FAISS

vectorstore = FAISS.from_documents(chunks, get_embeddings())
print(f"【入库】向量维度 = {len(get_embeddings().embed_query('测试'))}")

# ═══ 第 4 步:检索器 ════════════════════════════════════════════
# as_retriever 把向量库包装成 Runnable(又是它!):输入问题字符串,
# 输出最相似的 k 个 Document。
retriever = vectorstore.as_retriever(search_kwargs={"k": 3})

hits = retriever.invoke("出差住酒店能报多少钱?")
print("\n【检索测试】问:出差住酒店能报多少钱? 命中前3块:")
# 【Python】for 循环 + enumerate:边遍历列表边计数(从 1 开始)
for i, doc in enumerate(hits, 1):
    print(f"  {i}. {doc.page_content[:40]}...")

# ═══ 第 5 步:组装 RAG 链 ═══════════════════════════════════════
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough

prompt = ChatPromptTemplate.from_messages([
    ("system",
     "你是公司 HR 助手。只根据下面的手册内容回答,手册里没有的就明说不知道,"
     "不要编造。回答末尾引用依据的原文片段。\n\n=== 手册内容 ===\n{context}"),
    ("user", "{question}"),
])


# 【Python】def 定义函数。这个函数把检索到的 Document 列表拼成一整段文本。
# "\n\n".join([...]) 里面是「列表推导式」:对 docs 里每个 d 取出 page_content,
# 组成新列表,再用空行连接成一个字符串。相当于一行写完的 for 循环。
def format_docs(docs):
    return "\n\n".join([d.page_content for d in docs])


# 链的第一节是个字典 —— LCEL 的「并行」写法:两个分支同时执行,
# 各自的结果按键名填进模板的 {context} 和 {question}。
#   context 分支: 问题 → 检索器 → 拼接成文本
#   question 分支: RunnablePassthrough() = 原样把问题传下去
rag_chain = (
    {"context": retriever | format_docs, "question": RunnablePassthrough()}
    | prompt
    | get_llm("qwen-plus", temperature=0)
    | StrOutputParser()
)

# ═══ 试问几个问题 ═══════════════════════════════════════════════
for q in [
    "我入职第4年,一年有几天年假?没休完怎么办?",
    "出差去二线城市,住宿标准是多少?",
    "公司提供健身房吗?",   # 手册里没有 → 应该老实说不知道
]:
    print(f"\n❓ {q}\n💬 {rag_chain.invoke(q)}")

# ═══════════════════════════════════════════════════════════════
# 练习:
# 1. 把 k 改成 1 再问年假问题,观察答案质量是否下降(检索少了会漏信息)
# 2. 问一个跨章节的问题,如"新员工能远程办公吗?学习基金有多少?"
# 3. 往 data/ 里加一个你自己的 md 文件,把两个文件都加载进知识库
#    (提示: docs = TextLoader(...).load() + TextLoader(...).load(),
#     列表可以用 + 拼接)
# ═══════════════════════════════════════════════════════════════
