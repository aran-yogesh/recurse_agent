import json
import operator
from datetime import datetime
from pathlib import Path
from typing import Annotated, TypedDict, cast

from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic

load_dotenv()
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from prompts import (
    AGENTS_SYSTEM,
    EXTRACT_SYSTEM,
    EXTRACT_USER,
    MEMORY_SYSTEM,
    REFLECT_SYSTEM,
    REVISE_SYSTEM,
    SKILLS_SYSTEM,
    agents_update_prompt,
    extract_from_text_prompt,
    memory_update_prompt,
    reflect_prompt,
    revise_prompt,
    skills_update_prompt,
)
from utils.vision import encode_image
from utils.writer import ensure_claude_md, read_md, write_md

MAX_ITERATIONS = 3

_llm = ChatAnthropic(model="claude-opus-4-6", temperature=0)  # type: ignore[call-arg]


# ── Pydantic models ───────────────────────────────────────────────────────────

class ReviewIssue(BaseModel):
    comment: str = Field(description="Exact reviewer comment")
    pattern: str = Field(description="General rule being violated")
    category: str = Field(
        description="One of: error_handling | naming | structure | performance | security | style | testing | documentation | other"
    )
    severity: str = Field(description="One of: critical | major | minor")
    bad_example: str | None = Field(default=None, description="Bad code snippet if visible")
    good_example: str | None = Field(default=None, description="Suggested fix if visible")


class ExtractedFeedback(BaseModel):
    issues: list[ReviewIssue]
    overall_theme: str = Field(description="One-sentence summary of the main issues")


class ReflectionResult(BaseModel):
    needs_revision: bool = Field(description="Whether the files need another revision pass")
    reasoning: str = Field(description="Why revision is or isn't needed")
    focus_areas: list[str] = Field(
        default_factory=list,
        description="Specific issues to fix (empty if no revision needed)",
    )


# ── State ─────────────────────────────────────────────────────────────────────

class AgentState(TypedDict):
    image_path: str | None       # set when input is a screenshot
    review_text: str | None      # set when input is raw PR comment text
    target_dir: str
    feedback: ExtractedFeedback | None
    iteration: int
    reflection: ReflectionResult | None
    logs: Annotated[list[str], operator.add]


# ── Nodes ─────────────────────────────────────────────────────────────────────

def extract_feedback(state: AgentState) -> dict:
    """Parse review input into structured feedback. Handles both screenshot and raw text."""
    structured_llm = _llm.with_structured_output(ExtractedFeedback)

    review_text = state.get("review_text")
    image_path = state.get("image_path")

    if review_text:
        # Text mode: raw PR comments from GitHub webhook
        message = HumanMessage(content=extract_from_text_prompt(review_text))
        source_label = "github-pr"
    else:
        # Vision mode: screenshot
        assert image_path is not None, "extract_feedback requires either review_text or image_path"
        image_data, media_type = encode_image(image_path)
        message = HumanMessage(content=[
            {
                "type": "image_url",
                "image_url": {"url": f"data:{media_type};base64,{image_data}"},
            },
            {"type": "text", "text": EXTRACT_USER},
        ])
        source_label = Path(image_path).name

    feedback = cast(ExtractedFeedback, structured_llm.invoke(
        [SystemMessage(content=EXTRACT_SYSTEM), message]
    ))

    return {
        "feedback": feedback,
        "logs": [f"[{source_label}] Extracted {len(feedback.issues)} issue(s): {feedback.overall_theme}"],
    }


def update_files(state: AgentState) -> dict:
    """Write memory.md, skills.md, and agents.md from extracted feedback."""
    target = state["target_dir"]
    feedback = state["feedback"]
    assert feedback is not None, "update_files runs after extract_feedback; feedback must be set"
    date = datetime.now().strftime("%Y-%m-%d")
    image_path = state.get("image_path")
    image_name = Path(image_path).name if image_path else "github-pr"
    feedback_json = feedback.model_dump_json(indent=2)
    issues_json = json.dumps([i.model_dump() for i in feedback.issues], indent=2)

    def llm_call(system: str, user: str) -> str:
        return cast(str, _llm.invoke([SystemMessage(content=system), HumanMessage(content=user)]).content)

    write_md(target, "memory.md", llm_call(
        MEMORY_SYSTEM,
        memory_update_prompt(read_md(target, "memory.md"), date, image_name, feedback_json),
    ))

    write_md(target, "skills.md", llm_call(
        SKILLS_SYSTEM,
        skills_update_prompt(read_md(target, "skills.md"), issues_json),
    ))

    write_md(target, "agents.md", llm_call(
        AGENTS_SYSTEM,
        agents_update_prompt(read_md(target, "agents.md"), feedback_json),
    ))

    return {"logs": ["Updated memory.md, skills.md, agents.md"]}


