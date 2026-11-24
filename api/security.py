
"""Simple API key protection for local OpsDesk demos."""

import hmac
import os

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader


user_key_header = APIKeyHeader(
    name="X-OpsDesk-User-Key",
    scheme_name="OpsDeskUserKey",
    auto_error=False,
)

approver_key_header = APIKeyHeader(
    name="X-OpsDesk-Approver-Key",
    scheme_name="OpsDeskApproverKey",
    auto_error=False,
)


def _verify_key(
    provided: str | None,
    env_name: str,
) -> None:
    expected = os.getenv(env_name)

    # Never allow an unset credential to disable protection.
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="API authentication is not configured",
        )

    if not provided:
        raise HTTPException(
            status_code=401,
            detail="API key required",
        )

    if not hmac.compare_digest(provided, expected):
        raise HTTPException(
            status_code=403,
            detail="Invalid API key",
        )


def require_user_key(
    key: str | None = Security(user_key_header),
) -> None:
    _verify_key(key, "OPSDESK_USER_KEY")


def require_approver_key(
    key: str | None = Security(approver_key_header),
) -> None:
    _verify_key(key, "OPSDESK_APPROVER_KEY")