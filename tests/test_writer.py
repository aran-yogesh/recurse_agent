"""Tests for utils.writer — markdown file I/O and CLAUDE.md bootstrapping."""
from pathlib import Path

from utils.writer import CLAUDE_MD_IMPORTS, ensure_claude_md, read_md, write_md


class TestReadMd:
    def test_returns_empty_for_missing_file(self, tmp_path):
        assert read_md(str(tmp_path), "nope.md") == ""

    def test_reads_existing_file(self, tmp_path):
        (tmp_path / "memory.md").write_text("hello world")
        assert read_md(str(tmp_path), "memory.md") == "hello world"


class TestWriteMd:
    def test_writes_file(self, tmp_path):
        write_md(str(tmp_path), "skills.md", "# Skills\n")
        assert (tmp_path / "skills.md").read_text() == "# Skills\n"

    def test_creates_parent_dirs(self, tmp_path):
        nested = tmp_path / "a" / "b" / "c"
        write_md(str(nested), "agents.md", "content")
        assert (nested / "agents.md").read_text() == "content"

    def test_overwrites_existing(self, tmp_path):
        write_md(str(tmp_path), "x.md", "first")
        write_md(str(tmp_path), "x.md", "second")
        assert (tmp_path / "x.md").read_text() == "second"


class TestEnsureClaudeMd:
    def test_creates_new_file(self, tmp_path):
        ensure_claude_md(str(tmp_path))
        text = (tmp_path / "CLAUDE.md").read_text()
        assert "@memory.md" in text
        assert "@skills.md" in text
        assert "@agents.md" in text

    def test_prepends_to_existing_without_imports(self, tmp_path):
        existing = "# My Project\n\nSome notes.\n"
        (tmp_path / "CLAUDE.md").write_text(existing)
        ensure_claude_md(str(tmp_path))
        text = (tmp_path / "CLAUDE.md").read_text()
        assert text.startswith(CLAUDE_MD_IMPORTS)
        assert existing in text

    def test_idempotent_when_imports_present(self, tmp_path):
        # Set up CLAUDE.md that already has imports
        ensure_claude_md(str(tmp_path))
        first = (tmp_path / "CLAUDE.md").read_text()
        ensure_claude_md(str(tmp_path))
        second = (tmp_path / "CLAUDE.md").read_text()
        assert first == second  # unchanged
        # No duplication of import block
        assert second.count("@skills.md") == 1


def test_round_trip(tmp_path: Path):
    """read_md should return exactly what write_md wrote."""
    payload = "# Memory\n\n- review 2025-01-01\n- review 2025-01-02\n"
    write_md(str(tmp_path), "memory.md", payload)
    assert read_md(str(tmp_path), "memory.md") == payload
