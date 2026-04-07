package messagessplitterprocessor

import (
	"context"
	"encoding/json"

	"go.opentelemetry.io/collector/consumer"
	"go.opentelemetry.io/collector/pdata/ptrace"
)

const (
	allMessagesJSON = "all_messages_json"
	genAIInputMsgs  = "gen_ai.input.messages"
	genAIOutputMsgs = "gen_ai.output.messages"
)

var (
	inputRoles  = map[string]bool{"user": true, "system": true, "tool": true}
	outputRoles = map[string]bool{"assistant": true}
)

type messageSplitter struct{ next consumer.Traces }

func newMessageSplitter(next consumer.Traces) *messageSplitter {
	return &messageSplitter{next: next}
}

// ConsumeTraces mutates spans in-place and returns the modified traces.
// The processorhelper framework handles calling next.ConsumeTraces.
func (p *messageSplitter) ConsumeTraces(
	_ context.Context,
	td ptrace.Traces,
) (ptrace.Traces, error) {
	for i := range td.ResourceSpans().Len() {
		for j := range td.ResourceSpans().At(i).ScopeSpans().Len() {
			ss := td.ResourceSpans().At(i).ScopeSpans().At(j).Spans()
			for k := range ss.Len() {
				p.processSpan(ss.At(k))
			}
		}
	}
	return td, nil
}

func (p *messageSplitter) processSpan(span ptrace.Span) {
	attrs := span.Attributes()
	raw, ok := attrs.Get(allMessagesJSON)
	if !ok {
		return
	}

	var messages []map[string]any
	if err := json.Unmarshal([]byte(raw.Str()), &messages); err != nil {
		return
	}

	var inputs, outputs []map[string]any
	for _, m := range messages {
		role, _ := m["role"].(string)
		switch {
		case inputRoles[role]:
			inputs = append(inputs, m)
		case outputRoles[role]:
			outputs = append(outputs, m)
		}
	}

	if b, err := json.Marshal(inputs); err == nil && len(inputs) > 0 {
		attrs.PutStr(genAIInputMsgs, string(b))
	}
	if b, err := json.Marshal(outputs); err == nil && len(outputs) > 0 {
		attrs.PutStr(genAIOutputMsgs, string(b))
	}

	attrs.Remove(allMessagesJSON)
}
