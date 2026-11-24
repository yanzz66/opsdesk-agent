
"""Test semantic search over the local knowledge base."""

from knowledge_base import search_knowledge


TEST_QUESTIONS = [
    "公司 VPN 无法连接，身份验证失败怎么办？",
    "员工账号被锁定应该如何处理？",
    "办公电脑连接 Wi-Fi 后无法上网怎么办？",
]


def main():
    for question in TEST_QUESTIONS:
        print("\n" + "=" * 60)
        print("Question:", question)

        results = search_knowledge(question, k=2)

        assert results, "No documents retrieved"

        for index, document in enumerate(results, start=1):
            print(f"\n--- Result {index} ---")
            print("Source:", document.metadata["source"])
            print("Content:")
            print(document.page_content)


if __name__ == "__main__":
    main()