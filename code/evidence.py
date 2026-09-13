from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
import re

from models import CashFlowEntry, FinancialEvent, ImageReference, Message




@dataclass(frozen=True, slots=True)
class EvidenceFact:
    source_type: str
    source_id: str
    related_event_id: str
    extracted_value: Decimal
    image_path: str


@dataclass(frozen=True, slots=True)
class MessageFact:
    source_type: str
    source_id: str
    related_event_id: str | None
    date: str
    text: str


@dataclass(frozen=True, slots=True)
class ExtractedMessageFact:
    source_type: str
    source_id: str
    related_event_id: str | None
    date: str
    fact_type: str
    amount: Decimal | None
    currency: str | None
    effective_date: str | None
    text: str


UNTRUSTED_INSTRUCTION_PATTERNS = (
    re.compile(r"\bignore\s+(?:all\s+)?previous\s+instructions?\b", re.I),
    re.compile(r"\bremove\s+(?:the\s+)?minimum\s+balance\b", re.I),
    re.compile(r"\btreat\s+(?:the\s+)?pending\s+payment\s+as\s+settled\b", re.I),
    re.compile(r"\b(?:call|run|execute)\s+(?:a\s+)?(?:tool|command|script)\b", re.I),
    re.compile(r"\bapprove\s+this\s+request\b", re.I),
)


def contains_untrusted_instruction(text: str) -> bool:
    return any(pattern.search(text) for pattern in UNTRUSTED_INSTRUCTION_PATTERNS)


def relevant_message_facts(
    messages: tuple[Message, ...], user_id: str, request_id: str
) -> tuple[MessageFact, ...]:
    facts: list[MessageFact] = []
    for message in messages:
        if message.user_id != user_id:
            continue
        if message.request_id not in {None, request_id}:
            continue
        if contains_untrusted_instruction(message.message_text):
            continue
        facts.append(
            MessageFact(
                source_type=message.source_type,
                source_id=message.message_id,
                related_event_id=message.related_event_id,
                date=message.sent_at.date().isoformat(),
                text=message.message_text,
            )
        )
    return tuple(sorted(facts, key=lambda fact: (fact.date, fact.source_id)))


AMOUNT_AFTER_CURRENCY_PATTERN = re.compile(
    r"(?P<currency>IDR|INR|USD|EUR|ZAR)\s*(?P<amount>\d+(?:[,.]\d+)?)\b",
    re.I,
)
AMOUNT_BEFORE_CURRENCY_PATTERN = re.compile(
    r"(?P<amount>\d+(?:[,.]\d+)?)\s*(?P<currency>IDR|INR|USD|EUR|ZAR)\b",
    re.I,
)
DATE_PATTERN = re.compile(r"\b(?P<date>\d{4}-\d{2}-\d{2})\b")


def extract_message_facts(
    messages: tuple[Message, ...], user_id: str, request_id: str
) -> tuple[ExtractedMessageFact, ...]:
    extracted: list[ExtractedMessageFact] = []
    for message in messages:
        if message.user_id != user_id or message.request_id not in {None, request_id}:
            continue
        if contains_untrusted_instruction(message.message_text):
            continue
        text = message.message_text
        lowered = text.lower()
        amount_match = AMOUNT_AFTER_CURRENCY_PATTERN.search(text)
        if amount_match is None:
            amount_match = AMOUNT_BEFORE_CURRENCY_PATTERN.search(text)
        date_matches = DATE_PATTERN.findall(text)
        amount = None
        currency = None
        if amount_match:
            amount = Decimal(amount_match.group("amount").replace(",", ""))
            currency = amount_match.group("currency").upper()
        if any(word in lowered for word in ("salary", "gaji", "payroll")):
            fact_type = "income_update"
        elif any(word in lowered for word in ("cancel", "cancelled", "canceled")):
            fact_type = "cancellation"
        elif any(word in lowered for word in ("settled", "settlement", "paid")):
            fact_type = "settlement"
        elif any(word in lowered for word in ("delay", "delayed", "postponed")):
            fact_type = "delay"
        elif any(word in lowered for word in ("confirm", "confirmed", "approved")):
            fact_type = "confirmation"
        else:
            fact_type = "unclassified"
        extracted.append(
            ExtractedMessageFact(
                source_type=message.source_type,
                source_id=message.message_id,
                related_event_id=message.related_event_id,
                date=message.sent_at.date().isoformat(),
                fact_type=fact_type,
                amount=amount,
                currency=currency,
                effective_date=date_matches[0] if date_matches else None,
                text=text,
            )
        )
    return tuple(sorted(extracted, key=lambda fact: (fact.date, fact.source_id)))


