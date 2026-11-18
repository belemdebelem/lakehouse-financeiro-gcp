from pathlib import Path

from lakehouse.generation import DEFAULT_SEED, generate_dataset, load_dataset
from lakehouse.schema import FIELDS, validate_dataset

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_DIR = REPO_ROOT / "data" / "sample"
INVALID_DIR = SAMPLE_DIR / "invalid"


def test_valid_dataset_has_no_structural_errors():
    assert validate_dataset(generate_dataset(DEFAULT_SEED)) == []


def test_versioned_samples_validate():
    assert validate_dataset(load_dataset(SAMPLE_DIR)) == []


def test_headers_match_schema():
    dataset = generate_dataset(DEFAULT_SEED)
    for entity, fields in FIELDS.items():
        assert tuple(dataset[entity][0]) == fields


def test_invalid_examples_are_rejected():
    errors = validate_dataset(load_dataset(INVALID_DIR))
    expected = (
        "customer_id duplicado",
        "customer_segment fora do domínio",
        "product_type fora do domínio",
        "customer_id sem relacionamento",
        "end_date deve ser posterior a start_date",
        "amount_paid inválido",
        "contract_id sem relacionamento",
        "status fora do domínio",
    )
    for message in expected:
        assert any(message in error for error in errors), message
