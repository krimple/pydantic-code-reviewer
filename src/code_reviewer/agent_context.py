"""ContextVars for propagating the current agent ID and name to child spans.

Kept in a separate module to avoid circular imports between
telemetry.py and normalizer.py.
"""

from __future__ import annotations

from contextvars import ContextVar

# Each asyncio task gets its own copy, so parallel agents don't collide.
current_agent_id: ContextVar[str] = ContextVar("current_agent_id", default="")
current_agent_name: ContextVar[str] = ContextVar("current_agent_name", default="")