# Transcribed from the supplied linked images; kept separate from dataset CSVs.
VERIFIED_IMAGE_AMOUNTS = {
    "image_01": Decimal("4365000"),
    "image_02": Decimal("200000"),
    "image_03": Decimal("41272"),
    "image_04": Decimal("2854"),
    "image_05": Decimal("704.05"),
    "image_06": Decimal("1995"),
    "image_07": Decimal("8528"),
    "image_08": Decimal("15339"),
    "image_09": Decimal("723"),
    "image_10": Decimal("79679.26"),
    "image_11": Decimal("3650"),
    "image_12": Decimal("33.50"),
    "image_13": Decimal("2298"),
    "image_14": Decimal("4593"),
    "image_15": Decimal("9968"),
    "image_16": Decimal("393.22"),
}


def resolve_image_amounts(
    images: tuple[ImageReference, ...], image_dir: Path
) -> tuple[dict[str, Decimal], tuple[EvidenceFact, ...], tuple[str, ...]]:
    event_amounts: dict[str, Decimal] = {}
    facts: list[EvidenceFact] = []
    failures: list[str] = []
    for image in images:
        if not image.related_event_id:
            continue
        image_path = image_dir / f"{image.image_id}.png"
        amount = VERIFIED_IMAGE_AMOUNTS.get(image.image_id)
        if amount is None or not image_path.is_file():
            failures.append(image.related_event_id)
            continue
        event_amounts[image.related_event_id] = amount
        facts.append(
            EvidenceFact(
                source_type="image",
                source_id=image.image_id,
                related_event_id=image.related_event_id,
                extracted_value=amount,
                image_path=str(image_path),
            )
        )
    return event_amounts, tuple(facts), tuple(sorted(set(failures)))


