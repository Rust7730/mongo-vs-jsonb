import json

from orchestrator.dataload import same_dataset, validate
from tests.fixture_gen import main as make_fixture


def test_fixture_satisfies_the_contract(tmp_path):
    p = tmp_path / "f.ndjson"
    make_fixture(500, p)
    report = validate(p)
    assert report["errors"] == [] and report["count"] == 500


def test_validate_rejects_bad_timestamp_and_string_prices(tmp_path):
    p = tmp_path / "f.ndjson"
    make_fixture(50, p)
    docs = [json.loads(l) for l in p.read_text().splitlines()]
    docs[0]["timestamp"] = "2026-01-01 00:00:00"
    docs[1]["items"][0]["price"] = "99.0"
    docs[2]["order_id"] = docs[3]["order_id"]
    p.write_text("".join(json.dumps(d) + "\n" for d in docs))
    errors = " ".join(validate(p)["errors"])
    assert "timestamp" in errors and "numérico" in errors and "duplicado" in errors


def test_same_dataset_tolerates_only_float_rounding():
    a = {"count": 10, "completed": 5, "total": 1000.0000001}
    assert same_dataset(a, {"count": 10, "completed": 5, "total": 1000.0})
    assert not same_dataset(a, {"count": 10, "completed": 5, "total": 1001.0})
    assert not same_dataset(a, {"count": 9, "completed": 5, "total": 1000.0})
