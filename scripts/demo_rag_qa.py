
"""Test OpsDesk RAG question answering."""

from rag_qa import answer_with_rag, NO_EVIDENCE


TEST_QUESTIONS = [
    "公司 VPN 无法连接，身份验证失败怎么办？",
    "员工账号被锁定应该如何处理？",
    "办公电脑连接 Wi-Fi 后无法上网怎么办？",
    "公司员工每年有多少天带薪年假？",
]


def main():
    print("=== OpsDesk RAG QA Test ===")

    for question in TEST_QUESTIONS:
        print("\n" + "=" * 60)
        print("Question:", question)

        result = answer_with_rag(question, k=3)

        print("\nAnswer:")
        print(result["answer"])

        print("\nRetrieved sources:")

        for item in result["sources"]:
            print(
                f"{item['label']} {item['source']}"
            )

        print("\nCited sources:")

        for item in result["cited_sources"]:
            print(
                f"{item['label']} {item['source']}"
            )

        if (
            not result["cited_sources"]
            and result["answer"] != NO_EVIDENCE
        ):
            print(
                "WARNING: No recognized source citation "
                "was found in the answer."
            )

    print("\nRAG QA demo finished!")


if __name__ == "__main__":
    main()