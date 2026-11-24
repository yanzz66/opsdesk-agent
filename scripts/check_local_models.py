
"""OpsDesk Agent - local model connectivity test."""

import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_ollama import ChatOllama, OllamaEmbeddings


# Load configuration from the project root.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

BASE_URL = os.getenv(
    "OLLAMA_BASE_URL",
    "http://127.0.0.1:11434",
)

CHAT_MODEL = os.getenv(
    "OLLAMA_CHAT_MODEL",
    "qwen3:8b",
)

EMBED_MODEL = os.getenv(
    "OLLAMA_EMBED_MODEL",
    "bge-m3",
)


def test_chat_model():
    print("\n=== Testing Qwen3 ===")

    llm = ChatOllama(
        model=CHAT_MODEL,
        base_url=BASE_URL,
        temperature=0,
    )

    response = llm.invoke(
        "请用中文简单解释什么是企业 VPN。"
    )

    print("Model:", CHAT_MODEL)
    print("Response:", response.content)

    assert response.content, "Empty LLM response"


def test_embedding_model():
    print("\n=== Testing BGE-M3 ===")

    embeddings = OllamaEmbeddings(
        model=EMBED_MODEL,
        base_url=BASE_URL,
    )

    vector = embeddings.embed_query(
        "公司 VPN 无法连接，应该如何排查？"
    )

    print("Model:", EMBED_MODEL)
    print("Embedding dimensions:", len(vector))
    print("First 5 values:", vector[:5])

    assert len(vector) > 0, "Empty embedding vector"


if __name__ == "__main__":
    test_chat_model()
    test_embedding_model()

    print("\nAll local model tests passed!")