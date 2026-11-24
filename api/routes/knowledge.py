
"""OpsDesk Agent knowledge-base API endpoints."""

import logging

from fastapi import APIRouter, HTTPException

from api.schemas import (
    KnowledgeAskRequest,
    KnowledgeAskResponse,
)


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/knowledge",
    tags=["Knowledge QA"],
)


def _run_rag(question: str, k: int) -> dict:
    """Call the existing RAG business module."""

    # Lazy import prevents loading RAG dependencies
    # merely to start the FastAPI health endpoint.
    from rag_qa import answer_with_rag

    return answer_with_rag(
        question=question,
        k=k,
    )


@router.post(
    "/ask",
    response_model=KnowledgeAskResponse,
    summary="Ask the enterprise knowledge base",
    responses={
        503: {
            "description": "Knowledge QA service unavailable",
        }
    },
)
def ask_knowledge(
    request: KnowledgeAskRequest,
) -> KnowledgeAskResponse:
    """Retrieve relevant documents and generate an answer."""

    try:
        result = _run_rag(
            question=request.question,
            k=request.k,
        )

    except Exception as exc:
        # Never expose raw internal errors to API clients.
        logger.exception("RAG knowledge request failed")

        raise HTTPException(
            status_code=503,
            detail=(
                "知识问答服务暂时不可用，"
                "请检查本地模型服务与知识库。"
            ),
        ) from exc

    return KnowledgeAskResponse.model_validate(result)