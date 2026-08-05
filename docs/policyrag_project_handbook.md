# PolicyRAG Studio：项目说明与学习复盘

> 这是一个用于保险产品资料问答的本地 RAG（检索增强生成）MVP。它的目标不是让模型“背下”保险知识，而是让模型每次回答前先从受管控的资料库中查找证据，并把答案对应回原始文件和具体页码。

## 1. 项目要解决什么问题

保险产品资料通常篇幅长、版本多、条款和表格密集。业务人员想问“等候期是多久”“某项保障是否包含”时，传统做法是人工翻 PDF；直接问通用大模型又容易得到没有依据、甚至不属于该产品的回答。

这个项目把问题拆成三件事：

1. **资料可管理**：上传 PDF 或 Markdown，查看处理状态，并决定一份资料是否参与检索。
2. **回答有依据**：系统只把已启用资料中的相关内容交给模型；资料不够时应拒答，而不是猜测。
3. **证据可复核**：每条回答都附带真实的文件与页码；点击引用可在新标签页打开对应 PDF，并跳到该页。

它适合作为 AI 应用工程师方向的作品集：它不只是“调用一次大模型”，而是覆盖了文档处理、向量检索、LangChain 链、LangGraph 工作流、API、前端和可追溯性这些真实应用中的环节。

## 2. 当前主要功能

| 模块 | 用户能看到的功能 | 背后的处理 |
| --- | --- | --- |
| 知识库管理 | 上传 PDF/Markdown、查看页数和 chunk 数、启用、停用、下架 | 文件目录 + SQLite 目录表 + Chroma 向量库同步 |
| 文档预处理 | PDF 转 Markdown、清洗格式、输出逐页报告 | 保留原始文件；不使用 LLM 改写保险条款 |
| 切块检视器 | 按页浏览 chunk、文字、chunk ID 与 metadata，并可打开原始页 | 只读重建预览，不重新调用 embedding 或修改 Chroma |
| RAG 问答 | 输入问题，获得基于资料的回答 | 检索相关 chunk，再把“问题 + 资料”交给聊天模型 |
| 引用与证据 | 回答下显示文件与页码；右侧预览证据 PDF | 页码来自 `Document.metadata`，不是模型随口生成 |
| 检索重试 | 资料不足时最多改写一次检索查询并重试 | LangGraph 的条件分支，避免无限循环 |
| Web 界面 | macOS 风格的问答页和知识库管理页 | React + Vite 前端，FastAPI 后端 |

### 文档进入知识库的路径

```text
PDF / Markdown 上传
        ↓
保存到 private_docs/（不提交 Git）
        ↓
PDF：PyMuPDF 提取每页文字 → Markdown
Markdown：补齐来源和“第 1 页”边界
        ↓
可解释的格式清洗 + JSON 审计报告
        ↓
按“每一页”切成较小 chunks，并携带文件名、页码等 metadata
        ↓
Embedding（向量化） → 本地 Chroma
        ↓
启用后才允许参与问答检索
```

### 一次问答的路径

```text
用户问题
  → 把问题向量化
  → Chroma 找到最相近的 4 个文本块
  → Prompt 规定“只能使用这些资料回答”
  → 模型输出结构化结果（答案 / 证据是否足够 / 使用了哪些 chunk）
  → 程序校验证据 chunk 是否真的来自本次检索
  → 从 metadata 生成“文件名 + PDF 页码”引用
  → 前端显示答案、证据轨和可跳转 PDF 链接
```

## 3. 设计目的与关键取舍

### 资料私有，不进 GitHub

真实保险资料、清洗结果、向量库都保留在本机的 `private_docs/` 和 `storage/`。`.gitignore` 明确排除这两类内容，因此 GitHub 仓库只放代码、空目录占位文件和可公开的示例资料。这是处理企业资料时非常基础、但很重要的习惯。

### PDF 先转成带页码的 Markdown

当前 MVP 假设上游已经提供了有文字层的 PDF，不先解决 OCR。PyMuPDF 提取原生文字后，系统在每页前保留 `<!-- page: 25 -->` 这样的页码边界。后续切块永远不跨页，因此引用能精确回到原 PDF 页。

这是一种有意识的范围控制：保险扫描件、复杂表格和花花绿绿的版面确实需要 PaddleOCR 或文档解析服务，但先把“已经可读的资料如何可靠进入 RAG”做扎实，能更好地学习 LangChain 的核心问题。

### 清洗保守、可审计

清洗不会覆盖原始 Markdown，只会另写一份 cleaned Markdown 和一份 JSON 报告。它只合并明显由排版造成的断行，删除高频、非合规性的重复页眉页脚；疑似页码数字不会自动删掉，以免删掉费率表中的真实数据。

