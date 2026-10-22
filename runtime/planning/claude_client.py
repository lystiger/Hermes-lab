"""Planner model client backed by the Claude CLI.

The goal-planned runtime needs a callable that turns the planning prompt into the JSON plan. This one
sends the prompt to `claude -p` with no tools, the chosen model and effort, and returns the reply text.
"""

import asyncio

from orchestrator.chat import CLAUDE_MODELS, EFFORT_LEVELS, ChatError, ClaudeChatProvider

PLANNER_TIMEOUT_SECONDS = 900
PLANNER_SYSTEM_PROMPT = (
    "You are the Hermes planner. Decompose the engineering goal into tasks, choosing each task's "
    "execution_role and dependencies yourself. Answer with only the JSON plan the prompt asks for: "
    "no prose and no code fences."
)


def claude_planner_client(model="claude-opus-5-5", effort="high", provider=None):
    """Returns an async model_client for GroundedPlanner. Raises ValueError for an unknown model or effort."""
    if model not in CLAUDE_MODELS:
        raise ValueError(f"planner model must be one of {', '.join(CLAUDE_MODELS)}")
    if effort is not None and effort not in EFFORT_LEVELS:
        raise ValueError(f"planner effort must be one of {', '.join(EFFORT_LEVELS)}")
    provider = provider or ClaudeChatProvider(timeout=PLANNER_TIMEOUT_SECONDS)

    async def client(prompt):
        try:
            reply = await asyncio.to_thread(
                provider.reply, PLANNER_SYSTEM_PROMPT, [{"role": "user", "content": prompt}], model, effort
            )
        except ChatError as exc:
            raise RuntimeError(f"planner model call failed: {exc}") from exc
        return reply.text

    return client
