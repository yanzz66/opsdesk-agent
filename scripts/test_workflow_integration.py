
"""OpsDesk Agent: LangGraph + RAG integration test."""

from uuid import uuid4

from langgraph.types import Command

from rag_qa import NO_EVIDENCE
from workflow import app


def new_config():
    """Use a fresh thread for every test."""
    return {
        "configurable": {
            "thread_id": f"opsdesk-test-{uuid4().hex}"
        }
    }


def test_knowledge_qa():
    print("\n=== Test 1: RAG Knowledge QA ===")

    result = app.invoke(
        {
            "request": "公司 VPN 无法连接，身份验证失败怎么办？"
        },
        config=new_config(),
    )

    print("Intent:", result["intent"])
    print("Answer:", result["answer"])
    print("Sources:", result.get("sources", []))
    print("Cited:", result.get("cited_sources", []))

    assert result["intent"] == "qa"
    assert result["answer"].strip()
    assert result["answer"] != NO_EVIDENCE

    assert result.get("cited_sources"), (
        "RAG answer did not include recognized citations."
    )

    print("PASS: RAG knowledge QA")


def test_unknown_question():
    print("\n=== Test 2: Unknown Knowledge ===")

    result = app.invoke(
        {
            "request": "公司员工每年有多少天带薪年假？"
        },
        config=new_config(),
    )

    print("Answer:", result["answer"])

    assert result["intent"] == "qa"
    assert result["answer"] == NO_EVIDENCE
    assert not result.get("cited_sources")

    print("PASS: Unknown knowledge handled")


def test_ticket_approval(approved: bool):
    print(
        f"\n=== Test 3: Ticket Approval = {approved} ==="
    )

    config = new_config()

    pending = app.invoke(
        {
            "request": "请帮我创建工单：公司 VPN 无法登录"
        },
        config=config,
    )

    assert pending["intent"] == "ticket"
    assert "__interrupt__" in pending

    print(
        "Approval request:",
        pending["__interrupt__"][0].value,
    )

    result = app.invoke(
        Command(resume=approved),
        config=config,
    )

    expected_status = "open" if approved else "rejected"

    assert result["ticket_status"] == expected_status

    print("Ticket status:", result["ticket_status"])
    print("Answer:", result["answer"])
    print("PASS: Ticket approval workflow")


if __name__ == "__main__":
    test_knowledge_qa()
    test_unknown_question()
    test_ticket_approval(True)
    test_ticket_approval(False)

    print("\nAll workflow integration tests passed!")