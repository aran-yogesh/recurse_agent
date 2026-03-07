# ── System prompts (static strings) ──────────────────────────────────────────

EXTRACT_SYSTEM = (
    "You are a code review analyzer. "
    "Extract all feedback, comments, and suggestions from the screenshot accurately."
)

MEMORY_SYSTEM = (
    "You maintain a developer's code review history log (memory.md). "
    "Be concise and factual. Use clean markdown."
)

SKILLS_SYSTEM = (
    "You maintain a developer's coding rules file (skills.md). "
    "This file is read by an AI coding assistant to prevent review issues. "
    "Be specific, actionable, and direct."
)

AGENTS_SYSTEM = (
    "You maintain an AI coding agent's checklist file (agents.md). "
    "This tells the agent what to verify before completing any code task. "
    "Be direct and checklist-focused."
)

REFLECT_SYSTEM = (
    "You review coding pattern files for consistency, completeness, and coherence "
    "after a new code review was processed."
)

REVISE_SYSTEM = (
    "You improve coding pattern files to be more coherent, consistent, and useful "
    "for an AI coding assistant."
)


# ── User prompt builders (parameterized) ─────────────────────────────────────

# Used when input is a screenshot
EXTRACT_USER = (
    "Analyze this code review screenshot. "
    "Extract all visible feedback, comments, and suggestions from the reviewer. "
    "Identify the general pattern or rule being violated for each comment."
)


def extract_from_text_prompt(review_text: str) -> str:
    """Used when input is raw PR comment text (from GitHub webhook)."""
    return (
        "Structure these GitHub PR review comments into discrete feedback issues. "
        "For each comment, identify the general coding rule being violated.\n\n"
        f"PR COMMENTS:\n{review_text}"
    )


def memory_update_prompt(existing: str, date: str, image_name: str, feedback_json: str) -> str:
    return f"""Add this new review to memory.md.

EXISTING CONTENT:
{existing or "(empty — this is the first entry)"}

NEW REVIEW — {date} (source: {image_name}):
{feedback_json}

Rules:
- Add a new dated section at the END, never modify existing entries
- Each issue = one concise bullet point
- Include overall_theme as the section summary line
- Use clean markdown

Return the complete updated memory.md."""


def skills_update_prompt(existing: str, issues_json: str) -> str:
    return f"""Update skills.md with patterns learned from this review.

EXISTING CONTENT:
{existing or "(empty — this is the first entry)"}

NEW PATTERNS:
{issues_json}

Rules:
- Organize rules under category headers (## Error Handling, ## Naming, etc.)
- Each rule = one bullet starting with a verb (Always / Never / Use / Avoid)
- If a rule already exists, append *(seen again)* to mark recurrence
- Include bad/good code snippets inline where it adds clarity
- Write as direct commands to an AI coding assistant — no fluff

Return the complete updated skills.md."""


def agents_update_prompt(existing: str, feedback_json: str) -> str:
    return f"""Update agents.md based on this review.

EXISTING CONTENT:
{existing or "(empty — this is the first entry)"}

REVIEW DATA:
{feedback_json}

Rules:
- Keep a ## Pre-Submit Checklist section with checkbox items
- Keep a ## Priority Rules section for critical/major severity issues
- Mark repeatedly seen issues with 🔴 RECURRING
- Write as direct instructions to the agent (e.g., "Before finishing, verify...")
- Keep it under 40 lines — be ruthlessly concise

Return the complete updated agents.md."""


def reflect_prompt(memory: str, skills: str, agents: str, theme: str) -> str:
    return f"""Review these three files that were just updated from a code review.

Theme of this review: "{theme}"

MEMORY.MD:
{memory}

SKILLS.MD:
{skills}

AGENTS.MD:
{agents}

Check for:
1. Contradictions between the files
2. Duplicate rules that should be merged
3. Issues captured in memory but missing from skills
4. Poorly structured or unclear sections

Decide if a revision pass is needed."""


def revise_prompt(file_name: str, content: str, focus_areas: list[str]) -> str:
    areas = "\n".join(f"- {area}" for area in focus_areas)
    return f"""Revise {file_name} to address these specific issues:
{areas}

CURRENT CONTENT:
{content}

Return the complete improved content of {file_name}."""
