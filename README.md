# Code Reviewer

AI-powered code review application using Pydantic AI agents with OpenTelemetry instrumentation.

## Overview

Code Reviewer takes a GitHub repository URL, clones it, and runs three parallel review workstreams:

1. **Security Review** - Static analysis (bandit), dependency vulnerability scanning (pip-audit), and AI-assisted source code review
2. **Complexity Review** - Cyclomatic complexity analysis (radon), dead code detection (vulture), and duplicate code identification
3. **Documentation Review** - Checks for README, API docs, and contributing guides; evaluates documentation relevance against the actual codebase

Results from all three workstreams are synthesized by a report agent into a comprehensive `FinalReport`.

## Architecture

```
ReviewRequest (repo URL + branch)
        |
   clone_repo()
        |
   +----+----+--------------------+
   |         |                    |
Security  Complexity      Documentation
 Agent      Agent              Agent
   |         |                    |
   +----+----+--------------------+
        |
   Report Agent
        |
   FinalReport (JSON)
```

Each agent is a Pydantic AI `Agent` with tool functions that execute analysis tools (bandit, radon, vulture, pip-audit) and read source files. The agents use Claude to interpret tool outputs and produce structured Pydantic model results.

## Setup

### Prerequisites

- Python 3.11+
- Git
- A Honeycomb account (for telemetry)
- An Anthropic API key

### Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### Configuration

Copy `.env.example` to `.env` and fill in your keys:

```bash
cp .env.example .env
```

Required environment variables:

| Variable | Description |
|---|---|
| `HONEYCOMB_API_KEY` | Your Honeycomb API key |
| `OTEL_SERVICE_NAME` | Service name for telemetry (default: `code-reviewer`) |
| `ANTHROPIC_API_KEY` | Your Anthropic API key |
| `CLAUDE_CODE_ENABLE_TELEMETRY` | Enable telemetry (`true`) |
| `AGENT_LOG_STATUS` | Log agent status (`true`) |
| `OTEL_LOG_USER_PROMPTS` | Log user prompts in telemetry (`true`) |

## Usage

The simplest way to run the reviewer is with the `./execute-agent` script, which activates the virtual environment automatically:

```bash
# Review a repository
./execute-agent https://github.com/user/repo

# Uses a default demo repo if no URL is provided
./execute-agent
```

To run the full load test (starts an OTel collector, reviews multiple repos, then tears down the collector):

```bash
# Run 1 cycle (default)
./run-tests

# Run 3 cycles
./run-tests 3
```

You can also run it directly:

```bash
source .venv/bin/activate
python src/code_reviewer/main.py https://github.com/user/repo
```

Output is a JSON `FinalReport` containing security, complexity, and documentation review results with severity-rated findings.

## Telemetry

The application sends OpenTelemetry traces to Honeycomb using the GenAI Semantic Conventions (v1.40.0). Traces include:

- `gen_ai.system` - Provider (anthropic)
- `gen_ai.request.model` / `gen_ai.response.model` - Model used
- `gen_ai.usage.input_tokens` / `gen_ai.usage.output_tokens` - Token usage
- `gen_ai.operation.name` - Operation type (chat)

Custom spans cover the full pipeline: cloning, each review workstream, tool executions (bandit, radon, vulture, pip-audit), and report generation.

## Development

```bash
# Run tests
pytest tests/ -v

# Run with coverage
coverage run -m pytest tests/ && coverage report

# Lint
ruff check src/ tests/
```

## Project Structure

```
src/code_reviewer/
    __init__.py
    main.py              # CLI entry point
    config.py            # Configuration constants
    pipeline.py          # Orchestration pipeline
    repo.py              # Git clone/cleanup
    telemetry.py         # OTel setup + GenAI conventions
    agents/
        __init__.py
        security.py      # Security review agent
        complexity.py    # Complexity review agent
        documentation.py # Documentation review agent
        report.py        # Final report agent
    models/
        __init__.py
        review.py        # Pydantic models
tests/
    test_agents.py
    test_main.py
    test_models.py
    test_pipeline.py
    test_repo.py
    test_telemetry.py
```
