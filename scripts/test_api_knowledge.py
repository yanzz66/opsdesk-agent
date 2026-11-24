
"""Test the OpsDesk RAG API without loading local models."""

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.app import app


client = TestClient(app)

ENDPOINT = "/api/knowledge/ask"


def fake_rag_answer(question):
    return {
        "question": question,
        "answer": "请检查 VPN 连接配置。[1]",
        "sources": [
            {
                "label": "[1]",
                "source": "knowledge/vpn_troubleshooting.md",
            }
        ],
        "cited_sources": [
            {
                "label": "[1]",
                "source": "knowledge/vpn_troubleshooting.md",
            }
        ],
    }


class TestKnowledgeAPI(unittest.TestCase):

    def test_valid_question(self):
        question = "公司 VPN 无法连接怎么办？"

        with patch(
            "api.routes.knowledge._run_rag",
            return_value=fake_rag_answer(question),
        ) as mock_rag:

            response = client.post(
                ENDPOINT,
                json={"question": question, "k": 3},
            )

            self.assertEqual(response.status_code, 200)

            data = response.json()

            self.assertEqual(data["question"], question)
            self.assertTrue(data["answer"])
            self.assertEqual(len(data["sources"]), 1)
            self.assertEqual(len(data["cited_sources"]), 1)

            mock_rag.assert_called_once_with(
                question=question,
                k=3,
            )

    def test_default_k(self):
        question = "VPN 登录失败怎么办？"

        with patch(
            "api.routes.knowledge._run_rag",
            return_value=fake_rag_answer(question),
        ) as mock_rag:

            response = client.post(
                ENDPOINT,
                json={"question": question},
            )

            self.assertEqual(response.status_code, 200)

            mock_rag.assert_called_once_with(
                question=question,
                k=3,
            )

    def test_unknown_knowledge(self):
        question = "公司员工每年有多少天带薪年假？"

        result = {
            "question": question,
            "answer": "当前演示知识库没有足够资料回答这个问题。",
            "sources": [],
            "cited_sources": [],
        }

        with patch(
            "api.routes.knowledge._run_rag",
            return_value=result,
        ):
            response = client.post(
                ENDPOINT,
                json={"question": question},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["cited_sources"],
            [],
        )

    def test_whitespace_question(self):
        response = client.post(
            ENDPOINT,
            json={"question": "   "},
        )

        self.assertEqual(response.status_code, 422)

    def test_invalid_k(self):
        for k in (0, 6):
            with self.subTest(k=k):
                response = client.post(
                    ENDPOINT,
                    json={
                        "question": "VPN 故障怎么办？",
                        "k": k,
                    },
                )

                self.assertEqual(response.status_code, 422)

    def test_rag_failure(self):
        with patch(
            "api.routes.knowledge._run_rag",
            side_effect=ConnectionError(
                "Simulated model connection failure"
            ),
        ):
            response = client.post(
                ENDPOINT,
                json={"question": "VPN 故障怎么办？"},
            )

        self.assertEqual(response.status_code, 503)
        self.assertNotIn(
            "Simulated model connection failure",
            response.text,
        )

    def test_existing_health_still_works(self):
        response = client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["status"],
            "ok",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)