"""Determinism: identical seeds reproduce identical results; the run hash is a
content hash of the config bundle."""
import numpy as np, yaml
from pathlib import Path
from cri_leveliia.benchmarks import run_one
from cri_leveliia import metadata

ROOT = Path(__file__).resolve().parents[1]

def test_replicate_is_deterministic():
    cfg = yaml.safe_load(open(ROOT / "configs/anchor.yaml"))
    a = run_one(cfg, 101, 3)["beta"]
    b = run_one(cfg, 101, 3)["beta"]
    assert a == b

def test_different_replicates_differ():
    cfg = yaml.safe_load(open(ROOT / "configs/anchor.yaml"))
    assert run_one(cfg, 101, 3)["beta"] != run_one(cfg, 101, 4)["beta"]

def test_run_hash_is_stable_and_content_dependent():
    b1 = {"a": {"x": 1}}
    b2 = {"a": {"x": 2}}
    assert metadata.compute_run_hash(b1, "full") == metadata.compute_run_hash(b1, "full")
    assert metadata.compute_run_hash(b1, "full") != metadata.compute_run_hash(b2, "full")
