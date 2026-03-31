This is a code review agent that clones a git repository and analyzes it across several dimensions, writing a report at the end.

It uses the following APIs:

- pydantic_ai - provides integrations with agents and LLMs
- OpenTelemetry Python API/SDK - to send telemetry to Honeycomb
- dotenv - to read environment vars from .env files at startup
- git - to clone projects on GitHub
- shutil - to run shell scripts
-

