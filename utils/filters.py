"""Filter low-signal PR comments before they reach the LLM.

A comment is low-signal if it carries no actionable review feedback:
  - Posted by a bot (GitHub `User.type == "Bot"` or known bot login)
  - Empty / whitespace only
  - Emoji-only (including GitHub `:shortcode:` form)
  - Matches a short approval phrase like "lgtm", "+1", "ship it"
"""

import re

_BOT_LOGINS = {
    "dependabot",
    "dependabot-preview",
    "github-actions",
    "codecov",
    "codecov-commenter",
    "renovate",
    "snyk-bot",
    "sonarcloud",
    "coderabbitai",
    "vercel",
    "netlify",
}

_APPROVAL_PHRASES = {
    "lgtm",
    "lgtm!",
    "looks good",
    "looks good to me",
    "looks good!",
    "looks good to me!",
    "approved",
    "approve",
    "ship it",
    "shipit",
    "ship it!",
    "+1",
    "+1!",
    "nice",
    "nice!",
    "thanks",
    "thanks!",
    "ty",
    "thx",
    "done",
    "fixed",
    "k",
    "ok",
    "ack",
    "ditto",
    "same",
    "agreed",
    "yep",
    "yes",
    "no",
}

_EMOJI_SHORTCODE = re.compile(r":[a-z0-9_+\-]+:")
_NON_EMOJI_CHAR = re.compile(
    r"[A-Za-z0-9]"  # any ASCII letter or digit means it's not emoji-only
)


def is_bot_user(user: dict) -> bool:
    """True if the GitHub user object represents a bot."""
    if not user:
        return False
    if user.get("type") == "Bot":
        return True
    login = (user.get("login") or "").lower()
    if login.endswith("[bot]"):
        return True
    return login in _BOT_LOGINS


def is_low_signal_body(body: str) -> bool:
    """True if the comment body carries no reviewable content."""
    if not body or not body.strip():
        return True

    stripped = _EMOJI_SHORTCODE.sub("", body).strip()
    if not stripped:
        return True

    # Emoji-only Unicode comment (no letters/digits left after stripping shortcodes)
    if not _NON_EMOJI_CHAR.search(stripped):
        return True

    normalized = re.sub(r"[\s.!?]+", " ", stripped.lower()).strip()
    if normalized in _APPROVAL_PHRASES:
        return True

    return False


def is_low_signal_comment(comment: dict) -> bool:
    """True if the GitHub comment object should be skipped."""
    if is_bot_user(comment.get("user", {})):
        return True
    return is_low_signal_body(comment.get("body", ""))
