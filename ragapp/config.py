"""集中管理路径和常量。改配置只来这一个文件——和 llm_setup 同一个思想。"""

from pathlib import Path

# 项目根目录(config.py 的上上级)。用代码算路径,而不是写死
# "/Users/abbyyu/...",这样项目拷到任何机器、任何目录都能跑。
ROOT = Path(__file__).parent.parent

DOCS_DIR = ROOT / "ragapp" / "docs"        # 上传的 PDF 原件存这里
CHROMA_DIR = ROOT / "ragapp" / "chroma_db"  # 向量库落盘目录

DOCS_DIR.mkdir(parents=True, exist_ok=True)   # 目录不存在就创建

CHUNK_SIZE = 500      # 每块字数
CHUNK_OVERLAP = 100   # 相邻块重叠
TOP_K = 4             # 检索返回块数
