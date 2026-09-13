from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from models import DatasetBundle, Request


class Route(str, Enum):
    DETERMINISTIC_ONLY = "deterministic_only"
    LLM_EVIDENCE_EXTRACTION = "llm_evidence_extraction"
    LLM_EVIDENCE_EXTRACTION_WITH_REVIEW = "llm_evidence_extraction_with_review"


@dataclass(frozen=True, slots=True)
class RequestContext:
    request_id: str
    user_id: str
    request_type: str
    request_text: str
    relevant_messages: bool
    relevant_images: bool
    blank_amount: bool
    ocr_required: bool
    multilingual_evidence: bool
    income_update: bool
    cancellation_or_amendment: bool
    structured_conflict: bool
    refund_or_failed_payment: bool
    recurring_change: bool
    uncertain_wording: bool
    unstructured_explanation: bool


def build_context(bundle: DatasetBundle, request: Request) -> RequestContext:
    messages = tuple(
        message for message in bundle.messages
        if message.user_id == request.user_id
        and message.request_id in {None, request.request_id}
    )
    images = tuple(
        image for image in bundle.images
        if image.user_id == request.user_id
        and image.request_id in {None, request.request_id}
    )
    events = tuple(event for event in bundle.financial_events if event.user_id == request.user_id)
    text = " ".join(message.message_text for message in messages).lower()
    blank_amount = any(event.amount is None for event in events)
    multilingual = any(any(ord(char) > 127 for char in message.message_text) for message in messages)
    income = any(word in text for word in ("salary", "payroll", "gaji", "income", "wage"))
    amendment = any(word in text for word in ("cancel", "amend", "increase", "decrease", "changed"))
    refund_failed = any(word in text for word in ("refund", "failed", "retry", "chargeback"))
    recurring_change = any(word in text for word in ("subscription", "recurring", "monthly", "rent"))
    uncertain = any(word in text for word in ("maybe", "might", "pending", "awaiting", "uncertain", "not sure"))
    conflict = any(message.related_event_id for message in messages)
    return RequestContext(
        request.request_id, request.user_id, request.request_type, request.request_text,
        bool(messages), bool(images), blank_amount, bool(images and blank_amount),
        multilingual, income, amendment, conflict, refund_failed, recurring_change,
        uncertain, bool(messages or images or blank_amount),
    )


def route_context(context: RequestContext, *, provider_available: bool) -> Route:
    needs_llm = any((
        context.relevant_messages, context.relevant_images, context.blank_amount,
        context.ocr_required, context.multilingual_evidence, context.income_update,
        context.cancellation_or_amendment, context.structured_conflict,
        context.refund_or_failed_payment, context.recurring_change,
        context.uncertain_wording, context.unstructured_explanation,
    ))
    if not needs_llm:
        return Route.DETERMINISTIC_ONLY
    if not provider_available:
        return Route.LLM_EVIDENCE_EXTRACTION_WITH_REVIEW
    if context.uncertain_wording or context.structured_conflict or context.ocr_required:
        return Route.LLM_EVIDENCE_EXTRACTION_WITH_REVIEW
    return Route.LLM_EVIDENCE_EXTRACTION
