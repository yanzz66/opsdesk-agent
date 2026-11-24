
"""Build the local OpsDesk knowledge index."""

from knowledge_base import build_index


if __name__ == "__main__":
    print("=== OpsDesk Knowledge Ingestion ===")

    build_index()

    print("Knowledge ingestion completed!")