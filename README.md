# LangChain & LangGraph 实战课

环境:Python 3.12 + uv,LangChain 1.x + LangGraph 1.x,模型用阿里云千问(DashScope OpenAI 兼容接口)。

运行方式:`uv run 01_hello_llm.py`

## 课程路线

| 课 | 文件 | 学什么 |
|---|------|--------|
| 1 | `01_hello_llm.py` | 连接千问、消息类型、invoke/stream —— LangChain 的最小单元 |
| 2 | `02_chains.py` | LCEL 管道(prompt \| model \| parser)、结构化输出 |
| 3 | `03_rag.py` | 文档加载 → 切分 → 向量化 → 检索 → 带引用的问答 |
| 4 | `04_tools_agent.py` | @tool 定义工具、create_agent 自主调用工具 |
| 5 | `05_langgraph_basics.py` | StateGraph、节点、条件边 —— 手写一个图 |
| 6 | `06_langgraph_agent.py` | 带记忆(checkpointer)的多轮 Agent,RAG + 工具结合 |

每课文件里有注释讲解,跑通后改一改再跑,是最快的学法。

## MVP：保险 PDF RAG

真实保险资料只放在 `private_docs/`，转换结果、向量库等本地数据只放在
`storage/`；这两个目录已被 Git 忽略，不会上传到 GitHub。

目前先使用已有文字层的 PDF，不做 OCR。下面的命令会把每一页的原生文本转为
Markdown，并保留 `<!-- page: 页码 -->` 标记，供后续 RAG 引用具体 PDF 页码：

```bash
.venv/bin/python -m ragapp.pdf_to_markdown
```

转换后的原始 Markdown 不会被覆盖。下面的命令只做可解释的格式清洗（断行和
高置信度、非合规类的重复页眉/页脚），并分别写出清洗后的 Markdown 和逐页 JSON
报告。疑似页码只会记录在报告中，不自动删除，避免误删保费表中的数字：

```bash
.venv/bin/python -m ragapp.clean_markdown
```

将清洗后的 Markdown 按页切块时，每一个 chunk 都会带上原 PDF 的文件名和页码。
默认命令只预览本地切块，不会调用模型服务：

```bash
.venv/bin/python -m ragapp.index_markdown
```

确认私有内容可以发送到 embedding 服务后，再用 `--index` 写入本地 Chroma：

```bash
.venv/bin/python -m ragapp.index_markdown --index
```

入库后，先不调用聊天模型，直接检查 Chroma 返回的文本块和页码：

```bash
.venv/bin/python -m ragapp.retrieve_preview
```

第一条 RAG 问答链使用 `Retriever → Prompt → ChatModel → Pydantic 结构化输出`。模型只根据
检索到的资料回答。它通过 Pydantic 结构化输出返回“证据是否充分”和所用 chunk ID；
程序会验证这些 ID 确实来自本次检索，再由 metadata 生成页码引用，而不是由模型编造：

```bash
.venv/bin/python -m ragapp.rag_chat --question "这份癌症保险的等候期是多久？"
```

零基础学习时，可按 [`docs/langchain_rag_guide.md`](docs/langchain_rag_guide.md) 的顺序阅读
本项目代码与核心概念。

如果需要从“项目全貌、设计取舍、Python/LangChain/LangGraph 学习重点、排错思路”系统复盘，
请阅读 [`docs/policyrag_project_handbook.md`](docs/policyrag_project_handbook.md)。

## LangGraph：带条件重试的 RAG

`ragapp/langgraph_rag.py` 将 RAG 表达成一个状态图：先检索和回答；若模型判断证据不足，
最多改写一次检索查询并重试，仍不足则拒答。这样既不会一遇到检索不佳就放弃，也不会无限循环。

```bash
.venv/bin/python -m ragapp.langgraph_rag --question "这份癌症保险的等候期是多久？"
```

## FastAPI 后端

将 LangGraph 工作流封装成本地 API；前端只需要调用 `/chat`，不直接接触模型、Chroma 或私有文件路径。

```bash
.venv/bin/uvicorn ragapp.api:app --reload
```

启动后访问 `http://127.0.0.1:8000/docs` 查看接口文档。`GET /documents` 返回文件清单，
`POST /chat` 返回回答、是否有足够证据、检索次数和可跳转 PDF 的页码引用。

### 知识库管理接口

- `POST /documents/upload`：上传本地 PDF 或 Markdown；上传后默认不启用。
- `POST /documents/{filename}/enable`：执行转换、清洗、向量化并加入 Chroma。
- `POST /documents/{filename}/disable`：从 Chroma 移除，原文件仍保留在本机。
- `DELETE /documents/{filename}`：下架并移除原件、向量和派生文件。
- `GET /documents/{filename}/chunks`：只读返回已清洗资料按当前规则生成的 chunk、页码和 metadata，供前端预览；不会调用 embedding 或修改 Chroma。

## React 前端

前端位于 `frontend/`，有两个独立页面：

- **智能问答**：问题、RAG 答案、可点击引用，以及右侧 PDF 证据阅读器。
- **知识库管理**：PDF/Markdown 上传、处理状态、启用/停用和下架。
- **资料检视器**：从已处理文档进入，按页预览 chunk 文本、metadata 与原始 PDF 页，方便检查切块质量。

先启动后端，再在第二个终端启动前端：

```bash
# 终端 1（项目根目录）
.venv/bin/uvicorn ragapp.api:app --reload

# 终端 2
cd frontend
npm install
npm run dev
```

浏览器访问 `http://127.0.0.1:5173`。