这里的原则是：**在金融/保险资料中，宁可保留一点噪声，也不要静默篡改原文。**

### 引用由程序生成，不让模型编造

模型会生成自然语言，但不能被完全信任来报页码。项目让模型返回本次回答使用的 `chunk_id`；程序只接受那些确实位于本次检索结果中的 ID，再从对应 `Document.metadata` 中读出 `source_file` 和 `page`。这减少了“答案看上去很像有引用，实际页码是模型编的”的风险。

### 启用和停用是检索权限，不是删除按钮

上传后的资料默认未启用。启用时才会转换、清洗、向量化并写入 Chroma；停用时仅从 Chroma 删除其 chunks，原文件仍在本地；下架才删除原件和派生文件。这个设计让知识库管理员能控制“哪一版资料可被问答”。

## 4. 技术栈

| 层 | 技术 | 在项目中的角色 |
| --- | --- | --- |
| 运行环境 | Python 3.12、uv | 管理 Python 版本、虚拟环境和依赖 |
| 模型接入 | DashScope/Qwen 的 OpenAI 兼容接口、`langchain-openai` | 聊天模型与 embedding 模型 |
| RAG 框架 | LangChain 1.x | Prompt、`Document`、Retriever、LCEL、结构化输出 |
| 工作流 | LangGraph 1.x | 检索 → 回答 → 判断是否重试 → 改写检索词的状态图 |
| 向量数据库 | Chroma（本地持久化） | 保存每个 chunk 的向量与 metadata，并做相似度检索 |
| 文档处理 | PyMuPDF、Markdown、正则表达式 | PDF 原生文本抽取、按页保留和可审计清洗 |
| 元数据目录 | SQLite（Python 内置 `sqlite3`） | 记录文件状态、启用状态、页数、chunk 数和错误信息 |
| 后端 API | FastAPI、Pydantic、Uvicorn | 提供 `/chat`、上传、启停、下架和 PDF 文件服务 |
| 前端 | React、Vite、原生 CSS | 问答、知识库管理、PDF 预览与 Hash 路由 |

> `faiss-cpu` 虽在依赖中，但当前 MVP 实际使用的是 Chroma；简历或项目介绍中不应把 FAISS 写成已落地的向量库。

## 5. 最值得掌握的 Python 基础（从本项目出发）

Python 不需要先学到“很厉害”才开始做 RAG。下面这些概念能支撑你读懂本项目的大部分代码。

### 函数：把一个小步骤装进可复用的盒子

```python
def format_docs(documents: list[Document]) -> str:
    return "..."
```

- `def`：定义一个函数。
- `documents`：传进来的输入。
- `list[Document]`：类型提示，意思是“这应该是一组 `Document`”；它帮助人和编辑器理解代码，不会自动把错误修好。
- `-> str`：函数应返回字符串。

例如 `format_docs` 只负责把检索到的资料卡拼成模型能读的上下文；`select_evidence` 只负责验证证据。让每个函数只做一件事，排错会容易很多。

### `dict`（字典）：带名字的数据包

```python
{"question": question, "documents": retriever.invoke(question)}
```

字典像一个贴好标签的收纳盒：用 `"question"` 找用户问题，用 `"documents"` 找检索结果。LangChain 和 LangGraph 经常用字典在步骤之间传数据。

### `list`（列表）与循环：处理一组资料

```python
for document in documents:
    print(document.metadata["page"])
```

检索不会只返回一段文本，而是返回多张 `Document` 资料卡。`for` 会一张一张处理它们；`metadata["page"]` 取出当前卡片的页码。

### 类与 Pydantic：把模型输出变成可检查的数据

```python
class RAGAnswer(BaseModel):
    answer: str
    has_sufficient_evidence: bool
    evidence_chunk_ids: list[str]
```

`class` 可以理解成一张“填写规范”。这里规定模型的回答必须有三栏：正文、证据是否足够、证据 ID 列表。`Pydantic` 会检查返回结果是否符合这张规范，远比解析一段随意文本可靠。

### `try / except / finally`：预期失败也要收尾

`enable_document` 处理文件时会依次转换、清洗和向量化，其中任一步都可能失败。`try` 放正常流程；`except` 捕获异常、把文档状态记为 `failed`；`finally` 适合做不管成功失败都该执行的收尾动作。前端请求也用同样思路，把网络失败展示为“请求失败”，而不是让页面崩掉。

### `Path`：安全地处理文件路径

