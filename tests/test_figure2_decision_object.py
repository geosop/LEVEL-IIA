from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from make_figure2 import PANELS, _decision_box_text, _rate_text  # noqa: E402


def test_decision_box_uses_representative_replicate_beta_min() -> None:
    obj = {
        "out": {
            "beta": -60.124645,
            "ucb": -54.004140,
            "beta_min": 31.837233,
        }
    }

    text = _decision_box_text(obj)

    assert r"\beta_{\min} = 31.8" in text
    assert "31.4" not in text


def test_figure_uses_forward_only_adequate_reader_labels() -> None:
    anchor = PANELS[0]
    injected = PANELS[1]
    assert "FWD-ONLY ADEQUATE" in anchor["chips"]
    summary = {
        "M": 1200,
        "support_n": 0,
        "support_rate": 0.0,
        "null_n": 1073,
        "null_rate": 1073 / 1200,
    }
    anchor_rate = _rate_text(anchor, summary)
    assert "fwd-only adequate\n1073/1200 (0.8942)" in anchor_rate
    assert "\nnull " not in anchor_rate

    injected_summary = {
        "M": 1200,
        "support_n": 1189,
        "support_rate": 1189 / 1200,
        "null_n": 0,
        "null_rate": 0.0,
    }
    injected_rate = _rate_text(injected, injected_summary)
    assert "fwd-only adequate\n0/1200 (0.0000)" in injected_rate
    assert "\nnull " not in injected_rate
