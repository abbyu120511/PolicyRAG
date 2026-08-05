# 本项目的 LangChain RAG 导读

这不是一个“模型记住保险知识”的系统。模型每次回答前，都会从本地 Chroma
找回相关资料；模型只能依据这些资料组织答案。

```text
用户问题
  -> embedding（把问题变成向量）
  -> Chroma 检索（找相近 chunks）
  -> Prompt（问题 + 检索资料）
  -> ChatModel（基于资料回答）
  -> Pydantic 校验（答案、是否有证据、所用 chunk）
  -> metadata 生成 PDF 页码引用
```

## 推荐阅读顺序

1. `llm_setup.py`
   - 一个模型工厂。理解为什么业务代码不应到处写 API Key、模型名和 URL。
2. `01_hello_llm.py`
   - `invoke`、`stream`、`batch` 和 `AIMessage`。
3. `02_chains.py`
   - `Prompt | Model | Parser` 的 LCEL 管道；结构化输出的基本思想。
4. `ragapp/index_markdown.py`
   - 已清洗 Markdown 如何按页切块，并带上文件名和页码 metadata 写入 Chroma。
5. `ragapp/retrieve_preview.py`
   - 不调用聊天模型，直接观察 Chroma 找回了什么。这是排查 RAG 的第一步。
6. `ragapp/rag_chat.py`
   - 本项目真正的 RAG 链：检索、拼 prompt、结构化回答、证据和引用验证。

## 四个最重要的对象

| 对象 | 通俗理解 | 在本项目中的作用 |
|---|---|---|
| `Document` | 一张带标签的资料卡 | `page_content` 是文本，`metadata` 含 PDF 页码 |
| `Retriever` | 图书管理员 | 输入问题，返回相关资料卡 |
| `Prompt` | 给模型的工作说明书 | 强制模型只能按资料回答 |
| `Runnable` / LCEL | 流水线零件 | 用 `|` 把检索、提示词和模型接起来 |

## 为什么引用不能交给模型

模型擅长写答案，但会偶尔编造文件名或页码。这里让模型只返回它使用的
`chunk_id`，程序检查该 ID 必须来自这次 Chroma 检索；随后再从 chunk 的 metadata
读取页码。因此“引用”是程序数据，不是模型猜测。

## 如何排查一个坏回答

按这个顺序，而不是一上来改提示词：

1. 运行 `ragapp.retrieve_preview.py`，看正确页是否被检索到。
2. 没找到：检查 Markdown、切块规则、embedding、`k` 值和 query。
3. 找到了但回答错：检查 prompt、模型和结构化输出。
4. 回答对但页码错：检查 `Document.metadata` 和引用生成代码。

## 当前边界

- 目前没有 OCR；假设上游已提供包含文字层的 PDF。
- 当前只有一份本地私有产品资料，原文件、Markdown、Chroma 都不提交 Git。
- `ragapp/langgraph_rag.py` 已用 LangGraph 给“资料是否充足”的结果增加条件分支：拒答前最多改写一次问题并重检索。下一步可扩展为转人工处理、Langfuse trace 和前端状态展示。
