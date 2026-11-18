from datetime import date
from pathlib import Path

from lakehouse.generation import (
    DEFAULT_SEED,
    INSTALLMENTS_PER_CONTRACT,
    REFERENCE_DATE,
    generate_dataset,
    write_dataset,
)
from lakehouse.schema import FIELDS, validate_dataset

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_DIR = REPO_ROOT / "data" / "sample"


def test_generation_is_reproducible():
    first = generate_dataset(DEFAULT_SEED)
    second = generate_dataset(DEFAULT_SEED)
    assert first == second
    assert validate_dataset(first) == []


def test_different_seed_changes_data():
    assert generate_dataset(DEFAULT_SEED) != generate_dataset(DEFAULT_SEED + 1)


def test_sample_files_match_generator(tmp_path):
    write_dataset(generate_dataset(DEFAULT_SEED), tmp_path)
    for entity in FIELDS:
        generated = (tmp_path / f"{entity}.csv").read_bytes()
        versioned = (SAMPLE_DIR / f"{entity}.csv").read_bytes()
        assert generated == versioned


def test_counts_and_relationships():
    dataset = generate_dataset(DEFAULT_SEED)
    assert len(dataset["customers"]) == 10
    assert 10 <= len(dataset["contracts"]) <= 20
    assert len(dataset["installments"]) == (
        INSTALLMENTS_PER_CONTRACT * len(dataset["contracts"])
    )
    customer_ids = {row["customer_id"] for row in dataset["customers"]}
    contract_ids = {row["contract_id"] for row in dataset["contracts"]}
    assert all(row["customer_id"] in customer_ids for row in dataset["contracts"])
    assert all(row["contract_id"] in contract_ids for row in dataset["installments"])


def test_statuses_and_dates_are_coherent():
    dataset = generate_dataset(DEFAULT_SEED)
    starts = {
        row["contract_id"]: date.fromisoformat(row["start_date"])
        for row in dataset["contracts"]
    }
    for row in dataset["installments"]:
        due = date.fromisoformat(row["due_date"])
        paid_at = date.fromisoformat(row["paid_at"]) if row["paid_at"] else None
        assert due >= starts[row["contract_id"]]
        if row["status"] == "paid":
            assert paid_at is not None
            assert paid_at >= starts[row["contract_id"]]
        else:
            assert paid_at is None
        if row["status"] == "overdue":
            assert due < REFERENCE_DATE
        if row["status"] == "open":
            assert due >= REFERENCE_DATE


def test_rows_have_only_technical_identifiers():
    dataset = generate_dataset(DEFAULT_SEED)
    personal_fields = {"name", "cpf", "address", "account"}
    for rows in dataset.values():
        for row in rows:
            assert not personal_fields & set(row)
