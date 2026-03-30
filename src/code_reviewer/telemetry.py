"""OpenTelemetry setup with GenAI Semantic Conventions for Honeycomb."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

from opentelemetry import trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.context import Context
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, Span, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from pydantic_ai import Agent


# GenAI Semantic Convention attribute keys (v1.40.0)
GEN_AI_SYSTEM = "gen_ai.system"
GEN_AI_OPERATION_NAME = "gen_ai.operation.name"
GEN_AI_REQUEST_MODEL = "gen_ai.request.model"
GEN_AI_RESPONSE_MODEL = "gen_ai.response.model"
GEN_AI_REQUEST_MAX_TOKENS = "gen_ai.request.max_tokens"
GEN_AI_REQUEST_TEMPERATURE = "gen_ai.request.temperature"
GEN_AI_USAGE_INPUT_TOKENS = "gen_ai.usage.input_tokens"
GEN_AI_USAGE_OUTPUT_TOKENS = "gen_ai.usage.output_tokens"
GEN_AI_RESPONSE_ID = "gen_ai.response.id"
GEN_AI_RESPONSE_FINISH_REASONS = "gen_ai.response.finish_reasons"

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
        "source_attribute": "all_messages_json",
        "input_attribute": "gen_ai.input.messages",
        "output_attribute": "gen_ai.output.messages",
        "input_roles": ["user"],
        "output_roles": ["assistant"],
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

    def __init__(self, config: dict | None = None) -> None:
        if config is None:
            config = _load_normalizer_config()
        self._enabled = config.get("enabled", True)
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
        self._msg_input_roles = set(msg_cfg.get("input_roles", ["user"]))
        self._msg_output_roles = set(msg_cfg.get("output_roles", ["assistant"]))

    def on_start(self, span: Span, parent_context: Context | None = None) -> None:
        if not self._enabled or not self._op_name_enabled:
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
            self._unpack_messages(attrs)
        except TypeError:
            logger.debug("on_end: span '%s' attributes are frozen, skipping mutations", span.name)

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
        input_msgs = [m for m in messages if m.get("role") in self._msg_input_roles]
        output_msgs = [m for m in messages if m.get("role") in self._msg_output_roles]
        if input_msgs:
            attrs[self._msg_input_attr] = json.dumps(input_msgs)
        if output_msgs:
            attrs[self._msg_output_attr] = json.dumps(output_msgs)
        del attrs[self._msg_source]

    def shutdown(self) -> None:
        pass

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True


def _is_truthy(val: str | None) -> bool:
    return val is not None and val.lower() in ("true", "1", "yes")


def log_prompts_enabled() -> bool:
    """Check if user prompt logging is enabled."""
    return _is_truthy(os.getenv("OTEL_LOG_USER_PROMPTS"))


def agent_status_logging_enabled() -> bool:
    """Check if agent status logging is enabled."""
    return _is_truthy(os.getenv("AGENT_LOG_STATUS"))


def setup_telemetry() -> TracerProvider:
    """Configure OpenTelemetry with OTLP export to Honeycomb.

    Respects environment variables:
    - HONEYCOMB_API_KEY: Required for Honeycomb export
    - OTEL_SERVICE_NAME: Service name (default: code-reviewer)
    - OTEL_EXPORTER_OTLP_ENDPOINT: OTLP endpoint (default: https://api.honeycomb.io)
    - CLAUDE_CODE_ENABLE_TELEMETRY: Master telemetry toggle
    - AGENT_LOG_STATUS: Log agent status transitions as span events
    - OTEL_LOG_USER_PROMPTS: Log user prompts as span events
    """
    if not _is_truthy(os.getenv("CLAUDE_CODE_ENABLE_TELEMETRY", "true")):
        logger.debug("Telemetry disabled via CLAUDE_CODE_ENABLE_TELEMETRY, returning no-op provider")
        provider = TracerProvider()
        trace.set_tracer_provider(provider)
        return provider

    service_name = os.getenv("OTEL_SERVICE_NAME", "code-reviewer")
    honeycomb_api_key = os.getenv("HONEYCOMB_API_KEY", "")
    endpoint = os.getenv(
        "OTEL_EXPORTER_OTLP_ENDPOINT", "https://api.honeycomb.io"
    )
    logger.debug("Telemetry config: service=%s, endpoint=%s, api_key=%s",
                 service_name, endpoint, "set" if honeycomb_api_key else "NOT SET")

    # Ensure the endpoint has a scheme — the parent shell (e.g. Claude Code)
    # may set OTEL_EXPORTER_OTLP_ENDPOINT without https://.
    if endpoint and not endpoint.startswith(("http://", "https://")):
        logger.debug("Adding https:// scheme to endpoint '%s'", endpoint)
        endpoint = f"https://{endpoint}"
    # Strip port 443 if present (redundant for https)
    endpoint = endpoint.rstrip("/").replace(":443", "")
    logger.debug("Final OTLP endpoint: %s", endpoint)

    resource = Resource.create({"service.name": service_name})

    provider = TracerProvider(resource=resource)

    # Add the GenAI operation name processor so agent/tool spans
    # get the required gen_ai.operation.name attribute.
    logger.debug("Adding PydanticTelemetryNormalizerProcessor")
    provider.add_span_processor(PydanticTelemetryNormalizerProcessor())

    if honeycomb_api_key:
        logger.debug("Configuring OTLP exporter -> %s/v1/traces", endpoint)
        exporter = OTLPSpanExporter(
            endpoint=f"{endpoint}/v1/traces",
            headers={"x-honeycomb-team": honeycomb_api_key},
        )
        provider.add_span_processor(BatchSpanProcessor(exporter))
    else:
        logger.debug("No HONEYCOMB_API_KEY set, skipping OTLP exporter")

    # --- OTel Logs Bridge ---
    # Bridges Python logging → OTel log records with trace/span context.
    # Log records emitted within an active span automatically carry
    # the trace_id and span_id, making them searchable alongside traces.
    logger_provider = LoggerProvider(resource=resource)
    if honeycomb_api_key:
        logger.debug("Configuring OTLP log exporter -> %s/v1/logs", endpoint)
        log_exporter = OTLPLogExporter(
            endpoint=f"{endpoint}/v1/logs",
            headers={"x-honeycomb-team": honeycomb_api_key},
        )
        logger_provider.add_log_record_processor(BatchLogRecordProcessor(log_exporter))
    set_logger_provider(logger_provider)

    # Attach the OTel handler to the root logger so all Python log calls
    # (including our logger.debug() calls) become OTel log records.
    otel_handler = LoggingHandler(level=logging.WARNING, logger_provider=logger_provider)
    logging.getLogger().addHandler(otel_handler)
    logger.debug("OTel Logs Bridge attached to root logger")

    # Ensure the OTLP env vars reflect our programmatic config so that
    # Agent.instrument_all() doesn't inherit a schemeless endpoint from
    # the parent shell (e.g. Claude Code sets api.honeycomb.io:443).
    if honeycomb_api_key:
        os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = endpoint
        os.environ["OTEL_EXPORTER_OTLP_HEADERS"] = f"x-honeycomb-team={honeycomb_api_key}"

    trace.set_tracer_provider(provider)

    logger.debug("Instrumenting all pydantic-ai agents")
    Agent.instrument_all()

    logger.debug("Telemetry setup complete")
    return provider


def get_tracer(name: str = "code-reviewer") -> trace.Tracer:
    """Get a tracer instance."""
    return trace.get_tracer(name)


def genai_span_attrs(
    model: str = "claude-sonnet-4-20250514",
    operation: str = "chat",
    temperature: float = 0.0,
    max_tokens: int = 4096,
) -> dict[str, str | float | int]:
    """Return standard GenAI semantic convention attributes for a span."""
    return {
        GEN_AI_SYSTEM: "anthropic",
        GEN_AI_OPERATION_NAME: operation,
        GEN_AI_REQUEST_MODEL: model,
        GEN_AI_REQUEST_TEMPERATURE: temperature,
        GEN_AI_REQUEST_MAX_TOKENS: max_tokens,
    }


def set_genai_response_attrs(
    span: trace.Span,
    *,
    model: str,
    input_tokens: int,
    output_tokens: int,
    response_id: str = "",
    finish_reason: str = "stop",
) -> None:
    """Set GenAI response attributes on a span."""
    span.set_attribute(GEN_AI_RESPONSE_MODEL, model)
    span.set_attribute(GEN_AI_USAGE_INPUT_TOKENS, input_tokens)
    span.set_attribute(GEN_AI_USAGE_OUTPUT_TOKENS, output_tokens)
    if response_id:
        span.set_attribute(GEN_AI_RESPONSE_ID, response_id)
    span.set_attribute(GEN_AI_RESPONSE_FINISH_REASONS, [finish_reason])
