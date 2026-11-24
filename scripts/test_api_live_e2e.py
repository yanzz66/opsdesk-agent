
"""Live HTTP integration test for OpsDesk Agent.

Requires a running local Ollama service with qwen3:8b.
All database writes use temporary SQLite files.
"""

import os

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]


def expect(response, status_code):
    assert response.status_code == status_code, (
        f"Expected HTTP {status_code}, "
        f"got {response.status_code}: {response.text}"
    )
    return response.json()


def main():
    with TemporaryDirectory(
        prefix="opsdesk_live_api_test_",
        dir=ROOT,
    ) as temp_dir:

        temp = Path(temp_dir)
        ticket_db = temp / "tickets.db"

        user_key = "user-" + uuid4().hex
        approver_key = "approver-" + uuid4().hex

        env = {
            "OPSDESK_CHECKPOINT_BACKEND": "sqlite",
            "OPSDESK_CHECKPOINT_PATH": str(
                temp / "checkpoints.db"
            ),
            "OPSDESK_DB_PATH": str(ticket_db),
            "OPSDESK_TICKET_PLANNER": "llm",
            "OPSDESK_USER_KEY": user_key,
            "OPSDESK_APPROVER_KEY": approver_key,
        }

        # Set environment variables before importing workflow.
        with patch.dict(os.environ, env):

            from api.app import app
            from ticket_store import count_tickets
            from workflow import _checkpoint_connection

            user_headers = {
                "X-OpsDesk-User-Key": user_key
            }
            approver_headers = {
                "X-OpsDesk-Approver-Key": approver_key
            }

            try:
                with TestClient(app) as client:

                    print("=== Test 1: Model Failure ===")

                    # Simulate a planning failure.
                    # No database write should occur.
                    with patch(
                        "ticket_tool_planner."
                        "plan_ticket_with_tool_call",
                        side_effect=RuntimeError(
                            "Simulated planning failure"
                        ),
                    ):
                        response = client.post(
                            "/api/tickets",
                            json={
                                "description": "VPN 无法登录"
                            },
                            headers=user_headers,
                        )

                    expect(response, 503)
                    assert count_tickets(ticket_db) == 0

                    print("PASS: Failed planning did not write")

                    print("\n=== Test 2: Real Qwen3 Planning ===")

                    response = client.post(
                        "/api/tickets",
                        json={
                            "description": "公司 VPN 无法登录"
                        },
                        headers=user_headers,
                    )

                    pending = expect(response, 201)

                    assert pending["status"] == "pending_approval"
                    assert pending["draft"]["issue_type"] == "vpn"
                    assert pending["draft"]["title"]
                    assert count_tickets(ticket_db) == 0

                    thread_id = pending["thread_id"]

                    print("Thread ID:", thread_id)
                    print("Issue:", pending["draft"]["issue_type"])
                    print("Title:", pending["draft"]["title"])
                    print("PASS: Qwen3 produced a ticket draft")

                    print("\n=== Test 3: Pending State ===")

                    response = client.get(
                        f"/api/tickets/workflows/{thread_id}",
                        headers=approver_headers,
                    )

                    state = expect(response, 200)

                    assert state["status"] == "pending_approval"

                    print("PASS: Saved workflow retrieved")

                    print("\n=== Test 4: Human Approval ===")

                    response = client.post(
                        (
                            "/api/tickets/workflows/"
                            f"{thread_id}/decision"
                        ),
                        json={"approved": True},
                        headers=approver_headers,
                    )

                    approved = expect(response, 200)

                    assert approved["status"] == "open"
                    assert approved["ticket_id"]
                    assert count_tickets(ticket_db) == 1

                    ticket_id = approved["ticket_id"]

                    print("Ticket ID:", ticket_id)
                    print("PASS: Approved ticket written to SQLite")

                    print("\n=== Test 5: Ticket Query ===")

                    response = client.get(
                        f"/api/tickets/{ticket_id}",
                        headers=approver_headers,
                    )

                    stored = expect(response, 200)

                    assert stored["status"] == "open"
                    assert stored["request_id"] == (
                        pending["draft"]["request_id"]
                    )

                    print("PASS: Stored ticket retrieved")

                    print("\n=== Test 6: Duplicate Decision ===")

                    response = client.post(
                        (
                            "/api/tickets/workflows/"
                            f"{thread_id}/decision"
                        ),
                        json={"approved": True},
                        headers=approver_headers,
                    )

                    expect(response, 409)
                    assert count_tickets(ticket_db) == 1

                    print("PASS: Repeated decision blocked")

                    print("\n=== Test 7: Rejection ===")

                    response = client.post(
                        "/api/tickets",
                        json={
                            "description": "办公电脑无法联网"
                        },
                        headers=user_headers,
                    )

                    second = expect(response, 201)

                    response = client.post(
                        (
                            "/api/tickets/workflows/"
                            f"{second['thread_id']}/decision"
                        ),
                        json={"approved": False},
                        headers=approver_headers,
                    )

                    rejected = expect(response, 200)

                    assert rejected["status"] == "rejected"
                    assert count_tickets(ticket_db) == 1

                    print("PASS: Rejected ticket not written")

            finally:
                if _checkpoint_connection is not None:
                    _checkpoint_connection.close()

    print("\nAll live API E2E tests passed!")


if __name__ == "__main__":
    main()