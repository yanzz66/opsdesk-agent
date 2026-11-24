
"""Pydantic request and response schemas for OpsDesk API."""

from pydantic import BaseModel, Field, field_validator
from uuid import UUID

class KnowledgeAskRequest(BaseModel):
    """Request body for a knowledge-base question."""

    question: str = Field(
        min_length=1,
        max_length=2000,
        description="员工提出的企业知识库问题",
    )

    k: int = Field(
        default=3,
        ge=1,
        le=5,
        strict=True,
        description="检索的知识片段数量，范围 1 到 5",
    )

    @field_validator("question", mode="before")
    @classmethod
    def strip_question(cls, value):
        if isinstance(value, str):
            return value.strip()
        return value


class KnowledgeSource(BaseModel):
    """A retrieved or cited knowledge source."""

    label: str
    source: str


class KnowledgeAskResponse(BaseModel):
    """Structured response returned by the RAG endpoint."""

    question: str
    answer: str
    sources: list[KnowledgeSource]
    cited_sources: list[KnowledgeSource]



# Ticket API schemas


class TicketCreateRequest(BaseModel):
    """Request for a new IT support ticket."""

    description: str = Field(
        min_length=1,
        max_length=1900,
        description="员工描述的 IT 问题",
    )

    @field_validator("description", mode="before")
    @classmethod
    def clean_description(cls, value):
        if isinstance(value, str):
            return value.strip()
        return value


class TicketDecisionRequest(BaseModel):
    """Human approval decision."""

    approved: bool = Field(
        strict=True,
        description="true=批准，false=拒绝",
    )


class TicketDraftResponse(BaseModel):
    request_id: str
    category: str
    description: str
    issue_type: str | None = None
    title: str | None = None


class TicketWorkflowResponse(BaseModel):
    thread_id: UUID
    status: str
    draft: TicketDraftResponse | None = None
    ticket_id: str | None = None
    answer: str | None = None


class TicketRecordResponse(BaseModel):
    ticket_id: str
    request_id: str
    category: str
    description: str
    status: str
    created_at: str