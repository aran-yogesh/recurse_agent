"""
GitHub activity poller.

Watches your GitHub events feed for @learn mentions across ALL repos —
including repos you don't own. No webhook registration needed.

Run:
  uv run python poller.py
"""

import asyncio
import os
from datetime import datetime

import httpx
from dotenv import load_dotenv

from agent import run_from_text
from utils.filters import is_low_signal_comment

load_dotenv()

GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
GITHUB_USERNAME = os.environ["GITHUB_USERNAME"]
TARGET_DIR = os.environ.get("TARGET_DIR", ".")
LEARN_TRIGGER = "@learn"
POLL_INTERVAL_SECONDS = 30

GITHUB_HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}


def log(tag: str, msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] [{tag}] {msg}")


# ── GitHub API helpers ────────────────────────────────────────────────────────

async def fetch_all_pr_comments(client: httpx.AsyncClient, repo: str, pr_number: int) -> str:
    """Fetch review comments + issue comments from a PR and format as plain text."""
    log("fetch", f"Getting all comments from {repo} PR #{pr_number}")

    review_resp, issue_resp = await asyncio.gather(
        client.get(f"https://api.github.com/repos/{repo}/pulls/{pr_number}/comments", headers=GITHUB_HEADERS),
        client.get(f"https://api.github.com/repos/{repo}/issues/{pr_number}/comments", headers=GITHUB_HEADERS),
    )

    log("fetch", f"Review comments API → HTTP {review_resp.status_code}")
    log("fetch", f"Issue comments API  → HTTP {issue_resp.status_code}")

    if review_resp.status_code != 200:
        log("fetch", f"Review comments error: {review_resp.text[:200]}")
    if issue_resp.status_code != 200:
        log("fetch", f"Issue comments error: {issue_resp.text[:200]}")

    review_comments = review_resp.json() if review_resp.status_code == 200 else []
    issue_comments = issue_resp.json() if issue_resp.status_code == 200 else []

    if not isinstance(review_comments, list):
        log("fetch", f"Unexpected review_comments response: {review_comments}")
        review_comments = []
    if not isinstance(issue_comments, list):
        log("fetch", f"Unexpected issue_comments response: {issue_comments}")
        issue_comments = []

    log("fetch", f"Found {len(review_comments)} review comment(s), {len(issue_comments)} issue comment(s)")

    sections = []
    skipped = 0
    for c in review_comments:
        if is_low_signal_comment(c):
            skipped += 1
            continue
        author = c["user"]["login"]
        path = c.get("path", "unknown file")
        line = c.get("line") or c.get("original_line", "")
        sections.append(f"Review on `{path}` line {line} by @{author}:\n{c['body']}")

    for c in issue_comments:
        if is_low_signal_comment(c):
            skipped += 1
            continue
        sections.append(f"PR comment by @{c['user']['login']}:\n{c['body']}")

    if skipped:
        log("fetch", f"Filtered {skipped} low-signal comment(s)")

    result = "\n\n---\n\n".join(sections)
    log("fetch", f"Total text length: {len(result)} chars")
    return result


async def try_thumbs_up(client: httpx.AsyncClient, repo: str, comment_id: int, event_type: str) -> None:
    """React 👍 to the triggering comment. Fails silently on repos without write access."""
    if event_type == "PullRequestReviewCommentEvent":
        url = f"https://api.github.com/repos/{repo}/pulls/comments/{comment_id}/reactions"
    else:
        url = f"https://api.github.com/repos/{repo}/issues/comments/{comment_id}/reactions"

    log("react", f"Adding 👍 → {url}")
    resp = await client.post(url, headers=GITHUB_HEADERS, json={"content": "+1"})
    log("react", f"HTTP {resp.status_code} — {'ok' if resp.status_code in (200, 201) else resp.text[:100]}")


# ── Core polling logic ────────────────────────────────────────────────────────