`pathlib.Path` 比手写字符串路径更可靠。项目还用 `.resolve()` 和父目录检查，确保请求 `/documents/{filename}` 时无法借文件名跳出 `private_docs/` 目录读取别的文件。这叫路径穿越防护。

### 缓存和延迟导入：让不需要模型的接口更轻、更稳

`@lru_cache(maxsize=1)` 会让 FastAPI 进程只编译一次 LangGraph，而不是每次问答都重新搭图。`from llm_setup import get_llm` 放在 `build_graph()` 内部，意味着访问 `/health` 或 `/documents` 时不必先检查 API Key 和模型网络。

## 6. LangChain：常用的搭建思路

### 先理解四个核心对象

| 对象 | 通俗比喻 | 当前项目用途 |
| --- | --- | --- |
| `Document` | 一张带标签的资料卡 | `page_content` 是文本；`metadata` 有文件名、页码和 chunk 编号 |
| Embedding | 把一句话编码成坐标 | 让“等候期多长”和相关条款在向量空间更接近 |
| Retriever | 图书管理员 | 根据问题从 Chroma 取回最相关的资料卡 |
| Prompt | 给模型的工作说明书 | 限制模型只能用当前资料回答，并规定资料不足时拒答 |

### LCEL：用 `|` 组装一条数据流水线

项目里的核心结构可以概念化为：

```python
retrieve | add_context | RunnablePassthrough.assign(answer=prompt | structured_llm)
```

不要把 `|` 当成神秘语法。它的意思接近“左边的输出，交给右边当输入”。

1. `retrieve`：拿问题去检索，输出 `question` 和 `documents`。
2. `add_context`：把 documents 格式化成带 chunk ID 和页码的 `context`。
3. `prompt | structured_llm`：把 `question` 和 `context` 填进提示词，请模型按 `RAGAnswer` 的结构返回。
4. `RunnablePassthrough.assign(...)`：在保留原字典内容的同时，新增 `answer` 字段。

这比把所有步骤写成一个巨大的函数更利于观察输入输出，也更适合以后插入日志、重排或替换某一个环节。

### 一个可靠 RAG 链的最小模板

```text
先检查资料能否正确切块和检索
→ Retriever 找资料
→ Prompt 明确边界
→ 模型结构化输出
→ 程序校验证据
→ 再生成给用户看的引用
```

重点不是“提示词写得多漂亮”，而是每一步都有可验证的输入输出。比如：检索错了，先查 chunk 和 embedding；不要马上怪模型或疯狂改 Prompt。

## 7. LangGraph：什么时候需要，以及怎么搭

单条 LangChain 链适合固定的直线流程；当系统需要“根据结果决定下一步”时，LangGraph 更清楚。

当前图的状态和流程是：

```text
START
  → retrieve（按 search_query 检索）
  → answer（回答并判断证据是否充分）
  → [证据足够 / 达到最大次数] → END
  → [证据不足且还可重试] → rewrite_query
                               → retrieve
```

### `State` 是节点共享的白板

`RAGState` 记录 `original_question`、当前 `search_query`、重试次数、检索到的 documents、答案和 evidence。每个节点只返回自己更新的部分，例如 `retrieve` 只更新 `documents`，`rewrite_query` 只更新检索词和次数。

### 节点、边、条件边的三步法

1. **定义状态**：哪些数据要跨步骤保存？
2. **定义节点函数**：每个函数读取 state，返回要更新的字段。
3. **连接边**：固定顺序用 `add_edge`；需要决策时用 `add_conditional_edges`。

### 为什么一定要有最大重试次数

“证据不够就改写再试”如果没有上限，模型可能一直改写、一直调用 embedding 和 LLM，既花钱又卡住用户。当前 `MAX_RETRIEVAL_ATTEMPTS = 2` 是一个清晰的安全阀。生产环境可根据监控数据调整，或者在失败后转人工/创建工单。

## 8. 这个过程中遇到的问题，以及解决思路

