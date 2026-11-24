
"""Test local tool-call planning and LangGraph integration."""

import os
import unittest

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from langgraph.types import Command

from ticket_tool_planner import (
    TicketPlanningError,
    plan_ticket_with_tool_call,
)
from ticket_store import count_tickets, get_ticket
from workflow import app, finish_ticket


ROOT = Path(__file__).resolve().parents[1]


def valid_call():
    return {
        "name": "TicketProposal",
        "args": {
            "issue_type": "vpn",
            "title": "VPN 无法登录",
        },
        "id": "test-call-1",
    }


class FakeModel:
    """Simulate a ChatOllama model returning tool calls."""

    def __init__(self, calls):
        self.calls = calls

    def bind_tools(self, tools):
        assert tools[0].__name__ == "TicketProposal"
        return self

    def invoke(self, messages):
        return SimpleNamespace(tool_calls=self.calls)


def new_config():
    return {
        "configurable": {
            "thread_id": f"tool-test-{uuid4().hex}"
        }
    }


class TestTicketToolCalling(unittest.TestCase):

    def test_valid_tool_call(self):
        result = plan_ticket_with_tool_call(
            "请创建工单：VPN 无法登录",
            llm=FakeModel([valid_call()]),
        )
        self.assertEqual(result["issue_type"], "vpn")
        self.assertEqual(result["title"], "VPN 无法登录")

    def test_missing_tool_call(self):
        with self.assertRaises(TicketPlanningError):
            plan_ticket_with_tool_call(
                "创建工单",
                llm=FakeModel([]),
            )

    def test_unknown_tool(self):
        call = valid_call()
        call["name"] = "DeleteDatabase"

        with self.assertRaises(TicketPlanningError):
            plan_ticket_with_tool_call(
                "创建工单",
                llm=FakeModel([call]),
            )

    def test_invalid_issue_type(self):
        call = valid_call()
        call["args"]["issue_type"] = "delete_database"

        with self.assertRaises(TicketPlanningError):
            plan_ticket_with_tool_call(
                "创建工单",
                llm=FakeModel([call]),
            )

    def test_extra_approval_field(self):
        call = valid_call()
        call["args"]["approved"] = True

        with self.assertRaises(TicketPlanningError):
            plan_ticket_with_tool_call(
                "创建工单",
                llm=FakeModel([call]),
            )

    def test_multiple_calls(self):
        with self.assertRaises(TicketPlanningError):
            plan_ticket_with_tool_call(
                "创建工单",
                llm=FakeModel([valid_call(), valid_call()]),
            )

    def test_approved_workflow(self):
        with TemporaryDirectory(dir=ROOT) as directory:
            db = Path(directory) / "tickets.db"

            with patch.dict(os.environ, {
                "OPSDESK_TICKET_PLANNER": "llm",
                "OPSDESK_DB_PATH": str(db),
            }), patch(
                "ticket_tool_planner.get_chat_model",
                return_value=FakeModel([valid_call()]),
            ):
                config = new_config()
                request = "请帮我创建工单：公司 VPN 无法登录"

                pending = app.invoke(
                    {"request": request},
                    config=config,
                )

                self.assertIn("__interrupt__", pending)
                self.assertEqual(
                    pending["ticket_draft"]["issue_type"],
                    "vpn",
                )
                self.assertEqual(
                    pending["ticket_draft"]["description"],
                    request,
                )
                self.assertEqual(count_tickets(db), 0)

                result = app.invoke(
                    Command(resume=True),
                    config=config,
                )

                self.assertEqual(result["ticket_status"], "open")
                self.assertEqual(count_tickets(db), 1)

                saved = get_ticket(result["ticket_id"], db)
                self.assertEqual(saved["description"], request)

                # Repeated write uses the same request_id.
                repeated = finish_ticket(result)
                self.assertEqual(
                    repeated["ticket_id"],
                    result["ticket_id"],
                )
                self.assertEqual(count_tickets(db), 1)

    def test_rejected_workflow(self):
        with TemporaryDirectory(dir=ROOT) as directory:
            db = Path(directory) / "tickets.db"

            with patch.dict(os.environ, {
                "OPSDESK_TICKET_PLANNER": "llm",
                "OPSDESK_DB_PATH": str(db),
            }), patch(
                "ticket_tool_planner.get_chat_model",
                return_value=FakeModel([valid_call()]),
            ):
                config = new_config()

                pending = app.invoke(
                    {"request": "请创建工单：VPN 无法登录"},
                    config=config,
                )
                self.assertIn("__interrupt__", pending)

                result = app.invoke(
                    Command(resume=False),
                    config=config,
                )

                self.assertEqual(
                    result["ticket_status"],
                    "rejected",
                )
                self.assertEqual(count_tickets(db), 0)

    def test_invalid_plan_does_not_write(self):
        with TemporaryDirectory(dir=ROOT) as directory:
            db = Path(directory) / "tickets.db"

            with patch.dict(os.environ, {
                "OPSDESK_TICKET_PLANNER": "llm",
                "OPSDESK_DB_PATH": str(db),
            }), patch(
                "ticket_tool_planner.get_chat_model",
                return_value=FakeModel([]),
            ):
                with self.assertRaises(TicketPlanningError):
                    app.invoke(
                        {"request": "请创建工单：VPN 无法登录"},
                        config=new_config(),
                    )

                self.assertEqual(count_tickets(db), 0)


if __name__ == "__main__":
    unittest.main()