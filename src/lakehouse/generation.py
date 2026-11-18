"""Gerador determinístico de dados sintéticos (Fase 2)."""

from __future__ import annotations

import csv
import random
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from lakehouse.schema import FIELDS

DEFAULT_SEED = 20261117
DEFAULT_CUSTOMERS = 10
INSTALLMENTS_PER_CONTRACT = 6
REFERENCE_DATE = date(2026, 1, 31)
SEGMENTS = ("mass", "affluent", "business")
PRODUCTS = ("personal_loan", "auto_loan")
CONTRACT_STATUSES = ("active", "closed", "cancelled")
MIN_CREATED = date(2024, 1, 1)
MAX_CREATED_OFFSET = 365


def _timestamp(day: date, extra_days: int = 0) -> str:
    value = day + timedelta(days=extra_days)
    return datetime(value.year, value.month, value.day, tzinfo=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def _money(value: Decimal) -> str:
    return f"{value:.2f}"


def _rate(value: Decimal) -> str:
    return f"{value:.4f}"


def generate_dataset(
    seed: int = DEFAULT_SEED, *, customers: int = DEFAULT_CUSTOMERS
) -> dict[str, list[dict[str, str]]]:
    rng = random.Random(seed)
    customer_rows: list[dict[str, str]] = []
    contract_rows: list[dict[str, str]] = []
    installment_rows: list[dict[str, str]] = []
    contract_number = 0

    for index in range(1, customers + 1):
        customer_id = f"C{index:06d}"
        created_at = MIN_CREATED + timedelta(days=rng.randint(0, MAX_CREATED_OFFSET))
        customer_rows.append(
            {
                "customer_id": customer_id,
                "customer_segment": rng.choice(SEGMENTS),
                "created_at": created_at.isoformat(),
                "updated_at": _timestamp(created_at, rng.randint(0, 120)),
            }
        )

        for _ in range(rng.randint(1, 2)):
            contract_number += 1
            contract_id = f"CT{contract_number:06d}"
            start_date = created_at + timedelta(days=rng.randint(0, 90))
            end_date = start_date + timedelta(days=rng.choice((180, 360, 720)))
            principal = Decimal(rng.randint(500000, 8000000)) / 100
            rate = Decimal(rng.randint(500, 6000)) / 10000
            contract_rows.append(
                {
                    "contract_id": contract_id,
                    "customer_id": customer_id,
                    "product_type": rng.choice(PRODUCTS),
                    "principal_amount": _money(principal),
                    "annual_interest_rate": _rate(rate),
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                    "status": rng.choice(CONTRACT_STATUSES),
                    "updated_at": _timestamp(start_date, rng.randint(0, 60)),
                }
            )

            amount_due = (principal / INSTALLMENTS_PER_CONTRACT).quantize(Decimal("0.01"))
            for number in range(1, INSTALLMENTS_PER_CONTRACT + 1):
                due_date = start_date + timedelta(days=30 * number)
                if due_date < REFERENCE_DATE:
                    paid = rng.random() < 0.7
                else:
                    paid = rng.random() < 0.4
                paid_at: date | None = None
                if paid:
                    limit = min(due_date, REFERENCE_DATE)
                    paid_at = max(start_date, limit - timedelta(days=rng.randint(0, 5)))
                if paid:
                    status = "paid"
                elif due_date < REFERENCE_DATE:
                    status = "overdue"
                else:
                    status = "open"
                installment_rows.append(
                    {
                        "contract_id": contract_id,
                        "installment_number": str(number),
                        "due_date": due_date.isoformat(),
                        "paid_at": paid_at.isoformat() if paid_at else "",
                        "amount_due": _money(amount_due),
                        "amount_paid": _money(amount_due) if paid else "0.00",
                        "status": status,
                        "updated_at": _timestamp(paid_at or due_date),
                    }
                )

    return {
        "customers": customer_rows,
        "contracts": contract_rows,
        "installments": installment_rows,
    }


def write_dataset(dataset: dict[str, list[dict[str, str]]], directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for entity, fields in FIELDS.items():
        with (directory / f"{entity}.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            writer.writerows(dataset[entity])


def load_dataset(directory: Path) -> dict[str, list[dict[str, str]]]:
    dataset: dict[str, list[dict[str, str]]] = {}
    for entity in FIELDS:
        with (directory / f"{entity}.csv").open(newline="", encoding="utf-8") as handle:
            dataset[entity] = list(csv.DictReader(handle))
    return dataset


def main() -> None:
    write_dataset(generate_dataset(), Path("data/sample"))


if __name__ == "__main__":
    main()