| 现象 / 风险 | 可能原因 | 当前解决方法 | 可迁移的经验 |
| --- | --- | --- | --- |
| PDF 有文字，但文本断行、页眉页脚重复 | PDF 按视觉排版存储，不按语义段落存储 | 原始 Markdown 保留；只做保守清洗；输出 JSON 报告 | 文档处理先保真、再优化；不要让 LLM 静默改合同原文 |
| 回答可能有幻觉页码 | 模型会自然语言生成，并不知道真实文件结构 | 模型仅选 chunk ID；程序从 metadata 生成页码 | 引用、金额、权限等关键字段应由程序控制 |
| 正确条款没被找回 | 切块边界、chunk 大小、embedding、查询表达或 k 值不合适 | 用 `retrieve_preview.py` 先看真实检索结果，再决定改哪里 | 排 RAG 要先看检索，不要第一时间改 Prompt |
| 重复上传或重新启用后存在旧向量 | 同一资料不同版本的 chunks 同时留在库中 | 根据 `source_file` 先删除旧 chunks，再写入新 chunks | 向量库也需要“版本和删除”策略 |
| 上传的 Markdown 没有 PDF 页码 | Markdown 本身不一定有分页信息 | 为它补 `page: 1` 的来源边界 | 每种输入格式都要补齐统一的元数据契约 |
| 浏览器出现 `Load failed` | 前端端口从 5173 改到 5174，但后端 CORS 白名单未包含新来源 | FastAPI 的 `CORSMiddleware` 同时允许 localhost/127.0.0.1 的 5173、5174 | 前后端分端口时，先检查浏览器 Network 和 CORS 配置 |
| 点击引用无法直达页面 | 只显示文件名，不携带页码信息 | PDF URL 使用 `#page=N`，并以新标签页打开；前端保留证据预览 | 引用不仅要“显示”，还要让审核者能低成本复核 |
| 本机网络/代理让模型域名解析异常 | 本地代理的 fake-IP 或网络抖动 | 模型工厂中检测异常 DNS，DoH 兜底并缓存上次 IP | 把供应商网络适配收敛到一个模块，业务代码不要到处打补丁 |

## 9. 建议你重点阅读的代码顺序

下面的顺序是按“最容易建立直觉”安排的，不必一次看完。

1. [`llm_setup.py`](../llm_setup.py)：模型和 embedding 是如何统一配置的。
2. [`01_hello_llm.py`](../01_hello_llm.py)：先认识 `invoke`、`stream` 和消息对象。
3. [`02_chains.py`](../02_chains.py)：理解 LCEL 的 `Prompt | Model | Parser`。
4. [`ragapp/index_markdown.py`](../ragapp/index_markdown.py)：理解一个 `Document` 如何带上页码 metadata 进入 Chroma。
5. [`ragapp/retrieve_preview.py`](../ragapp/retrieve_preview.py)：理解“为什么先看检索结果”。
6. [`ragapp/rag_chat.py`](../ragapp/rag_chat.py)：本项目最关键的 LangChain RAG 链和证据校验。
7. [`ragapp/langgraph_rag.py`](../ragapp/langgraph_rag.py)：理解状态、节点、条件边和重试上限。
8. [`ragapp/api.py`](../ragapp/api.py)：理解怎样把 Python 工作流包装成前端可调用的 API。
9. [`frontend/src/App.jsx`](../frontend/src/App.jsx)：理解网页怎样请求 `/chat`，并把引用跳转到 PDF 指定页。

## 10. 当前 MVP 的边界与下一步

当前版本已经能作为一个完整的本地演示项目，但不是直接给企业上线的生产系统。它暂时没有登录与权限、对象存储、托管数据库、多用户隔离、异步任务队列、自动化测试集、系统化日志/Trace 和线上监控。

建议下一阶段按下面的优先级推进：

1. **测试**：先用 `pytest` 覆盖切块页码、引用验证、启用/停用和 API 的正常/失败路径。
2. **可观测性**：接入 Langfuse，记录每次问答的输入、检索 chunk、耗时、token、模型输出和人工/LLM-as-a-judge 评分；注意脱敏与企业数据权限。
3. **评测集**：建立一小组人工核验过的保险问题、标准答案和标准页码，持续测检索命中率、引用正确率、拒答正确率、响应时间。
4. **生产化存储**：文件放对象存储；目录信息放 PostgreSQL；向量库按企业规模选择托管向量数据库或 PostgreSQL + pgvector；SQLite 和本地 Chroma 保留给单机 MVP。
5. **异步化和权限**：大 PDF 入库放到后台任务；增加用户登录、角色权限、审计日志、文件版本和删除策略。
6. **复杂文档**：在已经有回归评测集的前提下，再接 OCR/表格解析 pipeline，并比较新旧解析质量。

## 11. 一句话项目介绍（可用于 GitHub / 面试）

> PolicyRAG Studio 是一个面向保险产品资料的本地 RAG 问答 MVP。我使用 LangChain 构建“检索—结构化回答—证据校验”链路，用 LangGraph 实现证据不足时的受限查询改写重试；系统支持 PDF/Markdown 知识库管理、页码级可追溯引用、FastAPI 接口和 React 前端，并将真实业务文档、向量库与代码仓库隔离管理。
