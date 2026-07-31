from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from make_tables import remove_legacy_manuscript_tables  # noqa: E402


def test_remove_legacy_adequacy_table_preserves_current_route_tables(tmp_path):
    legacy = tmp_path / "adequacy_operating_characteristic.tex"
    assignment = (
        tmp_path / "adequacy_operating_characteristic_assignment_isolation.tex"
    )
    sequential = tmp_path / "adequacy_operating_characteristic_sequential_evalue.tex"

    legacy.write_text("legacy\n", encoding="utf-8")
    assignment.write_text("assignment\n", encoding="utf-8")
    sequential.write_text("sequential\n", encoding="utf-8")

    remove_legacy_manuscript_tables(tmp_path)

    assert not legacy.exists()
    assert assignment.read_text(encoding="utf-8") == "assignment\n"
    assert sequential.read_text(encoding="utf-8") == "sequential\n"
