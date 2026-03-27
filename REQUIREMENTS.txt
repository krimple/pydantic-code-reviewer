 Create an AI application with Pydantic using agents:

- one agent will build the application
- another agent will set up OpenTelemetry
- once both of the above agents are done, a third agent will instrument the application with the Generative AI Semantic Conventions 1.40.0
- a final agent will run the application and test it

The agentic application will:

Take an incoming github repository URL
Clone the repository locally
Run three different workstreams:
  1. check for security issues and bad dependency issues
  2. review the codebase for cyclomatic complexity, repeated code, and dead code
  3. review the application's documentation and make sure it exists, and if so, is it relevant to the current application codebase
Then, once completed, the application send this data to a final agent that will write a final report.

Technical requirements:
- the application will be fully tested
- the application will be thoroughly documented
- The application will use Pydantic to do its work and send telemetry
- The telemetry will be sent to Honeycomb
- The application's .env file will need a HONEYCOMB_API_KEY, a OTEL_SERVICE_NAME, an ANTHROPIC_API_KEY, and use
CLAUDE_CODE_ENABLE_TELEMETRY and AGENT_LOG_STATUS and OTEL_LOG_USER_PROMPTS
