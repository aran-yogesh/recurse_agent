"""Tests for agent.route_after_reflect — pure routing logic, no LLM."""
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# agent.py instantiates ChatAnthropic at import time, which requires an API key.
# Patch ChatAnthropic before the import so tests don't need network/credentials.
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-not-used")


@pytest.fixture(scope="module")
def agent_module():
    with patch("langchain_anthropic.ChatAnthropic", MagicMock()):
        if "agent" in sys.modules:
            del sys.modules["agent"]
        import agent
        return agent


def _state(needs_revision: bool, iteration: int, has_reflection: bool = True) -> dict:
    reflection = None
    if has_reflection:
        reflection = MagicMock()
        reflection.needs_revision = needs_revision
        reflection.focus_areas = ["naming"]
    return {"reflection": reflection, "iteration": iteration}


class TestRouteAfterReflect:
    def test_routes_to_revise_when_needed_and_under_limit(self, agent_module):
        result = agent_module.route_after_reflect(_state(True, 1))
        assert result == "revise"

    def test_routes_to_finalize_when_not_needed(self, agent_module):
        result = agent_module.route_after_reflect(_state(False, 1))
        assert result == "finalize"

    def test_routes_to_finalize_at_iteration_limit(self, agent_module):
        # MAX_ITERATIONS = 3; at iteration == 3, we should stop revising
        result = agent_module.route_after_reflect(_state(True, agent_module.MAX_ITERATIONS))
        assert result == "finalize"

    def test_routes_to_finalize_with_no_reflection(self, agent_module):
        result = agent_module.route_after_reflect(_state(False, 0, has_reflection=False))
        assert result == "finalize"

    @pytest.mark.parametrize("iteration", [0, 1, 2])
    def test_revises_when_below_max(self, agent_module, iteration):
        result = agent_module.route_after_reflect(_state(True, iteration))
        assert result == "revise"
