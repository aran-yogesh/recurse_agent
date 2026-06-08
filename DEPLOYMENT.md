# Deployment Checklist

This checklist covers deploying the `review-agent` Python service. It has three runtime entry points:

| Entry point | Purpose | Command |
|---|---|---|
| `main.py` | One-shot CLI (screenshot or text) | `uv run python main.py ...` |
| `webhook.py` | FastAPI webhook receiver | `uv run uvicorn webhook:app` |
| `poller.py` | GitHub events poller (no webhook needed) | `uv run python poller.py` |
| LangGraph server | Hosted graph via `langgraph.json` | `uv run langgraph dev` |

Pick **one** server mode (webhook OR poller OR LangGraph) per deployment.

---

## 1. Pre-deploy

- [ ] `make check` passes (lint + typecheck + tests)
- [ ] `make test` reports 0 failures
- [ ] No uncommitted changes; release tag/commit identified
- [ ] `uv.lock` matches `pyproject.toml` (`uv lock --check`)
- [ ] Python 3.14+ available on the target host
- [ ] `uv` available on target host (or vendored via container)
- [ ] Secrets store / env file location decided (never commit `.env`)

## 2. Environment variables

| Variable | Required by | Notes |
|---|---|---|
| `ANTHROPIC_API_KEY` | all entry points | LLM credential — keep secret |
| `TARGET_DIR` | all (optional) | Where `memory.md` / `skills.md` / `agents.md` get written. Defaults to `.` |
| `GITHUB_TOKEN` | webhook, poller | Needs `repo` scope to read PR comments + add reactions |
| `GITHUB_WEBHOOK_SECRET` | webhook only | Shared secret for HMAC signature verification |
| `GITHUB_USERNAME` | poller only | Account whose `/events` feed gets watched |

- [ ] All required vars set for the chosen entry point
- [ ] Verify `ANTHROPIC_API_KEY` works: `uv run python -c "from langchain_anthropic import ChatAnthropic; ChatAnthropic(model='claude-opus-4-6').invoke('hi')"`
- [ ] Verify `GITHUB_TOKEN` works: `curl -H "Authorization: Bearer $GITHUB_TOKEN" https://api.github.com/user`
- [ ] `TARGET_DIR` exists and is writable by the service user

## 3. Install

- [ ] `uv sync` (production only, no dev group) — or `uv sync --group dev` if running tests on box
- [ ] Confirm Python version: `uv run python --version` shows 3.14.x
- [ ] Confirm import works: `uv run python -c "import agent; print('ok')"`

## 4. Networking & process

### Webhook mode
- [ ] Public HTTPS endpoint configured (nginx / Caddy / cloud LB)
- [ ] GitHub webhook registered at `https://<host>/webhook/github`
- [ ] Webhook events subscribed: `pull_request_review_comment`, `issue_comment`
- [ ] Webhook content type: `application/json`
- [ ] Secret in GitHub matches `GITHUB_WEBHOOK_SECRET`
- [ ] Process supervisor configured (systemd / Docker restart / k8s Deployment)
- [ ] Health check wired to `GET /health` returning `{"status": "ok"}`

### Poller mode
- [ ] Process supervisor configured (long-running async task)
- [ ] Restart-on-failure policy set
- [ ] Note GitHub API rate limit: 5000/hr authenticated — polling every 30s is ~120 req/hr (safe)

## 5. Smoke tests (post-deploy)

- [ ] Process is running (`systemctl status` / `docker ps` / `kubectl get pods`)
- [ ] Logs show clean startup with no tracebacks
- [ ] **Webhook**: `curl https://<host>/health` returns 200
- [ ] **Webhook**: post a real `@learn` comment on a test PR → verify 👍 reaction appears within ~5s
- [ ] **Poller**: comment `@learn` on a PR → next poll cycle picks it up (check logs)
- [ ] After a trigger fires, confirm `memory.md`, `skills.md`, `agents.md`, `CLAUDE.md` exist in `TARGET_DIR` with new content

## 6. Observability

- [ ] Log output goes somewhere persistent (file, journald, log aggregator)
- [ ] Alert on process restarts / crash loops
- [ ] Alert on Anthropic 4xx/5xx spikes (LLM failures)
- [ ] Alert on GitHub 401 (token expired) / 403 (rate-limited)
- [ ] Cost monitor for Anthropic API spend (every `@learn` fires 5+ LLM calls)

## 7. Rollback

- [ ] Previous version tagged in git
- [ ] Rollback command documented: `git checkout <prev-tag> && uv sync && systemctl restart review-agent`
- [ ] `memory.md` / `skills.md` / `agents.md` in `TARGET_DIR` are not under source control — rollback does **not** restore them. Back them up separately if needed.

## 8. Security

- [ ] `.env` not committed (already in `.gitignore`)
- [ ] Secrets injected via env, not baked into image
- [ ] `GITHUB_WEBHOOK_SECRET` is random ≥32 bytes
- [ ] HMAC signature verification confirmed working (sign + send a payload; tamper one byte; expect 401)
- [ ] HTTPS only — never expose webhook over plain HTTP
- [ ] `GITHUB_TOKEN` scoped to minimum required perms (read repo, write reactions)
- [ ] Anthropic key rotation procedure documented

---

## Quick deploy commands

```bash
# Production install
uv sync --no-dev

# Webhook server (behind reverse proxy)
uv run uvicorn webhook:app --host 0.0.0.0 --port 8000

# Poller
uv run python poller.py

# CI gate
make check
```
