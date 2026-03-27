"""OpenTelemetry setup with GenAI Semantic Conventions for Honeycomb."""

from __future__ import annotations

import os

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
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
        # Return a no-op provider if telemetry is disabled
        provider = TracerProvider()
        trace.set_tracer_provider(provider)
        return provider

    service_name = os.getenv("OTEL_SERVICE_NAME", "code-reviewer")
    honeycomb_api_key = os.getenv("HONEYCOMB_API_KEY", "")
    endpoint = os.getenv(
        "OTEL_EXPORTER_OTLP_ENDPOINT", "https://api.honeycomb.io"
    )
    # Ensure the endpoint has a scheme — the parent shell (e.g. Claude Code)
    # may set OTEL_EXPORTER_OTLP_ENDPOINT without https://.
    if endpoint and not endpoint.startswith(("http://", "https://")):
        endpoint = f"https://{endpoint}"
    # Strip port 443 if present (redundant for https)
    endpoint = endpoint.rstrip("/").replace(":443", "")

    resource = Resource.create({"service.name": service_name})

    provider = TracerProvider(resource=resource)

    if honeycomb_api_key:
        exporter = OTLPSpanExporter(
            endpoint=f"{endpoint}/v1/traces",
            headers={"x-honeycomb-team": honeycomb_api_key},
        )
        provider.add_span_processor(BatchSpanProcessor(exporter))

    # Ensure the OTLP env vars reflect our programmatic config so that
    # Agent.instrument_all() doesn't inherit a schemeless endpoint from
    # the parent shell (e.g. Claude Code sets api.honeycomb.io:443).
    if honeycomb_api_key:
        os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = endpoint
        os.environ["OTEL_EXPORTER_OTLP_HEADERS"] = f"x-honeycomb-team={honeycomb_api_key}"

    trace.set_tracer_provider(provider)

    # Instrument all pydantic-ai agents with OpenTelemetry
    Agent.instrument_all()

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
