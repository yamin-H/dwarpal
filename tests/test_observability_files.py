import json
import re
from pathlib import Path

from app.observability.metrics import Metrics
from app.routing.router import Router

ROOT = Path(__file__).resolve().parents[1] / "observability"
SUFFIXES = ("_bucket", "_count", "_sum", "_total")


def known_families() -> set[str]:
    m = Metrics()
    m.bind_router(Router(lambda name: None))
    return {family.name for family in m.registry.collect()}


def referenced(text: str) -> set[str]:
    names = set()
    for token in re.findall(r"dwarpal_[a-z_]+", text):
        for suffix in SUFFIXES:
            if token.endswith(suffix):
                token = token[: -len(suffix)]
                break
        names.add(token)
    return names


def test_dashboard_is_valid_and_uses_only_real_metrics():
    path = ROOT / "grafana" / "dashboards" / "gateway.json"
    text = path.read_text(encoding="utf-8")
    dash = json.loads(text)
    panels = dash["panels"]
    assert len({p["id"] for p in panels}) == len(panels)
    assert all(p["targets"] for p in panels)
    used = referenced(text)
    assert used, "dashboard references no dwarpal metrics"
    assert not used - known_families(), f"unknown metrics: {used - known_families()}"


def test_alert_rules_use_only_real_metrics():
    text = (ROOT / "prometheus" / "alerts.yml").read_text(encoding="utf-8")
    used = referenced(text)
    assert used, "alerts reference no dwarpal metrics"
    assert not used - known_families(), f"unknown metrics: {used - known_families()}"