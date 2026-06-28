"""Run metadata: deterministic seeds, run-hash, and environment capture.

The run hash is a content hash over the resolved configuration set and the code
version, so a given configuration and code state always map to the same hash. The
manuscript figures and tables are tied to a frozen output directory named by this
hash.
"""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone

from . import __version__


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


def compute_run_hash(config_bundle, seed_family):
    payload = {
        "code_version": __version__,
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
        "git_commit": git_commit(),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "packages": package_versions(),
        "script_path": script_path,
        "scenarios": list(config_bundle.keys()),
    }
