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