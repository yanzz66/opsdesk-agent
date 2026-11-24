
"""Test LangGraph SQLite checkpoints across Python processes."""

import os
import subprocess
import sys

from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]


def worker(phase: str, thread_id: str):
    """Execute one phase in a fresh Python process."""

    from langgraph.types import Command

    from ticket_store import count_tickets, get_ticket
    from workflow import app, finish_ticket

    config = {
        "configurable": {
            "thread_id": thread_id,
        }
    }

    ticket_db = Path(os.environ["OPSDESK_DB_PATH"])

    if phase == "start":
        result = app.invoke(
            {
                "request": (
                    "请帮我创建工单：公司 VPN 无法登录"
                )
            },
            config=config,
            durability="sync",
        )

        assert "__interrupt__" in result
        assert result["ticket_status"] == "pending_approval"
        assert count_tickets(ticket_db) == 0

        # Confirm the interrupt is checkpointed.
        snapshot = app.get_state(config)

        assert snapshot.next

        request_id = snapshot.values[
            "ticket_draft"
        ]["request_id"]

        print("START: interrupted")
        print("Saved request_id:", request_id)
        print("Database rows:", count_tickets(ticket_db))
        return

    # This phase runs in a different Python process.
    # Retrieve the checkpoint from SQLite.
    snapshot = app.get_state(config)

    assert snapshot.next, (
        "No pending checkpoint found after restart"
    )

    draft = snapshot.values["ticket_draft"]
    request_id = draft["request_id"]

    assert request_id
    assert count_tickets(ticket_db) == 0

    print("RESTORED request_id:", request_id)

    approved = phase == "approve"

    result = app.invoke(
        Command(resume=approved),
        config=config,
        durability="sync",
    )

    if approved:
        assert result["ticket_status"] == "open"
        assert count_tickets(ticket_db) == 1

        stored = get_ticket(
            result["ticket_id"],
            db_path=ticket_db,
        )

        assert stored is not None
        assert stored["request_id"] == request_id

        # Repeating the approved business operation
        # must return the same ticket.
        repeated = finish_ticket(result)

        assert repeated["ticket_id"] == stored["ticket_id"]
        assert count_tickets(ticket_db) == 1

        print("RESUME: approved")
        print("Ticket ID:", stored["ticket_id"])
        print("PASS: approved restart recovery")

    else:
        assert result["ticket_status"] == "rejected"
        assert count_tickets(ticket_db) == 0

        print("RESUME: rejected")
        print("PASS: rejected restart recovery")

    print("Database rows:", count_tickets(ticket_db))


def run_child(phase: str, thread_id: str, env: dict):
    """Launch a separate interpreter and check its result."""

    process = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.test_checkpoint_restart",
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

    print(process.stdout, end="")


    if process.returncode != 0:
        raise RuntimeError(
            f"\nWorker phase: {phase}\n"
            f"Exit code: {process.returncode}\n\n"
            f"=== CHILD STDOUT ===\n"
            f"{process.stdout}\n\n"
            f"=== CHILD STDERR ===\n"
            f"{process.stderr}\n"
        )


def main():
    """Verify approval and rejection after process restart."""

    with TemporaryDirectory(
        prefix="opsdesk_checkpoint_test_",
        dir=ROOT,
    ) as directory:

        temp_path = Path(directory)

        for decision in ("approve", "reject"):
            print(
                f"\n=== Restart Test: {decision} ==="
            )

            thread_id = f"restart-{uuid4().hex}"

            # Each test has isolated SQLite files.
            env = os.environ.copy()

            env.update({
                "OPSDESK_CHECKPOINT_BACKEND": "sqlite",
                "OPSDESK_CHECKPOINT_PATH": str(
                    temp_path / f"{decision}_checkpoints.db"
                ),
                "OPSDESK_DB_PATH": str(
                    temp_path / f"{decision}_tickets.db"
                ),
                "OPSDESK_TICKET_PLANNER": "rule",
            })

            # Process A creates an interruption.
            run_child("start", thread_id, env)

            # Process A has exited.
            # Process B restores the same thread.
            run_child(decision, thread_id, env)

    print("\nAll checkpoint restart tests passed!")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--worker":
        worker(sys.argv[2], sys.argv[3])
    else:
        main()