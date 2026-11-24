
"""Test recovery after a crash following a committed ticket write."""

import os
import sqlite3
import subprocess
import sys

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
CRASH_EXIT_CODE = 77

REQUEST = "请帮我创建工单：公司 VPN 无法登录"


def find_ticket(db_path, request_id):
    """Look up a ticket using its idempotency key."""

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row

        row = conn.execute(
            """
            SELECT *
            FROM tickets
            WHERE request_id = ?
            """,
            (request_id,),
        ).fetchone()

        return dict(row) if row else None


def worker(phase, thread_id):
    """Run one phase inside a separate Python process."""

    import workflow

    from langgraph.types import Command
    from ticket_store import create_ticket, count_tickets

    app = workflow.app

    config = {
        "configurable": {
            "thread_id": thread_id,
        }
    }

    db = Path(os.environ["OPSDESK_DB_PATH"])

    # Phase A: Start and interrupt before approval.
    if phase == "start":
        result = app.invoke(
            {"request": REQUEST},
            config=config,
            durability="sync",
        )

        assert "__interrupt__" in result
        assert result["ticket_status"] == "pending_approval"
        assert count_tickets(db) == 0

        snapshot = app.get_state(config)
        request_id = snapshot.values[
            "ticket_draft"
        ]["request_id"]

        assert snapshot.next

        print("PASS: workflow paused before approval")
        print("Request ID:", request_id)
        print("Database rows:", count_tickets(db))
        return

    snapshot = app.get_state(config)

    assert snapshot.next, "Saved workflow is not pending"

    request_id = snapshot.values[
        "ticket_draft"
    ]["request_id"]

    # Phase B: Approve and crash after DB commit.
    if phase == "crash":

        assert count_tickets(db) == 0

        def crash_after_commit(**kwargs):
            # Execute the real database operation.
            ticket = create_ticket(**kwargs)

            assert ticket["request_id"] == request_id
            assert count_tickets(db) == 1

            print(
                "PASS: ticket committed to SQLite",
                flush=True,
            )
            print(
                "Committed ticket ID:",
                ticket["ticket_id"],
                flush=True,
            )
            print(
                "SIMULATED CRASH AFTER COMMIT",
                flush=True,
            )

            # Deliberately terminate this child process.
            # The LangGraph node does not return its result.
            os._exit(CRASH_EXIT_CODE)

        with patch.object(
            workflow,
            "create_ticket",
            side_effect=crash_after_commit,
        ):
            app.invoke(
                Command(resume=True),
                config=config,
                durability="sync",
            )

        raise AssertionError(
            "Fault injection did not reach create_ticket"
        )

    # Phase C: Restart and resume unfinished execution.
    if phase == "recover":

        print("Restored request ID:", request_id)
        print("Pending nodes:", snapshot.next)

        assert snapshot.values.get("approved") is True

        assert "finish_ticket" in snapshot.next, (
            "Expected unfinished finish_ticket node"
        )

        existing = find_ticket(db, request_id)

        assert existing is not None
        assert existing["description"] == REQUEST
        assert count_tickets(db) == 1

        original_ticket_id = existing["ticket_id"]

        # Continue unfinished work, not a new request.
        # Do not approve a second time.
        result = app.invoke(
            None,
            config=config,
            durability="sync",
        )

        assert result["ticket_status"] == "open"
        assert result["ticket_id"] == original_ticket_id

        # The idempotent write must reuse the old ticket.
        assert count_tickets(db) == 1

        final_snapshot = app.get_state(config)
        assert not final_snapshot.next

        print("Recovered ticket ID:", result["ticket_id"])
        print("Final status:", result["ticket_status"])
        print("Database rows:", count_tickets(db))

        print("PASS: crash recovery succeeded")
        print("PASS: duplicate ticket prevented")
        return

    raise ValueError(f"Unknown worker phase: {phase}")


def run_phase(phase, thread_id, env, expected_code=0):
    """Execute a worker and verify its expected exit code."""

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.test_crash_recovery",
            "--worker",
            phase,
            thread_id,
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )

    print(result.stdout, end="")

    if result.returncode != expected_code:
        raise AssertionError(
            f"Phase {phase} failed.\n"
            f"Expected exit code: {expected_code}\n"
            f"Actual exit code: {result.returncode}\n"
            f"STDOUT:\n{result.stdout}\n"
            f"STDERR:\n{result.stderr}"
        )


def main():
    """Run the complete three-process fault injection test."""

    with TemporaryDirectory(
        prefix="opsdesk_crash_test_",
        dir=ROOT,
    ) as directory:

        temp_path = Path(directory)
        thread_id = f"crash-{uuid4().hex}"

        env = os.environ.copy()
        env.update({
            "OPSDESK_CHECKPOINT_BACKEND": "sqlite",
            "OPSDESK_CHECKPOINT_PATH": str(
                temp_path / "checkpoints.db"
            ),
            "OPSDESK_DB_PATH": str(
                temp_path / "tickets.db"
            ),
            "OPSDESK_TICKET_PLANNER": "rule",
            "PYTHONIOENCODING": "utf-8",
        })

        print("=== Phase A: Start Workflow ===")

        run_phase(
            "start",
            thread_id,
            env,
        )

        print("\n=== Phase B: Inject Crash ===")

        # Exit code 77 is expected here.
        # It proves the crash injection was triggered.
        run_phase(
            "crash",
            thread_id,
            env,
            expected_code=CRASH_EXIT_CODE,
        )

        print("\n=== Phase C: Recover Workflow ===")

        run_phase(
            "recover",
            thread_id,
            env,
        )

    print("\nAll crash recovery tests passed!")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--worker":
        worker(sys.argv[2], sys.argv[3])
    else:
        main()