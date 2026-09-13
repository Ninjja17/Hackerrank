from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


OUTPUT_COLUMNS = (
    "request_id",
    "amount_safe_to_pay",
    "affordability_status",
    "recommended_payment_method",
    "payment_plan",
    "earliest_date_for_full_payment",
    "spending_changes_needed",
    "decision_explanation",
)

ALLOWED_AFFORDABILITY_STATUSES = frozenset(
    {
        "affordable_now",
        "affordable_with_plan",
        "affordable_later",
        "not_affordable",
    }
)

ALLOWED_PAYMENT_METHODS = frozenset(
    {
        "full_payment",
        "partial_payment",
        "installments",
        "wait",
        "not_recommended",
    }
)


@dataclass(frozen=True, slots=True)
class FinancialProfile:
    user_id: str
    home_currency: str
    current_available_balance: Decimal
    minimum_balance_to_keep: Decimal
    financial_priorities: tuple[str, ...]
    expense_categories_to_protect: tuple[str, ...]
    expense_categories_user_is_willing_to_reduce: tuple[str, ...]
    expense_categories_user_is_willing_to_stop: tuple[str, ...]
    payment_methods_user_will_consider: tuple[str, ...]
    max_installment_months: int | None


@dataclass(frozen=True, slots=True)
class FinancialEvent:
    event_id: str
    user_id: str
    event_type: str
    description: str
    category: str
    direction: str
    amount: Decimal | None
    currency: str
    event_date: date
    settlement_date: date | None
    status: str
    linked_event_id: str | None
    flexibility: str
    minimum_allowed_amount: Decimal | None


@dataclass(frozen=True, slots=True)
class ExchangeRate:
    rate_date: date
    from_currency: str
    to_currency: str
    rate: Decimal


@dataclass(frozen=True, slots=True)
class Request:
    request_id: str
    user_id: str
    request_date: date
    request_type: str
    requested_amount: Decimal
    desired_completion_date: date
    allows_partial_payment: bool
    request_text: str
    requested_amount_text: str = ""


@dataclass(frozen=True, slots=True)
class PaymentOption:
    payment_option_id: str
    request_id: str
    payment_method: str
    payment_amount: Decimal
    number_of_payments: int
    first_payment_date: date
    payment_frequency_days: int | None
    financing_fee: Decimal
    total_payable_amount: Decimal
    payment_amount_text: str = ""


@dataclass(frozen=True, slots=True)
class Message:
    message_id: str
    user_id: str
    request_id: str | None
    related_event_id: str | None
    sent_at: datetime
    source_type: str
    message_text: str


@dataclass(frozen=True, slots=True)
class ImageReference:
    image_id: str
    user_id: str
    request_id: str | None
    related_event_id: str | None


@dataclass(frozen=True, slots=True)
class OutputRow:
    request_id: str
    amount_safe_to_pay: Decimal
    affordability_status: str
    recommended_payment_method: str
    payment_plan: str
    earliest_date_for_full_payment: date | None
    spending_changes_needed: str
    decision_explanation: str


@dataclass(frozen=True, slots=True)
class SampleRequest:
    request: Request
    output: OutputRow


@dataclass(frozen=True, slots=True)
class DatasetBundle:
    financial_profiles: tuple[FinancialProfile, ...]
    financial_events: tuple[FinancialEvent, ...]
    exchange_rates: tuple[ExchangeRate, ...]
    requests: tuple[Request, ...]
    sample_requests: tuple[SampleRequest, ...]
    payment_options: tuple[PaymentOption, ...]
    messages: tuple[Message, ...]
    images: tuple[ImageReference, ...]
    output_template_request_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CashFlowEntry:
    date: date
    amount: Decimal
    source_id: str
    source_type: str
    description: str
    display_amount: str | None = None


@dataclass(frozen=True, slots=True)
class SimulationResult:
    request_date: date
    end_date: date
    minimum_balance: Decimal
    balances: tuple[tuple[date, Decimal], ...]
    entries: tuple[CashFlowEntry, ...]
    unresolved_event_ids: tuple[str, ...]

    @property
    def lowest_balance(self) -> Decimal:
        return min(balance for _, balance in self.balances)

    @property
    def is_safe(self) -> bool:
        return not self.unresolved_event_ids and self.lowest_balance >= self.minimum_balance
