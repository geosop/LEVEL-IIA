from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from make_figure2 import _decision_box_text  # noqa: E402


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
