

## Prerequisites

- **Python 3.14+**
- **[uv](https://docs.astral.sh/uv/getting-started/installation/)** — Python package manager
- **Node.js 18+** + **npm** — for the Electron UI
- An **Anthropic API key**

---

## Setup

### 1. Clone & install Python deps

```bash
git clone <repo-url>
cd recurse_agent
uv sync
```

### 2. Set environment variables

Create a `.env` file in the project root:

```env
ANTHROPIC_API_KEY=sk-ant-...
TARGET_DIR=/path/to/your/project   # optional — defaults to current dir
```

`TARGET_DIR` is the project whose `memory.md` / `skills.md` / `agents.md` get updated. If omitted, the agent writes files into the current directory.

### 3. Install Electron UI deps

```bash
cd electron-app
npm install
```

---

## Running

### Desktop UI (recommended)

```bash
cd electron-app
npm start
```

Opens a chat window. Paste screenshots, drag & drop images, or type review text directly. The sidebar shows live file contents and is editable.

### CLI — screenshot

```bash
uv run python main.py path/to/screenshot.png --dir /path/to/project
```

### CLI — text

```bash
uv run python main.py --text "variable names are not descriptive" --dir /path/to/project
```

`--dir` is optional; defaults to `.`.

---

## Output files

The agent writes/updates three files in `TARGET_DIR`:

| File | Contents |
|---|---|
| `memory.md` | Running log of every review session |
| `skills.md` | Coding patterns and rules extracted from reviews |
| `agents.md` | Pre-submit checklist and escalation gates |
| `CLAUDE.md` | Auto-generated — imports the three files above |

Add these to `.gitignore` if you don't want them committed:

```
CLAUDE.md
memory.md
skills.md
agents.md
```
