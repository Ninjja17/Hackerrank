from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path

from cashflow import CurrencyConverter
from context_router import Route, build_context, route_context
from evidence import extract_message_facts
from gemini_provider import GeminiEvidenceProvider, GeminiFact, GeminiProviderError
from models import CashFlowEntry, DatasetBundle


@dataclass(frozen=True, slots=True)
class AgentRun:
    facts_by_request: dict[str, tuple[GeminiFact, ...]]
    provider_errors: dict[str, str]
    routes: dict[str, str] = field(default_factory=dict)

    @property
    def fact_count(self) -> int:
        return sum(len(facts) for facts in self.facts_by_request.values())

    def review_rows(self) -> tuple[dict[str, str], ...]:
        rows: list[dict[str, str]] = []
        for request_id, error in self.provider_errors.items():
            rows.append({"request_id": request_id, "reason": "provider_error", "details": error})
        for request_id, facts in self.facts_by_request.items():
            for fact in facts:
                if fact.confidence < Decimal("0.7"):
                    rows.append(
                        {
                            "request_id": request_id,
                            "reason": "low_confidence_fact",
                            "details": f"{fact.source_id}:{fact.fact_type}:{fact.confidence}",
                        }
                    )
        return tuple(rows)


def income_entries_by_request(
    bundle: DatasetBundle, run: AgentRun
) -> dict[str, tuple[CashFlowEntry, ...]]:
    converter = CurrencyConverter(bundle.exchange_rates)
    profiles = {profile.user_id: profile for profile in bundle.financial_profiles}
    requests = {request.request_id: request for request in bundle.requests}
    entries: dict[str, tuple[CashFlowEntry, ...]] = {}
    for request_id, facts in run.facts_by_request.items():
        request = requests.get(request_id)
        profile = profiles.get(request.user_id) if request else None
        if profile is None:
            continue
        converted_entries: list[CashFlowEntry] = []
        for fact in facts:
            if (
                fact.fact_type != "income_update"
                or fact.confidence < Decimal("0.7")
                or not fact.usable_for_cashflow
                or fact.amount is None
                or fact.currency is None
                or fact.effective_date is None
            ):
                continue
            try:
                effective_date = date.fromisoformat(fact.effective_date)
                amount = converter.convert(
                    fact.amount, fact.currency, profile.home_currency, effective_date
                )
            except (ValueError, TypeError):
                continue
            converted_entries.append(
                CashFlowEntry(
                    date=effective_date,
                    amount=amount,
                    source_id=fact.source_id,
                    source_type="llm_evidence",
                    description="validated high-confidence income update",
                )
            )
        if converted_entries:
            entries[request_id] = tuple(converted_entries)
    return entries


def deterministic_message_entries_by_request(
    bundle: DatasetBundle,
) -> dict[str, tuple[CashFlowEntry, ...]]:
    from evidence import reconcile_events_with_messages

    entries: dict[str, tuple[CashFlowEntry, ...]] = {}
    all_requests = tuple(bundle.requests) + tuple(
        sample.request for sample in bundle.sample_requests
    )
    events_by_user: dict[str, list] = {}
    for event in bundle.financial_events:
        events_by_user.setdefault(event.user_id, []).append(event)

    for request in all_requests:
        user_events = tuple(events_by_user.get(request.user_id, ()))
        _, extra_entries = reconcile_events_with_messages(
            user_events,
            bundle.messages,
            request.user_id,
            request.request_id,
            request.request_date,
        )
        if extra_entries:
            entries[request.request_id] = extra_entries
    return entries




def extract_optional_evidence(bundle: DatasetBundle, provider: GeminiEvidenceProvider | None) -> AgentRun:
    if provider is None:
        return AgentRun(
            {}, {},
            {
                request.request_id: route_context(
                    build_context(bundle, request), provider_available=False
                ).value
                for request in bundle.requests
            },
        )
    facts: dict[str, tuple[GeminiFact, ...]] = {}
    errors: dict[str, str] = {}
    routes: dict[str, str] = {}
    messages_by_request: dict[str, list] = {request.request_id: [] for request in bundle.requests}
    for message in bundle.messages:
        for request in bundle.requests:
            if message.user_id == request.user_id and message.request_id in {None, request.request_id}:
                messages_by_request[request.request_id].append(message)
    for request in bundle.requests:
        route = route_context(build_context(bundle, request), provider_available=True)
        routes[request.request_id] = route.value
        if route == Route.DETERMINISTIC_ONLY:
            continue
        try:
            request_facts = provider.extract(
                tuple(messages_by_request[request.request_id]), request.user_id, request.request_id
            )
            image_facts = provider.extract_images(
                bundle.images,
                Path("dataset") / "media" / "images",
                request.user_id,
                request.request_id,
            )
            valid_event_ids = {
                event.event_id
                for event in bundle.financial_events
                if event.user_id == request.user_id
            }
            invalid_links = [
                fact.source_id
                for fact in (*request_facts, *image_facts)
                if fact.related_event_id and fact.related_event_id not in valid_event_ids
            ]
            if invalid_links:
                errors[request.request_id] = "LLM suggested an invalid event link"
                request_facts = tuple(
                    fact for fact in request_facts if not fact.related_event_id
                )
                image_facts = tuple(
                    fact for fact in image_facts if not fact.related_event_id
                )
            facts[request.request_id] = (*request_facts, *image_facts)
        except Exception as error:
            errors[request.request_id] = str(error)
            if len(errors) >= 3:
                for remaining in bundle.requests:
                    if remaining.request_id not in facts and remaining.request_id not in errors:
                        routes[remaining.request_id] = Route.LLM_EVIDENCE_EXTRACTION_WITH_REVIEW.value
                        errors[remaining.request_id] = "LLM circuit breaker opened after repeated failures"
                break
    return AgentRun(facts, errors, routes)