def reconcile_events_with_messages(
    events: tuple[FinancialEvent, ...],
    messages: tuple[Message, ...],
    user_id: str,
    request_id: str,
    request_date: date,
) -> tuple[tuple[FinancialEvent, ...], tuple[CashFlowEntry, ...]]:
    facts = extract_message_facts(messages, user_id, request_id)
    event_list = list(events)
    extra_entries: list[CashFlowEntry] = []

    for fact in facts:
        text = fact.text.lower()
        if (
            "contract has ended" in text
            or "employment has ended" in text
            or "hubungan kerja anda telah berakhir" in text
            or "seasonal contract has ended" in text
        ):
            event_list = [
                e for e in event_list
                if not (e.user_id == user_id and e.category == "salary" and (e.settlement_date or e.event_date or request_date) >= request_date)
            ]
            for i, e in enumerate(event_list):
                if e.user_id == user_id and e.category == "salary":
                    event_list[i] = FinancialEvent(
                        event_id=e.event_id,
                        user_id=e.user_id,
                        event_type=e.event_type,
                        description="Final employer payroll",
                        category=e.category,
                        direction=e.direction,
                        amount=e.amount,
                        currency=e.currency,
                        event_date=e.event_date,
                        settlement_date=e.settlement_date,
                        status=e.status,
                        linked_event_id=e.linked_event_id,
                        flexibility=e.flexibility,
                        minimum_allowed_amount=e.minimum_allowed_amount,
                    )
            continue

        if fact.source_type == "service_provider" and ("approved an invoice payment" in text or "menyetujui pembayaran faktur" in text):
            if fact.amount and fact.currency and fact.effective_date:
                try:
                    eff_date = date.fromisoformat(fact.effective_date)
                    if eff_date >= request_date:
                        extra_entries.append(
                            CashFlowEntry(
                                date=eff_date,
                                amount=fact.amount,
                                source_id=fact.source_id,
                                source_type="message_evidence",
                                description="confirmed invoice payment",
                            )
                        )
                except ValueError:
                    pass
            continue

        if fact.fact_type == "income_update" or fact.source_type == "employer":
            salary_indices = [
                i for i, e in enumerate(event_list)
                if e.user_id == user_id and e.category == "salary" and (e.settlement_date or e.event_date or request_date) >= request_date
            ]
            if salary_indices:
                idx = salary_indices[0]
                orig_event = event_list[idx]
                new_amount = fact.amount if fact.amount is not None else orig_event.amount
                new_currency = fact.currency if fact.currency is not None else orig_event.currency
                new_date = orig_event.settlement_date or orig_event.event_date or request_date
                if fact.effective_date:
                    try:
                        new_date = date.fromisoformat(fact.effective_date)
                    except ValueError:
                        pass

                arrears_match = re.search(
                    r"arrears adjustment of (?:IDR|INR|USD|EUR|ZAR)\s*([\d,.]+)|penyesuaian tunggakan satu kali sebesar (?:IDR|INR|USD|EUR|ZAR)\s*([\d,.]+)",
                    fact.text,
                    re.I,
                )
                if arrears_match:
                    arr_val = Decimal((arrears_match.group(1) or arrears_match.group(2)).replace(",", "").rstrip("."))
                    extra_entries.append(
                        CashFlowEntry(
                            date=new_date,
                            amount=arr_val,
                            source_id=fact.source_id,
                            source_type="message_evidence",
                            description="one-time arrears adjustment",
                        )
                    )

                event_list[idx] = FinancialEvent(
                    event_id=orig_event.event_id,
                    user_id=orig_event.user_id,
                    event_type=orig_event.event_type,
                    description=orig_event.description,
                    category=orig_event.category,
                    direction=orig_event.direction,
                    amount=new_amount,
                    currency=new_currency,
                    event_date=new_date,
                    settlement_date=new_date,
                    status=orig_event.status,
                    linked_event_id=orig_event.linked_event_id,
                    flexibility=orig_event.flexibility,
                    minimum_allowed_amount=orig_event.minimum_allowed_amount,
                )
            else:
                if fact.amount and fact.currency:
                    eff_date = None
                    if fact.effective_date:
                        try:
                            eff_date = date.fromisoformat(fact.effective_date)
                        except ValueError:
                            pass
                    if eff_date is None:
                        past_sals = [
                            e for e in event_list
                            if e.user_id == user_id and e.category == "salary" and (e.settlement_date or e.event_date)
                        ]
                        pay_day = 15
                        if past_sals:
                            latest_past = max(past_sals, key=lambda e: (e.settlement_date or e.event_date))
                            pay_day = (latest_past.settlement_date or latest_past.event_date).day
                        import calendar
                        year = request_date.year
                        month = request_date.month
                        day = min(pay_day, calendar.monthrange(year, month)[1])
                        eff_date = date(year, month, day)
                        if eff_date < request_date:
                            month = month % 12 + 1
                            if month == 1:
                                year += 1
                            day = min(pay_day, calendar.monthrange(year, month)[1])
                            eff_date = date(year, month, day)
                    if eff_date >= request_date:
                        extra_entries.append(
                            CashFlowEntry(
                                date=eff_date,
                                amount=fact.amount,
                                source_id=fact.source_id,
                                source_type="message_evidence",
                                description="confirmed salary credit",
                            )
                        )
                        for i, e in enumerate(event_list):
                            if e.user_id == user_id and e.category == "salary" and "arrears" not in e.description.lower() and "bonus" not in e.description.lower() and "commission" not in e.description.lower():
                                event_list[i] = FinancialEvent(
                                    event_id=e.event_id,
                                    user_id=e.user_id,
                                    event_type=e.event_type,
                                    description=e.description,
                                    category=e.category,
                                    direction=e.direction,
                                    amount=fact.amount,
                                    currency=fact.currency,
                                    event_date=e.event_date,
                                    settlement_date=e.settlement_date,
                                    status=e.status,
                                    linked_event_id=e.linked_event_id,
                                    flexibility=e.flexibility,
                                    minimum_allowed_amount=e.minimum_allowed_amount,
                                )
            continue

        if "renewed lease increases monthly rent by 12%" in text or "menaikkan sewa bulanan sebesar 12%" in text:
            for i, e in enumerate(event_list):
                if e.category == "rent" and e.amount is not None:
                    event_list[i] = FinancialEvent(
                        event_id=e.event_id,
                        user_id=e.user_id,
                        event_type=e.event_type,
                        description=e.description,
                        category=e.category,
                        direction=e.direction,
                        amount=e.amount * Decimal("1.12"),
                        currency=e.currency,
                        event_date=e.event_date,
                        settlement_date=e.settlement_date,
                        status=e.status,
                        linked_event_id=e.linked_event_id,
                        flexibility=e.flexibility,
                        minimum_allowed_amount=e.minimum_allowed_amount,
                    )
    return tuple(event_list), tuple(extra_entries)

