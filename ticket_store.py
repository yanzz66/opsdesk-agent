
"""OpsDesk Agent: SQLite ticket storage."""

import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_DB = PROJECT_ROOT / "data" / "tickets.db"


CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS tickets (
    ticket_id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL UNIQUE,
    category TEXT NOT NULL,
    description TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status = 'open'),
    created_at TEXT NOT NULL
)
"""


def _connect(db_path=None):
    """Open a SQLite connection."""
    path = Path(db_path) if db_path else DEFAULT_DB

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    conn = sqlite3.connect(
        path,
        timeout=10,
        autocommit=False,
    )

    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path=None):
    """Create database schema if necessary."""
    with closing(_connect(db_path)) as conn:
        with conn:
            conn.execute(CREATE_TABLE_SQL)


def _validate_text(name, value, max_length):
    """Validate business input."""
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string")

    value = value.strip()

    if not value:
        raise ValueError(f"{name} cannot be empty")

    if len(value) > max_length:
        raise ValueError(
            f"{name} exceeds {max_length} characters"
        )

    return value


def create_ticket(
    *,
    request_id: str,
    category: str,
    description: str,
    approved: bool,
    db_path=None,
):
    """Create one approved ticket idempotently."""

    # A database write requires explicit approval.
    if approved is not True:
        raise PermissionError(
            "Ticket creation requires human approval"
        )

    request_id = _validate_text(
        "request_id", request_id, 128
    )

    category = _validate_text(
        "category", category, 40
    )

    description = _validate_text(
        "description", description, 2000
    )

    init_db(db_path)

    ticket_id = str(uuid4())
    created_at = datetime.now(
        timezone.utc
    ).isoformat(timespec="seconds")

    with closing(_connect(db_path)) as conn:
        with conn:
            # Same request_id must not create duplicates.
            conn.execute(
                """
                INSERT INTO tickets (
                    ticket_id,
                    request_id,
                    category,
                    description,
                    status,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(request_id) DO NOTHING
                """,
                (
                    ticket_id,
                    request_id,
                    category,
                    description,
                    "open",
                    created_at,
                ),
            )

            row = conn.execute(
                """
                SELECT *
                FROM tickets
                WHERE request_id = ?
                """,
                (request_id,),
            ).fetchone()

            # A repeated request ID may only refer
            # to the same business operation.
            if (
                row["category"] != category
                or row["description"] != description
            ):
                raise ValueError(
                    "request_id already belongs to "
                    "a different ticket request"
                )

            return dict(row)


def get_ticket(ticket_id, db_path=None):
    """Retrieve one ticket by its ID."""
    init_db(db_path)

    with closing(_connect(db_path)) as conn:
        row = conn.execute(
            """
            SELECT *
            FROM tickets
            WHERE ticket_id = ?
            """,
            (ticket_id,),
        ).fetchone()

        return dict(row) if row else None


def count_tickets(db_path=None):
    """Return number of stored tickets."""
    init_db(db_path)

    with closing(_connect(db_path)) as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM tickets"
        ).fetchone()

        return row[0]