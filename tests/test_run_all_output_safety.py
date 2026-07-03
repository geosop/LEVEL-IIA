import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run_run_all(*args):
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "run_all.py"), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )


def test_run_all_refuses_existing_run_directory_without_overwrite(tmp_path):
    outdir = tmp_path / "outputs"
    args = [
        "--config",
        "configs/anchor.yaml",
        "--M",
        "5",
        "--outdir",
        str(outdir),
    ]

    first = run_run_all(*args)
    assert first.returncode == 0, first.stderr

    run_dirs = [p for p in outdir.iterdir() if p.is_dir()]
    assert len(run_dirs) == 1
    run_dir = run_dirs[0]

    sentinel = run_dir / "raw" / "sentinel.txt"
    sentinel.write_text("do not overwrite silently\n", encoding="utf-8")

    second = run_run_all(*args)
    assert second.returncode != 0
    assert "Run directory already exists" in (second.stdout + second.stderr)
    assert sentinel.exists()
    assert sentinel.read_text(encoding="utf-8") == "do not overwrite silently\n"


def test_run_all_overwrite_removes_stale_files(tmp_path):
    outdir = tmp_path / "outputs"
    args = [
        "--config",
        "configs/anchor.yaml",
        "--M",
        "5",
        "--outdir",
        str(outdir),
    ]

    first = run_run_all(*args)
    assert first.returncode == 0, first.stderr

    run_dir = next(p for p in outdir.iterdir() if p.is_dir())
    sentinel = run_dir / "raw" / "sentinel.txt"
    sentinel.write_text("stale file\n", encoding="utf-8")

    overwrite = run_run_all(*args, "--overwrite")
    assert overwrite.returncode == 0, overwrite.stderr
    assert not sentinel.exists()


def test_run_all_refuses_resume_of_completed_run_directory(tmp_path):
    outdir = tmp_path / "outputs"
    args = [
        "--config",
        "configs/anchor.yaml",
        "--M",
        "5",
        "--outdir",
        str(outdir),
    ]

    first = run_run_all(*args)
    assert first.returncode == 0, first.stderr

    run_dir = next(p for p in outdir.iterdir() if p.is_dir())
    metadata_dir = run_dir / "metadata"
    metadata_dir.mkdir(parents=True, exist_ok=True)
    (metadata_dir / "run_metadata.json").write_text("{}\n", encoding="utf-8")

    resumed = run_run_all(*args, "--resume")
    assert resumed.returncode != 0
    assert "Completed run directory already exists" in (
        resumed.stdout + resumed.stderr
    )


def test_run_all_refuses_resume_when_run_directory_absent(tmp_path):
    outdir = tmp_path / "outputs"
    args = [
        "--config",
        "configs/anchor.yaml",
        "--M",
        "5",
        "--outdir",
        str(outdir),
        "--resume",
    ]

    resumed = run_run_all(*args)
    assert resumed.returncode != 0
    assert "Cannot resume because the deterministic run directory does not exist" in (
        resumed.stdout + resumed.stderr
    )
