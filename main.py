#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

from agent import run, run_from_text


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Learn from a code review screenshot and update coding pattern files."
    )
    # @learn: screenshot is optional when --text is provided, so nargs="?" allows either mode
    parser.add_argument("screenshot", nargs="?", help="Path to the review screenshot")
    parser.add_argument(
        "--dir",
        default=".",
        metavar="DIR",
        help="Project directory where .md files will be written (default: current dir)",
    )
    # @learn: --text/-t enables text-only mode for the Electron UI and GitHub webhook use cases
    parser.add_argument("--text", "-t", help="Raw review text (alternative to screenshot)")
    args = parser.parse_args()

    target_dir = Path(args.dir).resolve()

    # Decision branch: text mode vs screenshot mode
    # @learn: we branch early so each path is clear and independently testable
    if args.text:
        # Text mode — no file I/O needed before invoking the agent
        # logging: entry point logged so subprocess output is traceable in Electron UI
        print("\nReview Agent")
        print("  Mode       : text")
        print(f"  Target dir : {target_dir}\n")
        logs = run_from_text(args.text, str(target_dir))
    else:
        # Screenshot mode — validate file exists before proceeding
        if not args.screenshot:
            print("Error: provide either a screenshot path or --text", file=sys.stderr)
            sys.exit(1)

        image_path = Path(args.screenshot).resolve()

        if not image_path.exists():
            print(f"Error: screenshot not found: {image_path}", file=sys.stderr)
            sys.exit(1)

        print("\nReview Agent")
        print(f"  Screenshot : {image_path.name}")
        print(f"  Target dir : {target_dir}\n")

        logs = run(str(image_path), str(target_dir))

    print("Run log:")
    for entry in logs:
        print(f"  • {entry}")

    print(
        "\nDone. Add to .gitignore:\n"
        "  CLAUDE.md\n"
        "  memory.md\n"
        "  skills.md\n"
        "  agents.md\n"
    )


if __name__ == "__main__":
    main()
