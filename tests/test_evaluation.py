import pytest

from app.cache.evaluation import cosine, recommend, sweep, thresholds


def test_cosine():
    assert cosine([1, 0], [1, 0]) == pytest.approx(1.0)
    assert cosine([1, 0], [0, 1]) == pytest.approx(0.0)
    assert cosine([0, 0], [1, 0]) == 0.0


def test_thresholds_range():
    ts = thresholds()
    assert ts[0] == 0.70 and ts[-1] == 0.99 and len(ts) == 30


def test_sweep_and_recommend():
    rows = {r["threshold"]: r for r in sweep([0.97, 0.93, 0.88], [0.91, 0.80], [0.85, 0.90, 0.95])}
    assert rows[0.85]["hit_rate"] == 1.0 and rows[0.85]["wrong_hit_rate"] == 0.5
    assert rows[0.95]["hit_rate"] == pytest.approx(1 / 3) and rows[0.95]["wrong_hit_rate"] == 0.0
    assert recommend(list(rows.values()), 0.0) == 0.95


def test_recommend_none_when_model_cannot_separate():
    rows = sweep([0.90], [0.99], [0.90, 0.95])
    assert recommend(rows, 0.0) is None



import json
from pathlib import Path

from app.cache.evaluation import separation_margin, validate_pairs


def test_separation_margin():
    assert separation_margin([0.9, 0.95], [0.8, 0.85]) == pytest.approx(0.05)
    assert separation_margin([0.9], [0.95]) == pytest.approx(-0.05)
    assert separation_margin([], [0.5]) is None


def pair(a, b, label="same"):
    return {"a": a, "b": b, "label": label}


def test_validate_pairs_catches_common_mistakes():
    assert validate_pairs([pair("a1", "b1"), pair("a2", "b2", "different")]) == []
    assert any("label" in e for e in validate_pairs([pair("a", "b", "similar")]))
    assert any("identical" in e for e in validate_pairs([pair("a", " a ")]))
    assert any("non-empty" in e for e in validate_pairs([pair("", "b")]))
    assert any("duplicates" in e for e in validate_pairs([pair("a", "b"), pair("b", "a")]))
    assert any("contradicts" in e
               for e in validate_pairs([pair("a", "b"), pair("b", "a", "different")]))
    assert any("object" in e for e in validate_pairs(["not a dict"]))


def test_the_shipped_pairs_file_is_valid():
    path = Path(__file__).resolve().parents[1] / "data" / "bench" / "pairs.jsonl"
    pairs = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
             if line.strip()]
    assert validate_pairs(pairs) == []
    labels = {p["label"] for p in pairs}
    assert labels == {"same", "different"}
