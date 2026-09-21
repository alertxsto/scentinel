from pathlib import Path

from scentinel.core import history

ROOT = Path(__file__).parents[2]


def test_the_documents_do_not_claim_an_old_manifest_version():
    for name in ("README.md", "docs/ROADMAP.md", "docs/ARCHITECTURE.md"):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert "format 8" not in text, name
        assert "format version 8" not in text, name


def test_the_documents_cite_the_current_mesh_gate_number():
    roadmap = (ROOT / "docs" / "ROADMAP.md").read_text(encoding="utf-8")
    assert "266.29" in roadmap
    assert "76.5%" not in roadmap


def test_the_manifest_version_constant_is_ten():
    assert history.RUN_FORMAT_VERSION == 10


def test_the_roadmap_describes_the_current_generation_contract():
    roadmap = (ROOT / "docs" / "ROADMAP.md").read_text(encoding="utf-8")
    normalized = " ".join(roadmap.split())
    assert "Manifest format 6" not in roadmap
    assert "Manifest format 10" in roadmap
    assert "measurement-replaceable default" in normalized
    assert "CO₂ carbon closure is an explicit model assumption" in normalized
