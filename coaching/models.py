"""Validated AI output contracts. Student-facing content is always reviewed."""
from typing import Literal
from pydantic import BaseModel, Field


class Claim(BaseModel):
    claim: str
    status: Literal['verified', 'preliminary', 'unanswered', 'contradicted']
    evidence_ids: list[str] = Field(default_factory=list)
    explanation: str


class ReferenceDraft(BaseModel):
    manuscript: str = Field(min_length=40)
    claims: list[Claim]
    change_summary: list[str]
    assignment_impacts: list[str]


class AssignmentDraft(BaseModel):
    title: str = Field(min_length=3)
    objective: str
    prompt: str = Field(min_length=15)
    deliverable: str
    criteria: list[str] = Field(min_length=1)
    estimated_minutes: int = Field(ge=5, le=240)
    section: str
    teacher_rationale: str


class AssignmentPlan(BaseModel):
    assignments: list[AssignmentDraft] = Field(min_length=1, max_length=12)


class FeedbackPoint(BaseModel):
    quote: str = Field(min_length=1)
    observation: str
    question: str


class FeedbackDraft(BaseModel):
    strengths: list[str]
    points: list[FeedbackPoint]
    next_task: str
    teacher_notes: str


class SourceCandidate(BaseModel):
    title: str
    url: str
    reason: str
    reading_question: str


class SourceSuggestions(BaseModel):
    sources: list[SourceCandidate] = Field(max_length=6)
