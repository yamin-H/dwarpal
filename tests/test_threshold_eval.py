import pytest
from threshold_sweep import evaluate, load_pairs


def test_evaluate_summarises_a_sweep():
    pairs = [{"a": "1", "b": "2", "label": "same"}, {"a": "3", "b": "4", "label": "same"},
             {"a": "5", "b": "6", "label": "different"}]
    result = evaluate(pairs, [0.97, 0.91, 0.80], max_wrong=0.0)
    assert (result["pairs_same"], result["pairs_different"]) == (2, 1)
    assert result["recommended_threshold"] == 0.81   # just above the worst near-miss (0.80)
    assert result["hit_rate_at_threshold"] == 1.0
    assert result["margin"] == pytest.approx(0.11)


def test_evaluate_needs_both_labels():
    with pytest.raises(ValueError):
        evaluate([{"a": "1", "b": "2", "label": "same"}], [0.9], 0.0)


def test_load_pairs_rejects_bad_files(tmp_path):
    f = tmp_path / "pairs.jsonl"
    f.write_text('{"a": "x", "b": "y", "label": "similar"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="invalid pairs file"):
        load_pairs(str(f))
