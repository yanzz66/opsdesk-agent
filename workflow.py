
"""OpsDesk Agent v0.1: workflow routing and human approval."""

import os
import sqlite3
from uuid import uuid4
from ticket_store import create_ticket

from typing import TypedDict

from rag_qa import answer_with_rag
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command, interrupt
from pathlib import Path

class DeskState(TypedDict, total=False):
    request: str
    intent: str
    answer: str

    # RAG results
    sources: list[dict[str, str]]
    cited_sources: list[dict[str, str]]

    # Ticket handling
    ticket_draft: dict[str, str]
    approved: bool
    ticket_status: str
    ticket_id: str

def classify_request(state: DeskState) -> dict:
    """Route a request to knowledge Q&A or ticket handling."""
    text = state["request"]
    keywords = ("创建工单", "提交工单", "报修", "开工单")
    intent = "ticket" if any(k in text for k in keywords) else "qa"
    return {"intent": intent}


def route_request(state: DeskState) -> str:
    return state["intent"]


def knowledge_qa(state: DeskState) -> dict:
    """Answer questions using the local RAG knowledge base."""

    question = state["request"]

    result = answer_with_rag(
        question=question,
        k=3,
    )

    return {
        "answer": result["answer"],
        "sources": result["sources"],
        "cited_sources": result["cited_sources"],
    }



def prepare_ticket(state: DeskState) -> dict:
    """Prepare a ticket with optional Qwen3 tool calling."""

    request = state["request"].strip()

    if not request:
        raise ValueError("Ticket request cannot be empty")

    if len(request) > 2000:
        raise ValueError("Ticket request is too long")

    # The original business parameters are controlled
    # by Python, not by the language model.
    draft = {
        "request_id": str(uuid4()),
        "category": "IT支持",
        "description": request,
    }

    planner = os.getenv(
        "OPSDESK_TICKET_PLANNER",
        "rule",
    ).strip().lower()

    if planner == "llm":
        from ticket_tool_planner import plan_ticket_with_tool_call

        proposal = plan_ticket_with_tool_call(request)

        # Only accept two model-generated fields.
        draft["issue_type"] = proposal["issue_type"]
        draft["title"] = proposal["title"]

    elif planner != "rule":
        raise ValueError(
            f"Unsupported ticket planner: {planner}"
        )

    return {
        "ticket_draft": draft,
        "ticket_status": "pending_approval",
    }

def human_approval(state: DeskState) -> dict:
    """Pause execution until a human makes a decision."""
    decision = interrupt({
        "message": "是否批准创建工单？",
        "ticket": state["ticket_draft"],
    })

    if not isinstance(decision, bool):
        raise ValueError("Approval must be a boolean")

    return {"approved": decision}


def finish_ticket(state: DeskState) -> dict:
    """Persist an approved ticket to SQLite."""

    # Step 1: Reject unapproved operations.
    if state.get("approved") is not True:
        return {
            "ticket_status": "rejected",
            "answer": "审批未通过，工单创建已取消。",
        }

    # Step 2: Read the prepared ticket.
    draft = state["ticket_draft"]

    # Step 3: Create an idempotent SQLite record.
    ticket = create_ticket(
        request_id=draft["request_id"],
        category=draft["category"],
        description=draft["description"],
        approved=True,
        db_path=os.getenv("OPSDESK_DB_PATH") or None,
    )

    # Step 4: Return the actual database result.
    return {
        "ticket_id": ticket["ticket_id"],
        "ticket_status": ticket["status"],
        "answer": (
            "审批通过，工单已成功创建。\n"
            f"工单编号：{ticket['ticket_id']}\n"
            f"当前状态：{ticket['status']}"
        ),
    }


def build_checkpointer():
    """Select memory or SQLite checkpoint storage."""

    backend = os.getenv(
        "OPSDESK_CHECKPOINT_BACKEND",
        "memory",
    ).strip().lower()

    if backend == "memory":
        return InMemorySaver(), None

    if backend != "sqlite":
        raise ValueError(
            f"Unsupported checkpoint backend: {backend}"
        )

    from langgraph.checkpoint.sqlite import SqliteSaver

    # Keep workflow checkpoints separate
    # from the business ticket database.
    default_path = (
        Path(__file__).resolve().parent
        / "data"
        / "checkpoints.db"
    )

    db_path = Path(
        os.getenv("OPSDESK_CHECKPOINT_PATH")
        or default_path
    )

    db_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    # The synchronous saver uses a lock.
    connection = sqlite3.connect(
        db_path,
        timeout=10,
        check_same_thread=False,
    )

    saver = SqliteSaver(connection)
    saver.setup()

    return saver, connection

builder = StateGraph(DeskState)

builder.add_node("classify", classify_request)
builder.add_node("knowledge_qa", knowledge_qa)
builder.add_node("prepare_ticket", prepare_ticket)
builder.add_node("approval", human_approval)
builder.add_node("finish_ticket", finish_ticket)

builder.add_edge(START, "classify")

builder.add_conditional_edges(
    "classify",
    route_request,
    {
        "qa": "knowledge_qa",
        "ticket": "prepare_ticket",
    },
)

builder.add_edge("knowledge_qa", END)
builder.add_edge("prepare_ticket", "approval")
builder.add_edge("approval", "finish_ticket")
builder.add_edge("finish_ticket", END)

checkpointer, _checkpoint_connection = (
    build_checkpointer()
)

app = builder.compile(
    checkpointer=checkpointer
)


if __name__ == "__main__":
    faq_config = {"configurable": {"thread_id": "demo-faq"}}

    faq_result = app.invoke(
        {"request": "怎么连接公司 VPN？"},
        config=faq_config,
    )
    print("知识问答:", faq_result["answer"])

    ticket_config = {
        "configurable": {"thread_id": "demo-ticket"}
    }

    pending = app.invoke(
        {"request": "请帮我创建工单：公司 VPN 无法登录"},
        config=ticket_config,
    )

    assert "__interrupt__" in pending
    print("人工审批请求:", pending["__interrupt__"][0].value)

    choice = input("是否批准创建工单？(y/n): ")
    approved = choice.strip().lower() == "y"

    result = app.invoke(
        Command(resume=approved),
        config=ticket_config,
    )

    print("工单状态:", result["ticket_status"])
    print("处理结果:", result["answer"])