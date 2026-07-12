"""Run metadata: deterministic seeds, source fingerprint, and environment capture.

The run hash is a content hash over the resolved configuration set, package
version, seed family, and executable source fingerprint. Manuscript figures and
tables are tied to the frozen output directory named by this hash.
"""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import __version__


PACKAGE_DIR = Path(__file__).resolve().parent
ROOT = PACKAGE_DIR.parents[1]
SOURCE_PATHS = [
    *sorted(PACKAGE_DIR.glob("*.py")),
    ROOT / "scripts" / "run_all.py",
    ROOT / "scripts" / "make_split_oc_tables.py",
    ROOT / "scripts" / "make_false_adequacy_rates.py",
]


def package_versions():
    mods = ["numpy", "scipy", "pandas", "matplotlib", "yaml"]
    out = {}
    for m in mods:
        try:
            mod = __import__(m)
            out[m] = getattr(mod, "__version__", "unknown")
        except Exception:
            out[m] = "not-installed"
    out["python"] = sys.version.split()[0]
    return out


def git_commit():
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL
        ).decode().strip()
    except Exception:
        return "no-git"


def source_fingerprint(paths=None):
    """Hash executable source files with stable repository-relative names."""
    selected = SOURCE_PATHS if paths is None else [Path(p) for p in paths]
    digest = hashlib.sha256()
    for path in sorted(selected, key=lambda p: p.as_posix()):
        if not path.exists():
            raise FileNotFoundError(f"run-hash source file is missing: {path}")
        try:
            label = path.resolve().relative_to(ROOT.resolve()).as_posix()
        except ValueError:
            label = path.name
        digest.update(label.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def compute_run_hash(config_bundle, seed_family):
    payload = {
        "code_version": __version__,
        "source_fingerprint": source_fingerprint(),
        "seed_family": seed_family,
        "configs": config_bundle,
    }
    blob = json.dumps(payload, sort_keys=True, default=str).encode()
    return hashlib.sha256(blob).hexdigest()[:16]


def make_metadata(config_bundle, seed_family, run_hash, script_path):
    return {
        "run_hash": run_hash,
        "seed_family": seed_family,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "code_version": __version__,
        "source_fingerprint": source_fingerprint(),
        "git_commit": git_commit(),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "packages": package_versions(),
        "script_path": script_path,
        "scenarios": list(config_bundle.keys()),
    }
