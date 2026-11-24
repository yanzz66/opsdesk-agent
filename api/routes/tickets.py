
"""OpsDesk ticket creation, approval, and query API."""

import logging
import os

from threading import Lock
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from langgraph.types import Command

from api.schemas import (
    TicketCreateRequest,
    TicketDecisionRequest,
    TicketWorkflowResponse,
    TicketRecordResponse,
)

from api.security import (
    require_user_key,
    require_approver_key,
)


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/tickets",
    tags=["Tickets"],
)

# Prevent simultaneous decisions in this demo process.
decision_lock = Lock()


def _graph_app():
    """Load the existing LangGraph workflow."""

    backend = os.getenv(
        "OPSDESK_CHECKPOINT_BACKEND",
        "memory",
    ).strip().lower()

    if backend != "sqlite":
        raise HTTPException(
            status_code=503,
            detail=(
                "Ticket API requires SQLite Checkpointer. "
                "Set OPSDESK_CHECKPOINT_BACKEND=sqlite."
            ),
        )

    from workflow import app as graph_app

    return graph_app


def _config(thread_id: UUID):
    return {
        "configurable": {
            "thread_id": str(thread_id),
        }
    }


def _workflow_response(
    thread_id: UUID,
    values: dict,
) -> TicketWorkflowResponse:
    """Convert LangGraph State into an API response."""

    return TicketWorkflowResponse(
        thread_id=thread_id,
        status=values.get("ticket_status", "unknown"),
        draft=values.get("ticket_draft"),
        ticket_id=values.get("ticket_id"),
        answer=values.get("answer"),
    )


def _get_snapshot(graph, thread_id: UUID):
    """Read a ticket workflow from the Checkpointer."""

    try:
        snapshot = graph.get_state(_config(thread_id))

    except Exception as exc:
        logger.exception("Failed to read workflow checkpoint")

        raise HTTPException(
            status_code=503,
            detail="工作流状态暂时无法读取",
        ) from exc

    values = snapshot.values or {}

    if values.get("intent") != "ticket":
        raise HTTPException(
            status_code=404,
            detail="未找到该工单工作流",
        )

    return snapshot


@router.post(
    "",
    status_code=201,
    response_model=TicketWorkflowResponse,
    summary="Submit a ticket for approval",
)
def submit_ticket(
    payload: TicketCreateRequest,
    _: None = Depends(require_user_key),
):
    """Submit an IT ticket without creating a DB record yet."""

    graph = _graph_app()
    thread_id = uuid4()

    # Explicitly express the ticket-creation intent.
    # LangGraph's existing classifier remains unchanged.
    graph_request = (
        f"请帮我创建工单：{payload.description}"
    )

    try:
        result = graph.invoke(
            {"request": graph_request},
            config=_config(thread_id),
            durability="sync",
        )

    except Exception as exc:
        logger.exception("Ticket preparation failed")

        raise HTTPException(
            status_code=503,
            detail="工单准备失败，请检查本地模型与工作流",
        ) from exc

    # There must be a real approval interruption.
    if (
        result.get("intent") != "ticket"
        or "__interrupt__" not in result
    ):
        logger.error("Ticket workflow did not interrupt")

        raise HTTPException(
            status_code=500,
            detail="工作流没有进入预期的审批状态",
        )

    return _workflow_response(thread_id, result)


@router.get(
    "/workflows/{thread_id}",
    response_model=TicketWorkflowResponse,
    summary="Get ticket workflow status",
)
def get_ticket_workflow(
    thread_id: UUID,
    _: None = Depends(require_approver_key),
):
    """Inspect a saved ticket workflow."""

    graph = _graph_app()
    snapshot = _get_snapshot(graph, thread_id)

    return _workflow_response(
        thread_id,
        snapshot.values,
    )


@router.post(
    "/workflows/{thread_id}/decision",
    response_model=TicketWorkflowResponse,
    summary="Approve or reject a ticket",
)
def decide_ticket(
    thread_id: UUID,
    payload: TicketDecisionRequest,
    _: None = Depends(require_approver_key),
):
    """Resume a pending human approval."""

    graph = _graph_app()

    with decision_lock:
        snapshot = _get_snapshot(graph, thread_id)
        values = snapshot.values

        # Never resume a finished or unexpected workflow.
        if (
                values.get("ticket_status") != "pending_approval"
                or "approval" not in snapshot.next
        ):
            raise HTTPException(
                status_code=409,
                detail="工单已处理或不处于待审批状态",
            )

        try:
            result = graph.invoke(
                Command(resume=payload.approved),
                config=_config(thread_id),
                durability="sync",
            )

        except Exception as exc:
            logger.exception("Ticket decision failed")

            raise HTTPException(
                status_code=503,
                detail="审批执行失败，请查询工作流状态",
            ) from exc

        expected = "open" if payload.approved else "rejected"

        if result.get("ticket_status") != expected:
            logger.error("Unexpected ticket workflow result")

            raise HTTPException(
                status_code=500,
                detail="审批结果异常，请查询工作流状态",
            )

    return _workflow_response(thread_id, result)


@router.get(
    "/{ticket_id}",
    response_model=TicketRecordResponse,
    summary="Get a stored ticket",
)
def read_ticket(
    ticket_id: UUID,
    _: None = Depends(require_approver_key),
):
    """Read an approved ticket from SQLite."""

    from ticket_store import get_ticket

    try:
        ticket = get_ticket(
            str(ticket_id),
            db_path=os.getenv("OPSDESK_DB_PATH") or None,
        )

    except Exception as exc:
        logger.exception("Ticket database query failed")

        raise HTTPException(
            status_code=503,
            detail="工单数据库暂时无法访问",
        ) from exc

    if ticket is None:
        raise HTTPException(
            status_code=404,
            detail="未找到该工单",
        )

    return TicketRecordResponse.model_validate(ticket)