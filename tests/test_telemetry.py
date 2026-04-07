"""Tests for telemetry setup and helpers."""

import json
from unittest.mock import patch

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from code_reviewer.telemetry import (
    GEN_AI_OPERATION_NAME,
    PydanticTelemetryNormalizerProcessor,
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


def _make_provider_and_exporter(config=None):
    """Helper to wire up a provider with the normalizer and an in-memory exporter."""
    provider = TracerProvider()
    provider.add_span_processor(PydanticTelemetryNormalizerProcessor(config))
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider, exporter


class TestPydanticTelemetryNormalizerProcessor:
    # --- operation name mapping (folded from GenAIOperationNameSpanProcessor) ---

    def test_sets_invoke_agent_operation_name(self):
        provider, exporter = _make_provider_and_exporter()
        tracer = provider.get_tracer("test")
        with tracer.start_as_current_span("invoke_agent my_agent"):
            pass
        spans = exporter.get_finished_spans()
        assert spans[0].attributes.get(GEN_AI_OPERATION_NAME) == "invoke_agent"
        provider.shutdown()

    def test_sets_execute_tool_operation_name(self):
        provider, exporter = _make_provider_and_exporter()
        tracer = provider.get_tracer("test")
        with tracer.start_as_current_span("execute_tool run_bandit"):
            pass
        spans = exporter.get_finished_spans()
        assert spans[0].attributes.get(GEN_AI_OPERATION_NAME) == "execute_tool"
        provider.shutdown()

    def test_does_not_set_for_other_spans(self):
        provider, exporter = _make_provider_and_exporter()
        tracer = provider.get_tracer("test")
        with tracer.start_as_current_span("review_pipeline"):
            pass
        spans = exporter.get_finished_spans()
        assert spans[0].attributes.get(GEN_AI_OPERATION_NAME) is None
        provider.shutdown()

    # --- attribute renaming ---

    def test_renames_gen_ai_attributes(self):
        provider, exporter = _make_provider_and_exporter()
        tracer = provider.get_tracer("test")
        with tracer.start_as_current_span("invoke_agent my_agent") as span:
            span.set_attribute("gen_ai.system", "anthropic")
            span.set_attribute("tool_response", "some result")
            span.set_attribute("tool_arguments", '{"arg": "val"}')
            span.set_attribute("agent_name", "security_agent")
        spans = exporter.get_finished_spans()
        attrs = spans[0].attributes
        assert attrs.get("gen_ai.tool.call.result") == "some result"
        assert attrs.get("gen_ai.tool.call.arguments") == '{"arg": "val"}'
        assert attrs.get("gen_ai.agent.name") == "security_agent"
        # originals removed
        assert attrs.get("tool_response") is None
        assert attrs.get("tool_arguments") is None
        assert attrs.get("agent_name") is None
        provider.shutdown()

    def test_skips_rename_without_gen_ai_attrs(self):
        provider, exporter = _make_provider_and_exporter()
        tracer = provider.get_tracer("test")
        with tracer.start_as_current_span("some_span") as span:
            span.set_attribute("tool_response", "should stay")
        spans = exporter.get_finished_spans()
        attrs = spans[0].attributes
        # no gen_ai.* attrs on span, so renaming is skipped
        assert attrs.get("tool_response") == "should stay"
        assert attrs.get("gen_ai.tool.call.result") is None
        provider.shutdown()

    # --- message unpacking ---

    def test_unpacks_messages_by_role(self):
        packed = json.dumps([
            {"role": "user", "parts": [{"type": "text", "content": "hello"}]},
            {"role": "assistant", "parts": [{"type": "text", "content": "hi"}],
             "finish_reason": "stop"},
            {"role": "user", "parts": [{"type": "tool_call_response", "id": "t1",
                                        "name": "foo", "result": "bar"}]},
        ])
        provider, exporter = _make_provider_and_exporter()
        tracer = provider.get_tracer("test")
        with tracer.start_as_current_span("invoke_agent review") as span:
            span.set_attribute("gen_ai.system", "anthropic")
            span.set_attribute("all_messages_json", packed)
        spans = exporter.get_finished_spans()
        attrs = spans[0].attributes

        input_msgs = json.loads(attrs["gen_ai.input.messages"])
        output_msgs = json.loads(attrs["gen_ai.output.messages"])
        assert len(input_msgs) == 2
        assert all(m["role"] == "user" for m in input_msgs)
        assert len(output_msgs) == 1
        assert output_msgs[0]["role"] == "assistant"
        # source attribute removed
        assert attrs.get("all_messages_json") is None
        provider.shutdown()

    def test_skips_unpack_when_source_missing(self):
        provider, exporter = _make_provider_and_exporter()
        tracer = provider.get_tracer("test")
        with tracer.start_as_current_span("invoke_agent x") as span:
            span.set_attribute("gen_ai.system", "anthropic")
        spans = exporter.get_finished_spans()
        attrs = spans[0].attributes
        assert attrs.get("gen_ai.input.messages") is None
        assert attrs.get("gen_ai.output.messages") is None
        provider.shutdown()

    # --- global and per-feature disable flags ---

    def test_global_disable(self):
        config = {"enabled": False}
        provider, exporter = _make_provider_and_exporter(config)
        tracer = provider.get_tracer("test")
        with tracer.start_as_current_span("invoke_agent my_agent") as span:
            span.set_attribute("gen_ai.system", "anthropic")
            span.set_attribute("tool_response", "keep me")
        spans = exporter.get_finished_spans()
        attrs = spans[0].attributes
        assert attrs.get(GEN_AI_OPERATION_NAME) is None
        assert attrs.get("tool_response") == "keep me"
        provider.shutdown()

    def test_disable_operation_name_only(self):
        config = {
            "enabled": True,
            "operation_name_mapping": {"enabled": False},
            "attribute_renaming": {
                "enabled": True,
                "mappings": {"tool_response": "gen_ai.tool.call.result"},
            },
        }
        provider, exporter = _make_provider_and_exporter(config)
        tracer = provider.get_tracer("test")
        with tracer.start_as_current_span("invoke_agent x") as span:
            span.set_attribute("gen_ai.system", "anthropic")
            span.set_attribute("tool_response", "val")
        spans = exporter.get_finished_spans()
        attrs = spans[0].attributes
        assert attrs.get(GEN_AI_OPERATION_NAME) is None
        assert attrs.get("gen_ai.tool.call.result") == "val"
        provider.shutdown()

    def test_disable_attribute_renaming_only(self):
        config = {
            "enabled": True,
            "operation_name_mapping": {
                "enabled": True,
                "prefixes": {"invoke_agent": "invoke_agent"},
            },
            "attribute_renaming": {"enabled": False},
        }
        provider, exporter = _make_provider_and_exporter(config)
        tracer = provider.get_tracer("test")
        with tracer.start_as_current_span("invoke_agent x") as span:
            span.set_attribute("gen_ai.system", "anthropic")
            span.set_attribute("tool_response", "keep")
        spans = exporter.get_finished_spans()
        attrs = spans[0].attributes
        assert attrs.get(GEN_AI_OPERATION_NAME) == "invoke_agent"
        assert attrs.get("tool_response") == "keep"
        assert attrs.get("gen_ai.tool.call.result") is None
        provider.shutdown()

    def test_disable_message_unpacking_only(self):
        packed = json.dumps([{"role": "user", "parts": []}])
        config = {
            "enabled": True,
            "message_unpacking": {"enabled": False},
        }
        provider, exporter = _make_provider_and_exporter(config)
        tracer = provider.get_tracer("test")
        with tracer.start_as_current_span("invoke_agent x") as span:
            span.set_attribute("gen_ai.system", "anthropic")
            span.set_attribute("all_messages_json", packed)
        spans = exporter.get_finished_spans()
        attrs = spans[0].attributes
        assert attrs.get("all_messages_json") == packed
        assert attrs.get("gen_ai.input.messages") is None
        provider.shutdown()


