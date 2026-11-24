
"""Test SQLite ticket persistence and idempotency."""

from pathlib import Path
from tempfile import TemporaryDirectory

from ticket_store import (
    create_ticket,
    get_ticket,
    count_tickets,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main():
    # Use an isolated temporary DB inside the E drive
    # project. Do not modify the real tickets.db.
    with TemporaryDirectory(
        prefix="opsdesk_ticket_test_",
        dir=PROJECT_ROOT,
    ) as temp_dir:

        test_db = Path(temp_dir) / "tickets.db"

        print("=== Test 1: Rejected Write ===")

        try:
            create_ticket(
                request_id="test-request-001",
                category="IT支持",
                description="VPN 无法登录",
                approved=False,
                db_path=test_db,
            )
        except PermissionError:
            print("PASS: Rejected write blocked")
        else:
            raise AssertionError(
                "Unapproved write was allowed"
            )

        assert count_tickets(test_db) == 0

        print("\n=== Test 2: Approved Write ===")

        first = create_ticket(
            request_id="test-request-001",
            category="IT支持",
            description="VPN 无法登录",
            approved=True,
            db_path=test_db,
        )

        print("Ticket ID:", first["ticket_id"])
        print("Status:", first["status"])

        assert first["status"] == "open"
        assert count_tickets(test_db) == 1

        print("PASS: Approved ticket created")

        print("\n=== Test 3: Idempotency ===")

        repeated = create_ticket(
            request_id="test-request-001",
            category="IT支持",
            description="VPN 无法登录",
            approved=True,
            db_path=test_db,
        )

        assert (
            repeated["ticket_id"]
            == first["ticket_id"]
        )

        assert count_tickets(test_db) == 1

        print("PASS: No duplicate ticket")

        print("\n=== Test 4: Conflicting Request ===")

        try:
            create_ticket(
                request_id="test-request-001",
                category="IT支持",
                description="不同的工单内容",
                approved=True,
                db_path=test_db,
            )
        except ValueError:
            print("PASS: Conflicting request blocked")
        else:
            raise AssertionError(
                "Conflicting request was accepted"
            )

        assert count_tickets(test_db) == 1

        print("\n=== Test 5: Persistent Read ===")

        stored = get_ticket(
            first["ticket_id"],
            db_path=test_db,
        )

        assert stored is not None
        assert stored["ticket_id"] == first["ticket_id"]
        assert stored["description"] == "VPN 无法登录"

        print("PASS: Ticket read from disk")

        print("\nAll ticket store tests passed!")


if __name__ == "__main__":
    main()