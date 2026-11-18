"""Esquema e validação estrutural dos arquivos sintéticos (Fase 2)."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

Row = Mapping[str, str]
Dataset = Mapping[str, Sequence[Row]]

CUSTOMER_FIELDS = ("customer_id", "customer_segment", "created_at", "updated_at")
CONTRACT_FIELDS = (
    "contract_id",
    "customer_id",
    "product_type",
    "principal_amount",
    "annual_interest_rate",
    "start_date",
    "end_date",
    "status",
    "updated_at",
)
INSTALLMENT_FIELDS = (
    "contract_id",
    "installment_number",
    "due_date",
    "paid_at",
    "amount_due",
    "amount_paid",
    "status",
    "updated_at",
)

FIELDS = {
    "customers": CUSTOMER_FIELDS,
    "contracts": CONTRACT_FIELDS,
    "installments": INSTALLMENT_FIELDS,
}

DOMAINS = {
    "customer_segment": ("mass", "affluent", "business"),
    "product_type": ("personal_loan", "auto_loan"),
    "contract_status": ("active", "closed", "cancelled"),
    "installment_status": ("open", "paid", "overdue"),
}

NULLABLE = {"installments": ("paid_at",)}


def _parse_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _parse_timestamp(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _parse_decimal(value: str) -> Decimal | None:
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def _check_unique(
    errors: list[str],
    entity: str,
    rows: Sequence[Row],
    key: Callable[[Row], object],
    label: str,
) -> None:
    seen: set[object] = set()
    for index, row in enumerate(rows, start=2):
        value = key(row)
        if value in seen:
            errors.append(f"{entity}:{index}: {label} duplicado")
        else:
            seen.add(value)


def validate_dataset(dataset: Dataset) -> list[str]:
    errors: list[str] = []

    for entity, fields in FIELDS.items():
        for index, row in enumerate(dataset.get(entity, []), start=2):
            if tuple(row.keys()) != fields:
                errors.append(f"{entity}:{index}: cabeçalho inválido")
                continue
            for field in fields:
                if row[field] == "" and field not in NULLABLE.get(entity, ()):
                    errors.append(f"{entity}:{index}: {field} obrigatório")

    for index, row in enumerate(dataset.get("customers", []), start=2):
        if row.get("customer_segment") not in DOMAINS["customer_segment"]:
            errors.append(f"customers:{index}: customer_segment fora do domínio")
        if _parse_date(row.get("created_at", "")) is None:
            errors.append(f"customers:{index}: created_at inválido")
        if _parse_timestamp(row.get("updated_at", "")) is None:
            errors.append(f"customers:{index}: updated_at inválido")

    for index, row in enumerate(dataset.get("contracts", []), start=2):
        if row.get("product_type") not in DOMAINS["product_type"]:
            errors.append(f"contracts:{index}: product_type fora do domínio")
        if row.get("status") not in DOMAINS["contract_status"]:
            errors.append(f"contracts:{index}: status fora do domínio")
        start = _parse_date(row.get("start_date", ""))
        end = _parse_date(row.get("end_date", ""))
        if start is None or end is None or end <= start:
            errors.append(f"contracts:{index}: end_date deve ser posterior a start_date")
        principal = _parse_decimal(row.get("principal_amount", ""))
        if principal is None or principal <= 0:
            errors.append(f"contracts:{index}: principal_amount inválido")
        rate = _parse_decimal(row.get("annual_interest_rate", ""))
        if rate is None or not Decimal("0") <= rate <= Decimal("1"):
            errors.append(f"contracts:{index}: annual_interest_rate inválido")
        if _parse_timestamp(row.get("updated_at", "")) is None:
            errors.append(f"contracts:{index}: updated_at inválido")

    for index, row in enumerate(dataset.get("installments", []), start=2):
        if row.get("status") not in DOMAINS["installment_status"]:
            errors.append(f"installments:{index}: status fora do domínio")
        if _parse_date(row.get("due_date", "")) is None:
            errors.append(f"installments:{index}: due_date inválido")
        if row.get("paid_at") and _parse_date(row["paid_at"]) is None:
            errors.append(f"installments:{index}: paid_at inválido")
        number = _parse_decimal(row.get("installment_number", ""))
        if number is None or number <= 0 or number != number.to_integral_value():
            errors.append(f"installments:{index}: installment_number inválido")
        due_amount = _parse_decimal(row.get("amount_due", ""))
        paid_amount = _parse_decimal(row.get("amount_paid", ""))
        if due_amount is None or due_amount <= 0:
            errors.append(f"installments:{index}: amount_due inválido")
        if paid_amount is None or paid_amount not in (Decimal("0"), due_amount):
            errors.append(f"installments:{index}: amount_paid inválido")
        if _parse_timestamp(row.get("updated_at", "")) is None:
            errors.append(f"installments:{index}: updated_at inválido")

    _check_unique(
        errors,
        "customers",
        dataset.get("customers", []),
        lambda row: row.get("customer_id"),
        "customer_id",
    )
    _check_unique(
        errors,
        "contracts",
        dataset.get("contracts", []),
        lambda row: row.get("contract_id"),
        "contract_id",
    )
    _check_unique(
        errors,
        "installments",
        dataset.get("installments", []),
        lambda row: (row.get("contract_id"), row.get("installment_number")),
        "contract_id/installment_number",
    )

    customer_ids = {row.get("customer_id") for row in dataset.get("customers", [])}
    contract_ids = {row.get("contract_id") for row in dataset.get("contracts", [])}
    contract_starts = {
        row.get("contract_id"): _parse_date(row.get("start_date", ""))
        for row in dataset.get("contracts", [])
    }

    for index, row in enumerate(dataset.get("contracts", []), start=2):
        if row.get("customer_id") not in customer_ids:
            errors.append(f"contracts:{index}: customer_id sem relacionamento")

    for index, row in enumerate(dataset.get("installments", []), start=2):
        if row.get("contract_id") not in contract_ids:
            errors.append(f"installments:{index}: contract_id sem relacionamento")
            continue
        start = contract_starts.get(row.get("contract_id"))
        paid_at = _parse_date(row["paid_at"]) if row.get("paid_at") else None
        if paid_at is not None and start is not None and paid_at < start:
            errors.append(f"installments:{index}: paid_at anterior ao contrato")

    return sorted(errors)
