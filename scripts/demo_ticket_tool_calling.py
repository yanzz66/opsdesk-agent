
"""Interactive demo: Qwen3 tool calling + human approval."""

import os

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import uuid4

from langgraph.types import Command

from ticket_store import count_tickets
from workflow import app


ROOT = Path(__file__).resolve().parents[1]


def main():
    # All demonstration writes go to a temporary database.
    with TemporaryDirectory(
        prefix="opsdesk_tool_demo_",
        dir=ROOT,
    ) as directory:

        db = Path(directory) / "tickets.db"

        with patch.dict(os.environ, {
            "OPSDESK_TICKET_PLANNER": "llm",
            "OPSDESK_DB_PATH": str(db),
        }):
            config = {
                "configurable": {
                    "thread_id": str(uuid4())
                }
            }

            request = "请帮我创建工单：公司 VPN 无法登录"

            print("=== Qwen3 Tool Calling Demo ===")
            print("Request:", request)

            # Step 1: Qwen3 proposes the ticket.
            # LangGraph then interrupts before any write.
            pending = app.invoke(
                {"request": request},
                config=config,
            )

            assert "__interrupt__" in pending
            assert count_tickets(db) == 0

            draft = pending["ticket_draft"]

            print("\nProposed ticket:")
            print("Request ID:", draft["request_id"])
            print("Category:", draft["category"])
            print("Issue type:", draft["issue_type"])
            print("Title:", draft["title"])
            print("Description:", draft["description"])

            print("\nDatabase rows before approval:", 0)

            # Step 2: Real human decision in the terminal.
            choice = input(
                "\nApprove this demo ticket? (y/N): "
            ).strip().lower()

            approved = choice == "y"

            # Step 3: Resume the same LangGraph thread.
            result = app.invoke(
                Command(resume=approved),
                config=config,
            )

            print("\nFinal result:")
            print("Status:", result["ticket_status"])
            print("Answer:", result["answer"])
            print(
                "Database rows after decision:",
                count_tickets(db),
            )

    print("\nDemo finished. Temporary database removed.")


if __name__ == "__main__":
    main()