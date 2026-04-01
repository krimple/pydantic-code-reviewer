#!/usr/bin/env bash
set -euo pipefail

aws sso login --sso-session sso-default

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Load environment variables from .env
set -a
source "${SCRIPT_DIR}/.env"
set +a

exec otelcol-contrib --config "${SCRIPT_DIR}/collector-config.yaml"
