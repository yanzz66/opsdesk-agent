
"""OpsDesk Agent: local enterprise knowledge base."""

import hashlib
import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_ollama import OllamaEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter


# All paths are relative to the OpsDesk project.
PROJECT_ROOT = Path(__file__).resolve().parent
KNOWLEDGE_DIR = PROJECT_ROOT / "knowledge"
VECTOR_DB_DIR = PROJECT_ROOT / "vector_db"

COLLECTION_NAME = "opsdesk_knowledge_bge_m3"

load_dotenv(PROJECT_ROOT / ".env")


def get_embeddings():
    """Create the local BGE-M3 embedding client."""
    return OllamaEmbeddings(
        model=os.getenv("OLLAMA_EMBED_MODEL", "bge-m3"),
        base_url=os.getenv(
            "OLLAMA_BASE_URL",
            "http://127.0.0.1:11434",
        ),
    )


def get_vector_store():
    """Open the persistent Chroma collection."""
    return Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=get_embeddings(),
        persist_directory=str(VECTOR_DB_DIR),
    )


def load_documents():
    """Load local Markdown files with source metadata."""
    paths = sorted(KNOWLEDGE_DIR.glob("*.md"))

    if not paths:
        raise FileNotFoundError(
            f"No Markdown files found in {KNOWLEDGE_DIR}"
        )

    documents = []

    for path in paths:
        content = path.read_text(encoding="utf-8").strip()

        if not content:
            continue

        documents.append(
            Document(
                page_content=content,
                metadata={
                    "source": path.relative_to(
                        PROJECT_ROOT
                    ).as_posix(),
                    "title": path.stem,
                },
            )
        )

    if not documents:
        raise ValueError("All knowledge documents are empty")

    return documents


def build_index():
    """Rebuild only the OpsDesk demo collection."""
    documents = load_documents()

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=350,
        chunk_overlap=50,
        separators=[
            "\n\n",
            "\n",
            "。",
            "；",
            "！",
            "？",
            "，",
            " ",
            "",
        ],
    )

    chunks = splitter.split_documents(documents)

    if not chunks:
        raise ValueError("No chunks were generated")

    store = get_vector_store()

    # Rebuild the demo collection to avoid duplicates
    # and stale chunks when source files change.
    existing_ids = store.get(include=[])["ids"]

    if existing_ids:
        store.delete(ids=existing_ids)

    ids = []

    for index, chunk in enumerate(chunks):
        raw_id = (
            f"{chunk.metadata['source']}:{index}"
        )
        chunk_id = hashlib.sha256(
            raw_id.encode("utf-8")
        ).hexdigest()

        ids.append(chunk_id)

    store.add_documents(
        documents=chunks,
        ids=ids,
    )

    print(f"Documents loaded: {len(documents)}")
    print(f"Chunks indexed: {len(chunks)}")
    print(f"Database: {VECTOR_DB_DIR}")
    print(f"Collection: {COLLECTION_NAME}")


def search_knowledge(question: str, k: int = 3):
    """Retrieve the most relevant knowledge chunks."""
    if not VECTOR_DB_DIR.exists():
        raise RuntimeError(
            "Vector database not found. Run ingestion first."
        )

    store = get_vector_store()

    count = len(store.get(include=[])["ids"])

    if count == 0:
        raise RuntimeError(
            "Knowledge collection is empty."
        )

    return store.similarity_search(
        question,
        k=k,
    )