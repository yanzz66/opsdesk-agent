"""Test ticket APIs with isolated SQLite databases."""

import os

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]


def main():
    with TemporaryDirectory(
        prefix="opsdesk_api_ticket_test_",
        dir=ROOT,
    ) as temp_dir:

        temp = Path(temp_dir)
        ticket_db = temp / "tickets.db"

        env = {
            "OPSDESK_CHECKPOINT_BACKEND": "sqlite",
            "OPSDESK_CHECKPOINT_PATH": str(
                temp / "checkpoints.db"
            ),
            "OPSDESK_DB_PATH": str(ticket_db),
            "OPSDESK_TICKET_PLANNER": "rule",
            "OPSDESK_USER_KEY": "test-user-key",
            "OPSDESK_APPROVER_KEY": "test-approver-key",
        }

        # Environment must be configured BEFORE
        # the workflow module is imported.
        with patch.dict(os.environ, env):

            from api.app import app
            from ticket_store import count_tickets
            from workflow import _checkpoint_connection

            user_headers = {
                "X-OpsDesk-User-Key": "test-user-key"
            }

            approver_headers = {
                "X-OpsDesk-Approver-Key": "test-approver-key"
            }

            try:
                with TestClient(app) as client:

                    print("=== Test 1: Health ===")
                    response = client.get("/health")
                    assert response.status_code == 200
                    print("PASS: Health endpoint")

                    print("\n=== Test 2: User API Key ===")

                    response = client.post(
                        "/api/tickets",
                        json={
                            "description": "VPN 无法登录"
                        },
                    )

                    assert response.status_code == 401
                    print("PASS: Missing key blocked")

                    print("\n=== Test 3: Input Validation ===")

                    response = client.post(
                        "/api/tickets",
                        json={"description": "  "},
                        headers=user_headers,
                    )

                    assert response.status_code == 422
                    print("PASS: Empty description blocked")

                    print("\n=== Test 4: Create Pending Ticket ===")

                    response = client.post(
                        "/api/tickets",
                        json={
                            "description": "公司 VPN 无法登录"
                        },
                        headers=user_headers,
                    )

                    assert response.status_code == 201

                    data = response.json()
                    thread_id = data["thread_id"]

                    assert data["status"] == "pending_approval"
                    assert data["draft"]["request_id"]
                    assert data["ticket_id"] is None
                    assert count_tickets(ticket_db) == 0

                    print("Thread ID:", thread_id)
                    print("PASS: Ticket pending approval")

                    print("\n=== Test 5: Approval Authorization ===")

                    url = (
                        f"/api/tickets/workflows/{thread_id}"
                    )

                    response = client.get(url)
                    assert response.status_code == 401

                    response = client.get(
                        url,
                        headers={
                            "X-OpsDesk-Approver-Key": "wrong-key"
                        },
                    )
                    assert response.status_code == 403

                    response = client.get(
                        url,
                        headers=approver_headers,
                    )

                    assert response.status_code == 200
                    assert response.json()["status"] == "pending_approval"

                    print("PASS: Approver authentication")

                    print("\n=== Test 6: Approve Ticket ===")

                    decision_url = url + "/decision"

                    response = client.post(
                        decision_url,
                        json={"approved": True},
                        headers=approver_headers,
                    )

                    print("Approval HTTP status:", response.status_code)
                    print("Approval response:", response.text)
                    assert response.status_code == 200

                    approved = response.json()
                    assert approved["status"] == "open"
                    assert approved["ticket_id"]
                    assert count_tickets(ticket_db) == 1

                    ticket_id = approved["ticket_id"]

                    print("Ticket ID:", ticket_id)
                    print("PASS: Approved ticket stored")

                    print("\n=== Test 7: Query Ticket ===")

                    response = client.get(
                        f"/api/tickets/{ticket_id}",
                        headers=approver_headers,
                    )

                    assert response.status_code == 200

                    stored = response.json()

                    assert stored["ticket_id"] == ticket_id
                    assert stored["status"] == "open"
                    assert count_tickets(ticket_db) == 1

                    print("PASS: Ticket read from SQLite")

                    print("\n=== Test 8: Duplicate Approval ===")

                    response = client.post(
                        decision_url,
                        json={"approved": True},
                        headers=approver_headers,
                    )

                    assert response.status_code == 409
                    assert count_tickets(ticket_db) == 1

                    print("PASS: Duplicate approval blocked")

                    print("\n=== Test 9: Reject Ticket ===")

                    response = client.post(
                        "/api/tickets",
                        json={
                            "description": "办公电脑无法上网"
                        },
                        headers=user_headers,
                    )

                    assert response.status_code == 201

                    reject_thread = response.json()["thread_id"]

                    response = client.post(
                        (
                            "/api/tickets/workflows/"
                            f"{reject_thread}/decision"
                        ),
                        json={"approved": False},
                        headers=approver_headers,
                    )

                    assert response.status_code == 200
                    assert response.json()["status"] == "rejected"

                    # Only the previously approved ticket exists.
                    assert count_tickets(ticket_db) == 1

                    print("PASS: Rejected ticket not stored")

                    print("\n=== Test 10: Unknown Resources ===")

                    unknown_id = str(uuid4())

                    response = client.get(
                        f"/api/tickets/workflows/{unknown_id}",
                        headers=approver_headers,
                    )
                    assert response.status_code == 404

                    response = client.get(
                        f"/api/tickets/{unknown_id}",
                        headers=approver_headers,
                    )
                    assert response.status_code == 404

                    print("PASS: Unknown resources handled")

            finally:
                # Release SQLite before TemporaryDirectory
                # cleans up its files on Windows.
                if _checkpoint_connection is not None:
                    _checkpoint_connection.close()

    print("\nAll ticket API tests passed!")


if __name__ == "__main__":
    main()