def reflect(state: AgentState) -> dict:
    """Read all three files and decide if a revision pass is needed."""
    target = state["target_dir"]
    iteration = state["iteration"] + 1
    feedback = state["feedback"]
    assert feedback is not None, "reflect runs after extract_feedback; feedback must be set"

    result = cast(ReflectionResult, _llm.with_structured_output(ReflectionResult).invoke([
        SystemMessage(content=REFLECT_SYSTEM),
        HumanMessage(content=reflect_prompt(
            read_md(target, "memory.md"),
            read_md(target, "skills.md"),
            read_md(target, "agents.md"),
            feedback.overall_theme,
        )),
    ]))

    return {
        "reflection": result,
        "iteration": iteration,
        "logs": [
            f"Reflection #{iteration}: needs_revision={result.needs_revision} — {result.reasoning}"
        ],
    }


def revise(state: AgentState) -> dict:
    """Apply targeted revisions to all files based on reflection feedback."""
    target = state["target_dir"]
    reflection = state["reflection"]
    assert reflection is not None, "revise runs after reflect; reflection must be set"
    focus = reflection.focus_areas

    for file_name in ("memory.md", "skills.md", "agents.md"):
        revised = cast(str, _llm.invoke([
            SystemMessage(content=REVISE_SYSTEM),
            HumanMessage(content=revise_prompt(file_name, read_md(target, file_name), focus)),
        ]).content)
        write_md(target, file_name, revised)

    return {"logs": [f"Revised files — focus: {'; '.join(focus)}"]}


def finalize(state: AgentState) -> dict:
    """Ensure CLAUDE.md imports the pattern files."""
    ensure_claude_md(state["target_dir"])
    return {"logs": ["Finalized — CLAUDE.md ready"]}


# ── Routing ───────────────────────────────────────────────────────────────────

def route_after_reflect(state: AgentState) -> str:
    """Route to revise if files need work and we're under the iteration limit."""
    if (
        state["reflection"]
        and state["reflection"].needs_revision
        and state["iteration"] < MAX_ITERATIONS
    ):
        return "revise"
    return "finalize"


# ── Graph ─────────────────────────────────────────────────────────────────────

def build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("extract_feedback", extract_feedback)
    graph.add_node("update_files", update_files)
    graph.add_node("reflect", reflect)
    graph.add_node("revise", revise)
    graph.add_node("finalize", finalize)

    graph.add_edge(START, "extract_feedback")
    graph.add_edge("extract_feedback", "update_files")
    graph.add_edge("update_files", "reflect")
    graph.add_conditional_edges(
        "reflect",
        route_after_reflect,
        {"revise": "revise", "finalize": "finalize"},
    )
    graph.add_edge("revise", "reflect")
    graph.add_edge("finalize", END)

    return graph.compile()


# Compiled graph exposed for LangGraph server (langgraph.json points here)
graph = build_graph()


def run(image_path: str, target_dir: str) -> list[str]:
    """Run the agent from a screenshot. Returns the execution log."""
    initial_state: AgentState = {
        "image_path": image_path,
        "review_text": None,
        "target_dir": target_dir,
        "feedback": None,
        "iteration": 0,
        "reflection": None,
        "logs": [],
    }
    final_state = build_graph().invoke(initial_state)
    return final_state["logs"]


def run_from_text(review_text: str, target_dir: str) -> list[str]:
    """Run the agent from raw PR comment text. Returns the execution log."""
    initial_state: AgentState = {
        "image_path": None,
        "review_text": review_text,
        "target_dir": target_dir,
        "feedback": None,
        "iteration": 0,
        "reflection": None,
        "logs": [],
    }
    final_state = build_graph().invoke(initial_state)
    return final_state["logs"]
