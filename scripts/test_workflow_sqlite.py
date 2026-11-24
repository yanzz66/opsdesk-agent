
"""OpsDesk Agent: LangGraph + SQLite integration tests."""

import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import uuid4

from langgraph.types import Command

from ticket_store import count_tickets, get_ticket
from workflow import app, finish_ticket


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def new_config():
    """Create an isolated LangGraph thread."""
    return {
        "configurable": {
            "thread_id": f"opsdesk-sqlite-{uuid4().hex}"
        }
    }


def start_ticket_request(request):
    """Run the workflow until human approval is required."""

    config = new_config()

    pending = app.invoke(
        {"request": request},
        config=config,
    )

    assert pending["intent"] == "ticket"
    assert "__interrupt__" in pending
    assert pending["ticket_status"] == "pending_approval"

    draft = pending["ticket_draft"]

    assert draft["request_id"]
    assert draft["category"] == "IT支持"
    assert draft["description"] == request

    return pending, config


def main():
    # Use a temporary database in the project directory.
    # The actual data/tickets.db is not modified.
    with TemporaryDirectory(
        prefix="opsdesk_workflow_test_",
        dir=PROJECT_ROOT,
    ) as temp_dir:

        test_db = Path(temp_dir) / "tickets.db"

        # Inject the isolated test database path.
        with patch.dict(
            os.environ,
            {"OPSDESK_DB_PATH": str(test_db)},
        ):

            print("=== Test 1: No Write Before Approval ===")

            pending, config = start_ticket_request(
                "请帮我创建工单：公司 VPN 无法登录"
            )

            assert count_tickets(test_db) == 0

            print("Status:", pending["ticket_status"])
            print("PASS: No database write before approval")

            print("\n=== Test 2: Approved Ticket ===")

            approved_result = app.invoke(
                Command(resume=True),
                config=config,
            )

            assert approved_result["approved"] is True
            assert approved_result["ticket_status"] == "open"
            assert approved_result["ticket_id"]
            assert count_tickets(test_db) == 1

            ticket = get_ticket(
                approved_result["ticket_id"],
                db_path=test_db,
            )

            assert ticket is not None
            assert ticket["request_id"] == (
                pending["ticket_draft"]["request_id"]
            )
            assert ticket["category"] == "IT支持"
            assert ticket["description"] == (
                pending["ticket_draft"]["description"]
            )
            assert ticket["status"] == "open"

            print("Ticket ID:", ticket["ticket_id"])
            print("Status:", ticket["status"])
            print("PASS: Approved ticket persisted to SQLite")

            print("\n=== Test 3: Rejected Ticket ===")

            rejected_pending, rejected_config = (
                start_ticket_request(
                    "请帮我创建工单：办公电脑无法联网"
                )
            )

            assert count_tickets(test_db) == 1

            rejected_result = app.invoke(
                Command(resume=False),
                config=rejected_config,
            )

            assert rejected_result["approved"] is False
            assert rejected_result["ticket_status"] == "rejected"

            # The rejected request must not create a record.
            assert count_tickets(test_db) == 1

            print("Status:", rejected_result["ticket_status"])
            print("PASS: Rejected ticket not persisted")

            print("\n=== Test 4: Idempotent Write ===")

            # Simulate re-executing the same approved
            # business operation using the saved state.
            repeated = finish_ticket(approved_result)

            assert repeated["ticket_id"] == ticket["ticket_id"]
            assert repeated["ticket_status"] == "open"

            # Still exactly one ticket.
            assert count_tickets(test_db) == 1

            print("Ticket ID:", repeated["ticket_id"])
            print("PASS: Duplicate write prevented")

            print("\n=== Test 5: Approval Guard ===")

            unapproved_state = {
                **approved_result,
                "approved": False,
            }

            blocked = finish_ticket(unapproved_state)

            assert blocked["ticket_status"] == "rejected"
            assert count_tickets(test_db) == 1

            print("PASS: Unapproved execution blocked")

    print("\nAll LangGraph SQLite workflow tests passed!")


if __name__ == "__main__":
    main()