async def process_event(client: httpx.AsyncClient, event: dict) -> None:
    """Handle a single @learn event: react, fetch comments, run agent."""
    event_type = event["type"]
    payload = event.get("payload", {})
    comment = payload.get("comment", {})
    repo = event["repo"]["name"]
    comment_id = comment.get("id")

    pr_number = (
        payload.get("pull_request", {}).get("number")
        or payload.get("issue", {}).get("number")
    )

    log("trigger", f"@learn found! repo={repo} pr={pr_number} comment_id={comment_id} type={event_type}")

    if not pr_number:
        log("trigger", "Could not resolve PR number — skipping")
        return

    await try_thumbs_up(client, repo, comment_id, event_type)

    review_text = await fetch_all_pr_comments(client, repo, pr_number)

    if not review_text.strip():
        log("agent", "No comments found in PR — skipping agent run")
        return

    log("agent", f"Running review agent on {len(review_text)} chars of comments...")
    logs = await asyncio.to_thread(run_from_text, review_text, TARGET_DIR)
    for entry in logs:
        log("agent", entry)


async def poll_once(client: httpx.AsyncClient, last_event_id: str | None) -> str | None:
    """Fetch latest events, process new @learn mentions. Returns the newest event ID."""
    log("poll", f"Fetching events for @{GITHUB_USERNAME}...")

    resp = await client.get(
        f"https://api.github.com/users/{GITHUB_USERNAME}/events",
        headers={**GITHUB_HEADERS, "per_page": "100"},
    )

    log("poll", f"GitHub API → HTTP {resp.status_code}")

    if resp.status_code != 200:
        log("poll", f"Error response: {resp.text[:200]}")
        return last_event_id

    events = resp.json()

    if not isinstance(events, list):
        log("poll", f"Unexpected response (not a list): {events}")
        return last_event_id

    if not events:
        log("poll", "No events returned")
        return last_event_id

    newest_id = events[0]["id"]
    log("poll", f"Latest event ID: {newest_id} | Last seen: {last_event_id}")

    # Collect only events newer than the last seen one
    new_events = []
    for event in events:
        if event["id"] == last_event_id:
            break
        new_events.append(event)

    log("poll", f"{len(new_events)} new event(s) since last poll")

    for e in new_events:
        body = e.get("payload", {}).get("comment", {}).get("body", "")[:80]
        log("poll", f"  type={e['type']} repo={e['repo']['name']} body={repr(body)}")

    # Process oldest-first so memory.md stays in chronological order
    for event in reversed(new_events):
        event_type = event["type"]

        if event_type not in ("PullRequestReviewCommentEvent", "IssueCommentEvent"):
            log("poll", f"  Skipping {event_type} (not a comment event)")
            continue

        body = event.get("payload", {}).get("comment", {}).get("body", "")

        if LEARN_TRIGGER not in body:
            log("poll", f"  Skipping — no '{LEARN_TRIGGER}' in body: {repr(body[:60])}")
            continue

        log("poll", f"  '{LEARN_TRIGGER}' matched! Processing...")
        try:
            await process_event(client, event)
        except Exception as exc:
            log("error", f"Failed to process event: {exc}")
            import traceback
            traceback.print_exc()

    return newest_id


# ── Entry point ───────────────────────────────────────────────────────────────

async def main() -> None:
    log("startup", f"Watching @{GITHUB_USERNAME} for '{LEARN_TRIGGER}' mentions")
    log("startup", f"Writing patterns to: {TARGET_DIR}")
    log("startup", f"Polling every {POLL_INTERVAL_SECONDS}s — Ctrl+C to stop")

    async with httpx.AsyncClient() as client:
        log("startup", "Seeding last event ID...")
        resp = await client.get(
            f"https://api.github.com/users/{GITHUB_USERNAME}/events",
            headers=GITHUB_HEADERS,
        )
        log("startup", f"Seed request → HTTP {resp.status_code}")
        events = resp.json()

        if not isinstance(events, list):
            log("startup", f"GitHub API error: {events.get('message', events)}")
            log("startup", "Check GITHUB_TOKEN and GITHUB_USERNAME in .env")
            return

        last_event_id = events[0]["id"] if events else None
        log("startup", f"Seeded to event {last_event_id} — now listening\n")

        while True:
            try:
                last_event_id = await poll_once(client, last_event_id)
            except Exception as exc:
                log("error", f"Unexpected error in poll loop: {exc}")
                import traceback
                traceback.print_exc()

            await asyncio.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    asyncio.run(main())
