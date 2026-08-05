"""不调用聊天模型，只检查 Chroma 是否找到了正确的资料和页码。

运行：
    .venv/bin/python -m ragapp.retrieve_preview
"""

from ragapp.index_markdown import get_vectorstore


QUESTIONS = [
    "这份癌症保险的等候期是多久？",
    "确诊早期癌症后可以获得什么保障？",
    "保单持有人可以怎样更改受保人？",
]


def main() -> None:
    vectorstore = get_vectorstore()
    for question in QUESTIONS:
        print(f"\n{'=' * 72}\n问题：{question}")
        # distance 是向量距离，不等于“百分之多少准确”。这里只用它辅助排序观察。
        hits = vectorstore.similarity_search_with_score(question, k=3)
        for rank, (document, distance) in enumerate(hits, start=1):
            metadata = document.metadata
            preview = document.page_content.replace("\n", " ")[:220]
            print(
                f"\n{rank}. [{metadata['source_file']} 第 {metadata['page']} 页 "
                f"chunk {metadata['chunk_index']}] distance={distance:.3f}\n{preview}..."
            )


if __name__ == "__main__":
    main()
