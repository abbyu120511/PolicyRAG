"""
第 1 课:LangChain 的最小单元 —— ChatModel

你以前直接调 LLM API 大概是这样:拼一个 messages 数组的 JSON,POST 出去,解析返回。
LangChain 做的第一件事,就是把「模型」抽象成一个统一接口(ChatModel):
不管背后是千问、Claude 还是 GPT,用法完全一样,换模型只改一行初始化。

千问兼容 OpenAI 协议,所以用 langchain-openai 的 ChatOpenAI,指向 DashScope 的地址即可。
"""

# ── 1. 初始化模型:细节收敛在 llm_setup.py 里(连接地址、DNS 补丁等) ──
from llm_setup import get_llm

llm = get_llm("qwen-turbo", temperature=0)

# ── 2. 最简单的调用:invoke ──────────────────────────────────────
# 可以直接传字符串,LangChain 会帮你包装成一条 user 消息
resp = llm.invoke("用一句话解释什么是 LangChain")
print("【invoke 返回】", resp.content)
print("【返回类型】", type(resp).__name__)  # AIMessage —— 不是裸字符串!
print("【token 用量】", resp.usage_metadata)

# ── 3. 消息类型:LangChain 对话的通用语言 ─────────────────────────
# 你手写 API 时的 {"role": "system", ...} 在这里变成了类型化的消息对象。
# 后面学 Agent 和 LangGraph 时,状态里传来传去的就是这些 Message。
from langchain_core.messages import HumanMessage, SystemMessage

messages = [
    SystemMessage("你是一个只说文言文的助手。"),
    HumanMessage("介绍一下你自己"),
]
resp = llm.invoke(messages)
print("\n【带 system 提示】", resp.content)

# ── 4. 流式输出:stream ─────────────────────────────────────────
# invoke 换成 stream,返回一个 chunk 迭代器。所有 LangChain 组件都遵循
# invoke / stream / batch 这套统一接口(叫 Runnable 协议),下一课细讲。
print("\n【流式输出】", end="")
for chunk in llm.stream("写一首关于秋天的五言绝句"):
    print(chunk.content, end="", flush=True)
print()

# ── 5. 并发处理:batch ──────────────────────────────────────────
# batch 接收「一个列表」(方括号包起来),并发请求,按原顺序返回完整答案列表。
# 和 stream 的区别:stream 是一个问题的碎片流;batch 是多个问题各自的完整回答。
results = llm.batch(["写一首关于秋天的五言绝句", "写一首关于失业落寞的七言律诗"])
for i, msg in enumerate(results, 1):  # enumerate: 边遍历边计数
    print(f"\n【batch 第{i}首】\n{msg.content}")

# ═══════════════════════════════════════════════════════════════
# 练习(改完重新 uv run 01_hello_llm.py):
# 1. 把 model 改成 "qwen-turbo",感受速度差异
# 2. 把 temperature 改成 0,连续跑两次,观察输出是否变得稳定
# 3. 用 llm.batch(["问题1", "问题2"]) 并发处理两个问题
# ═══════════════════════════════════════════════════════════════
