"""Configuration constants."""

import os

DEFAULT_MODEL = os.getenv("CODE_REVIEWER_MODEL", "anthropic:claude-sonnet-4-20250514")
