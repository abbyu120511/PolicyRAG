"""
共享模型工厂:所有课程从这里拿模型实例。

把「连接哪家模型」收敛到一个模块是实战中的好习惯——换供应商时只改这一个文件。

本机的 Clash 开了 TUN + fake-IP,会把 dashscope-intl.aliyuncs.com 劫持进
代理隧道,而代理节点连不通阿里云国际。所以启动时先通过 DoH(DNS over HTTPS)
查到真实 IP,再覆盖 Python 的域名解析,让请求直连。

这一版比最初健壮了很多(拿真实报错换来的教训):
  1. 先检测 DNS 是否真的被劫持(解析结果在 198.18.x.x 段),没劫持就不打补丁
  2. DoH 有两个服务商可轮换,单个超时不至于全挂
  3. 查到的 IP 缓存到文件,网络抖动时用上次的结果兜底
如果你以后在 Clash 里给 aliyuncs.com 加了 DIRECT 规则,这个补丁会自动跳过。
"""

import os
import socket
from pathlib import Path

import httpx
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv()

QWEN_HOST = "dashscope-intl.aliyuncs.com"
BASE_URL = f"https://{QWEN_HOST}/compatible-mode/v1"

# 【Python】Path(__file__) 是当前文件的路径,.parent 是它所在目录。
# 缓存文件固定放在项目目录下,不管你从哪里运行脚本。
_IP_CACHE = Path(__file__).parent / ".qwen_ip_cache"

# DoH 服务商:阿里、腾讯。一个连不上就试下一个。
_DOH_URLS = [
    "https://223.5.5.5/resolve",
    "https://120.53.53.53/resolve",
]


def _dns_is_hijacked() -> bool:
    """正常解析一次,看结果是否落在 fake-IP 段(198.18.x.x)。"""
    try:
        ip = socket.gethostbyname(QWEN_HOST)
    except socket.gaierror:  # 连解析都失败,当作被劫持处理
        return True
    return ip.startswith("198.18.") or ip.startswith("198.19.")


def _lookup_real_ip() -> str | None:
    """依次尝试各 DoH 服务商查真实 IP;全失败则返回缓存;再没有就 None。"""
    for url in _DOH_URLS:
        try:
            resp = httpx.get(
                url,
                params={"name": QWEN_HOST, "type": "A"},
                timeout=5,  # 【教训】上一版没兜底,DoH 一超时整个程序就起不来
            )
            ip = next(a["data"] for a in resp.json()["Answer"] if a["type"] == 1)
            _IP_CACHE.write_text(ip)  # 查到就缓存,给下次网络抖动时兜底
            return ip
        except Exception:
            continue  # 这家连不上,换下一家

    if _IP_CACHE.exists():
        print(f"[llm_setup] DoH 全部超时,使用缓存 IP: {_IP_CACHE.read_text()}")
        return _IP_CACHE.read_text().strip()
    return None


def _patch_dns() -> None:
    if not _dns_is_hijacked():
        return  # DNS 正常(比如 Clash 关了或加了直连规则),无需补丁

    real_ip = _lookup_real_ip()
    if real_ip is None:
        raise RuntimeError(
            "无法获取千问服务器的真实 IP:DoH 查询失败且无缓存。\n"
            "请检查网络,或在 Clash 中给 aliyuncs.com 添加 DIRECT 规则。"
        )

    _orig = socket.getaddrinfo

    def patched(host, *args, **kwargs):
        if host == QWEN_HOST:
            host = real_ip
        return _orig(host, *args, **kwargs)

    socket.getaddrinfo = patched


_patch_dns()


def get_llm(model: str = "qwen-plus", **kwargs) -> ChatOpenAI:
    """返回一个连接千问的 ChatModel。temperature 等参数可透传覆盖。"""
    return ChatOpenAI(
        model=model,
        api_key=os.environ["DASHSCOPE_API_KEY"],
        base_url=BASE_URL,
        **kwargs,
    )


def get_embeddings():
    """返回千问的向量化模型(把文本变成向量,RAG 检索用)。"""
    from langchain_openai import OpenAIEmbeddings

    return OpenAIEmbeddings(
        model="text-embedding-v3",
        api_key=os.environ["DASHSCOPE_API_KEY"],
        base_url=BASE_URL,
        # 千问的 embedding 接口一次最多接收 10 条文本,这里让 LangChain 分批发
        chunk_size=10,
        # 该接口不支持 OpenAI 的 base64 编码返回,显式要求返回 float 数组
        check_embedding_ctx_length=False,
    )
