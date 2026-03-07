"""
GitHub webhook receiver.

When you tag @learn in any PR review comment, this server:
  1. Reacts to your comment with 👍 to confirm it was received
  2. Fetches all review comments from that PR
  3. Runs the review agent to update memory.md, skills.md, agents.md

Setup:
  - Set GITHUB_TOKEN, GITHUB_WEBHOOK_SECRET, and TARGET_DIR in .env
  - Expose this server publicly (e.g. ngrok) and register the webhook in GitHub
  - GitHub webhook events to subscribe: pull_request_review_comment, issue_comment

Run:
  uv run uvicorn webhook:app --reload
"""

import asyncio
import hashlib
import hmac
import os

import httpx
from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request

from agent import run_from_text

load_dotenv()

GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
WEBHOOK_SECRET = os.environ["GITHUB_WEBHOOK_SECRET"]
TARGET_DIR = os.environ.get("TARGET_DIR", ".")
LEARN_TRIGGER = "@learn"

GITHUB_HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}

app = FastAPI(title="Review Agent Webhook")


# ── Signature verification ────────────────────────────────────────────────────

def is_valid_signature(payload: bytes, signature_header: str) -> bool:
    """Verify GitHub's HMAC-SHA256 webhook signature."""
    if not signature_header.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(
        WEBHOOK_SECRET.encode(), msg=payload, digestmod=hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header)


# ── GitHub API helpers ────────────────────────────────────────────────────────

async def add_thumbs_up(client: httpx.AsyncClient, repo: str, comment_id: int, event: str) -> None:
    """React to the triggering comment with 👍."""
    if event == "pull_request_review_comment":
        url = f"https://api.github.com/repos/{repo}/pulls/comments/{comment_id}/reactions"
    else:
        url = f"https://api.github.com/repos/{repo}/issues/comments/{comment_id}/reactions"

    await client.post(url, headers=GITHUB_HEADERS, json={"content": "+1"})


async def fetch_pr_comments(client: httpx.AsyncClient, repo: str, pr_number: int) -> str:
    """Fetch all review comments and issue comments from a PR, formatted as text."""
    review_url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}/comments"
    issue_url = f"https://api.github.com/repos/{repo}/issues/{pr_number}/comments"

    review_resp, issue_resp = await asyncio.gather(
        client.get(review_url, headers=GITHUB_HEADERS),
        client.get(issue_url, headers=GITHUB_HEADERS),
    )

    sections = []

    for c in review_resp.json():
        author = c["user"]["login"]
        path = c.get("path", "unknown file")
        line = c.get("line") or c.get("original_line", "")
        body = c["body"]
        sections.append(f"Review on `{path}` line {line} by @{author}:\n{body}")

    for c in issue_resp.json():
        author = c["user"]["login"]
        body = c["body"]
        sections.append(f"PR comment by @{author}:\n{body}")

    return "\n\n---\n\n".join(sections)


# ── Background task ───────────────────────────────────────────────────────────

async def process_learn_trigger(repo: str, pr_number: int, comment_id: int, event: str) -> None:
    """React to the comment, fetch all PR comments, run the review agent."""
    async with httpx.AsyncClient() as client:
        await add_thumbs_up(client, repo, comment_id, event)
        review_text = await fetch_pr_comments(client, repo, pr_number)

    logs = await asyncio.to_thread(run_from_text, review_text, TARGET_DIR)

    print(f"\n[webhook] PR #{pr_number} processed:")
    for entry in logs:
        print(f"  • {entry}")


# ── Webhook endpoint ──────────────────────────────────────────────────────────

@app.post("/webhook/github")
async def github_webhook(request: Request, background_tasks: BackgroundTasks):
    payload = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")

    if not is_valid_signature(payload, signature):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    event = request.headers.get("X-GitHub-Event", "")
    data = await request.json()

    # Only handle PR review comments and general PR comments
    if event not in ("pull_request_review_comment", "issue_comment"):
        return {"status": "ignored", "reason": f"unhandled event: {event}"}

    comment = data.get("comment", {})
    body = comment.get("body", "")

    if LEARN_TRIGGER not in body:
        return {"status": "ignored", "reason": f"no {LEARN_TRIGGER} trigger found"}

    repo = data["repository"]["full_name"]
    comment_id = comment["id"]
    pr_number = (
        data.get("pull_request", {}).get("number")
        or data.get("issue", {}).get("number")
    )

    if not pr_number:
        return {"status": "ignored", "reason": "could not determine PR number"}

    background_tasks.add_task(process_learn_trigger, repo, pr_number, comment_id, event)

    return {"status": "processing", "pr": pr_number, "repo": repo}


@app.get("/health")
async def health():
    return {"status": "ok"}
