"""Tests for telemetry setup and helpers."""

from unittest.mock import patch

from opentelemetry import trace

from code_reviewer.telemetry import (
    GEN_AI_OPERATION_NAME,
    GEN_AI_REQUEST_MODEL,
    GEN_AI_SYSTEM,
    genai_span_attrs,
    set_genai_response_attrs,
    setup_telemetry,
)


class TestSetupTelemetry:
    def test_setup_returns_provider(self):
        with patch.dict("os.environ", {"HONEYCOMB_API_KEY": ""}):
            provider = setup_telemetry()
            assert provider is not None
            provider.shutdown()

    def test_setup_with_api_key(self):
        with patch.dict(
            "os.environ",
            {
                "HONEYCOMB_API_KEY": "test-key",
                "OTEL_SERVICE_NAME": "test-service",
            },
        ):
            provider = setup_telemetry()
            assert provider is not None
            provider.shutdown()


class TestGenaiSpanAttrs:
    def test_default_attrs(self):
        attrs = genai_span_attrs()
        assert attrs[GEN_AI_SYSTEM] == "anthropic"
        assert attrs[GEN_AI_OPERATION_NAME] == "chat"
        assert attrs[GEN_AI_REQUEST_MODEL] == "claude-sonnet-4-20250514"

    def test_custom_attrs(self):
        attrs = genai_span_attrs(
            model="claude-opus-4-20250514",
            operation="text_completion",
            temperature=0.5,
            max_tokens=2048,
        )
        assert attrs[GEN_AI_REQUEST_MODEL] == "claude-opus-4-20250514"
        assert attrs[GEN_AI_OPERATION_NAME] == "text_completion"


class TestSetGenaiResponseAttrs:
    def test_sets_attributes(self):
        provider = setup_telemetry()
        tracer = trace.get_tracer("test")
        with tracer.start_as_current_span("test-span") as span:
            set_genai_response_attrs(
                span,
                model="claude-sonnet-4-20250514",
                input_tokens=100,
                output_tokens=50,
                response_id="resp-123",
                finish_reason="stop",
            )
        provider.shutdown()
