from pathlib import Path

CLAUDE_MD_IMPORTS = """\
<!-- review-agent: auto-managed code quality context -->
@memory.md
@skills.md
@agents.md
<!-- end review-agent -->"""


def read_md(target_dir: str, filename: str) -> str:
    """Read a markdown file from target_dir, or return empty string if missing."""
    path = Path(target_dir) / filename
    return path.read_text() if path.exists() else ""


def write_md(target_dir: str, filename: str, content: str) -> None:
    """Write content to a markdown file inside target_dir."""
    path = Path(target_dir) / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def ensure_claude_md(target_dir: str) -> None:
    """Create CLAUDE.md (or prepend imports if it already exists)."""
    path = Path(target_dir) / "CLAUDE.md"

    if path.exists():
        existing = path.read_text()
        if "@skills.md" in existing:
            return  # already set up, nothing to do
        path.write_text(CLAUDE_MD_IMPORTS + "\n\n" + existing)
    else:
        path.write_text(
            "# Code Quality Context\n\n"
            "Auto-managed by review-agent. Add your own project notes below.\n\n"
            + CLAUDE_MD_IMPORTS
        )
