"""SpanProcessor that normalizes Pydantic AI telemetry to GenAI semantic conventions."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from opentelemetry.context import Context
from opentelemetry.sdk.trace import ReadableSpan, Span
from opentelemetry.sdk.trace.export import SpanProcessor

from opentelemetry.semconv._incubating.attributes.gen_ai_attributes import (
    GEN_AI_AGENT_ID,
    GEN_AI_AGENT_NAME,
    GEN_AI_CONVERSATION_ID,
)

from code_reviewer.agent_context import current_agent_id, current_agent_name

logger = logging.getLogger(__name__)

GEN_AI_OPERATION_NAME = "gen_ai.operation.name"

_DEFAULT_NORMALIZER_CONFIG: dict = {
    "enabled": True,
    "operation_name_mapping": {
        "enabled": True,
        "prefixes": {
            "invoke_agent": "invoke_agent",
            "agent run": "invoke_agent",
            "execute_tool": "execute_tool",
            "running tool": "execute_tool",
        },
    },
    "attribute_renaming": {
        "enabled": True,
        "mappings": {
            "tool_response": "gen_ai.tool.call.result",
            "tool_arguments": "gen_ai.tool.call.arguments",
            "agent_name": "gen_ai.agent.name",
        },
    },
    "message_unpacking": {
        "enabled": True,
        "source_attribute": "pydantic_ai.all_messages",
        "input_attribute": "gen_ai.input.messages",
        "output_attribute": "gen_ai.output.messages",
        "input_roles": ["system", "user", "tool"],
        "output_roles": ["assistant"],
        "part_kind_to_role": {
            "system-prompt": "system",
            "user-prompt": "user",
            "tool-return": "tool",
            "retry-prompt": "user",
            "text": "assistant",
            "tool-call": "assistant",
        },
    },
}


def _load_normalizer_config() -> dict:
    """Load normalizer config from pydantic-mappings.json, falling back to defaults."""
    config_path = Path(__file__).parent / "pydantic-mappings.json"
    if config_path.exists():
        logger.debug("Loading normalizer config from %s", config_path)
        with open(config_path) as f:
            return json.load(f)
    logger.debug("No pydantic-mappings.json found, using default normalizer config")
    return _DEFAULT_NORMALIZER_CONFIG


class PydanticTelemetryNormalizerProcessor(SpanProcessor):
    """SpanProcessor that normalizes Pydantic AI telemetry to GenAI semantic conventions.

    Combines three capabilities controlled by pydantic-mappings.json:
    1. Operation name mapping — sets gen_ai.operation.name from span name prefixes
    2. Attribute renaming — renames Pydantic-specific attrs to gen_ai conventions
    3. Message unpacking — splits packed conversation into input/output messages

    Attribute renaming and message unpacking only apply to spans that already
    carry at least one ``gen_ai.*`` attribute.
    """

    def __init__(self, config: dict | None = None, conversation_id: str = "") -> None:
        if config is None:
            config = _load_normalizer_config()
        self._conversation_id = conversation_id
        self._enabled = config.get("enabled", True)
        # Maps agent_id -> agent_name, populated on_start when both are available.
        self._agent_names: dict[str, str] = {}
        logger.debug("PydanticTelemetryNormalizerProcessor initialized (enabled=%s)", self._enabled)

        op_cfg = config.get("operation_name_mapping", {})
        self._op_name_enabled = op_cfg.get("enabled", True)
        self._op_name_prefixes: dict[str, str] = op_cfg.get("prefixes", {})

        rename_cfg = config.get("attribute_renaming", {})
        self._rename_enabled = rename_cfg.get("enabled", True)
        self._rename_mappings: dict[str, str] = rename_cfg.get("mappings", {})

        msg_cfg = config.get("message_unpacking", {})
        self._msg_enabled = msg_cfg.get("enabled", True)
        self._msg_source = msg_cfg.get("source_attribute", "all_messages_json")
        self._msg_input_attr = msg_cfg.get("input_attribute", "gen_ai.input.messages")
        self._msg_output_attr = msg_cfg.get("output_attribute", "gen_ai.output.messages")
        self._msg_input_roles = set(msg_cfg.get("input_roles", ["system", "user", "tool"]))
        self._msg_output_roles = set(msg_cfg.get("output_roles", ["assistant"]))
        self._part_kind_to_role: dict[str, str] = msg_cfg.get("part_kind_to_role", {
            "system-prompt": "system",
            "user-prompt": "user",
            "tool-return": "tool",
            "retry-prompt": "user",
            "text": "assistant",
            "tool-call": "assistant",
        })

    def on_start(self, span: Span, parent_context: Context | None = None) -> None:
        if not self._enabled:
            return
        if self._conversation_id:
            span.set_attribute(GEN_AI_CONVERSATION_ID, self._conversation_id)
        agent_id = current_agent_id.get()
        if agent_id:
            span.set_attribute(GEN_AI_AGENT_ID, agent_id)
        agent_name = current_agent_name.get()
        if agent_name:
            span.set_attribute(GEN_AI_AGENT_NAME, agent_name)
            if agent_id:
                self._agent_names[agent_id] = agent_name
        if not self._op_name_enabled:
            return
        name = span.name if hasattr(span, "name") else ""
        for prefix, operation in self._op_name_prefixes.items():
            if name.startswith(prefix):
                logger.debug("on_start: span '%s' matched prefix '%s' -> operation '%s'", name, prefix, operation)
                span.set_attribute(GEN_AI_OPERATION_NAME, operation)
                break
        else:
            logger.debug("on_start: span '%s' did not match any operation name prefix", name)

    def on_end(self, span: ReadableSpan) -> None:
        if not self._enabled:
            return
        attrs = getattr(span, "_attributes", None)
        if not attrs:
            logger.debug("on_end: span '%s' has no attributes, skipping", span.name)
            return
        if not any(str(k).startswith("gen_ai.") for k in attrs.keys()):
            logger.debug("on_end: span '%s' has no gen_ai.* attributes, skipping", span.name)
            return
        logger.debug("on_end: processing span '%s' with %d attributes", span.name, len(attrs))
        try:
            self._rename_attributes(attrs)
            self._backfill_agent_name(attrs)
            self._unpack_messages(attrs)
            self._drop_final_result(attrs)
        except TypeError:
            logger.debug("on_end: span '%s' attributes are frozen, skipping mutations", span.name)

    def _backfill_agent_name(self, attrs) -> None:
        """Set gen_ai.agent.name on spans that have gen_ai.agent.id but are missing the name.

        Pydantic AI natively sets gen_ai.agent.id on all child spans (tool calls,
        chat completions), but not gen_ai.agent.name.  We fill it in from the
        mapping built during on_start.
        """
        agent_id = attrs.get(GEN_AI_AGENT_ID)
        if agent_id and GEN_AI_AGENT_NAME not in attrs:
            name = self._agent_names.get(agent_id, agent_id)
            logger.debug("Backfilling gen_ai.agent.name='%s' from agent_id='%s'", name, agent_id)
            attrs[GEN_AI_AGENT_NAME] = name

    def _rename_attributes(self, attrs) -> None:
        if not self._rename_enabled:
            return
        for old_key, new_key in self._rename_mappings.items():
            if old_key in attrs:
                logger.debug("Renaming attribute '%s' -> '%s'", old_key, new_key)
                attrs[new_key] = attrs[old_key]
                del attrs[old_key]

    def _unpack_messages(self, attrs) -> None:
        if not self._msg_enabled:
            return
        if self._msg_source not in attrs:
            return
        logger.debug("Unpacking messages from '%s'", self._msg_source)
        raw = attrs[self._msg_source]
        try:
            messages = json.loads(raw) if isinstance(raw, str) else raw
        except (json.JSONDecodeError, TypeError):
            return
        if not isinstance(messages, list):
            return
        # If messages are already in OTel format (role/parts), use them directly;
        # otherwise normalize from pydantic_ai native format (kind/parts with part_kind).
        if messages and "role" in messages[0] and "parts" in messages[0]:
            normalized = messages
        else:
            normalized = self._normalize_messages(messages)
        input_msgs = [m for m in normalized if m.get("role") in self._msg_input_roles]
        output_msgs = [m for m in normalized if m.get("role") in self._msg_output_roles]
        if input_msgs:
            attrs[self._msg_input_attr] = json.dumps(input_msgs)
        if output_msgs:
            attrs[self._msg_output_attr] = json.dumps(output_msgs)
        del attrs[self._msg_source]

    def _drop_final_result(self, attrs) -> None:
        """Remove the final_result attribute set by pydantic_ai.

        This attribute contains the raw Pydantic model output, which is not
        in OTel GenAI format and duplicates information already captured in
        the conversation messages.
        """
        if "final_result" in attrs:
            logger.debug("Dropping final_result attribute")
            del attrs["final_result"]

    def _normalize_messages(self, messages: list) -> list:
        """Convert pydantic_ai native messages (kind/part_kind) to role/content format.

        Supports two formats:
        - Simple role-based: ``{"role": "user", "content": "..."}`` — passed through.
        - Pydantic AI native: ``{"kind": "request"/"response", "parts": [...]}``
          — each part is flattened into a separate ``{"role": ..., "content": ...}`` dict
          using the ``part_kind_to_role`` mapping.
        """
        normalized: list[dict] = []
        for msg in messages:
            if "role" in msg:
                normalized.append(msg)
            elif "kind" in msg and "parts" in msg:
                for part in msg["parts"]:
                    role = self._part_kind_to_role.get(part.get("part_kind", ""))
                    if role is None:
                        continue
                    entry: dict = {"role": role}
                    if "content" in part:
                        entry["content"] = part["content"]
                    if part.get("part_kind") == "tool-call":
                        entry["tool_name"] = part.get("tool_name", "")
                        entry["tool_call_id"] = part.get("tool_call_id", "")
                        if "args" in part:
                            entry["args"] = part["args"]
                    elif part.get("part_kind") == "tool-return":
                        entry["tool_name"] = part.get("tool_name", "")
                        entry["tool_call_id"] = part.get("tool_call_id", "")
                    normalized.append(entry)
        return normalized

    def shutdown(self) -> None:
        pass

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True
