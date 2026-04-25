"""Prompt rendering and lightweight response parsing helpers."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"
_PROMPT_ENV = Environment(
    loader=FileSystemLoader(PROMPTS_DIR),
    undefined=StrictUndefined,
    autoescape=False,
    trim_blocks=True,
    lstrip_blocks=True,
)


def render_prompt(template_name: str, **context: Any) -> str:
    """Render a prompt template from the repository prompt directory."""

    return _PROMPT_ENV.get_template(template_name).render(**context).strip()


def parse_json_response(content: str) -> Any:
    """Parse a JSON response, tolerating fenced markdown payloads."""

    return json.loads(_strip_code_fences(content).strip())


def count_sentences(text: str) -> int:
    """Count sentence-like segments in generated prose."""

    return len(split_sentences(text))


def split_sentences(text: str) -> tuple[str, ...]:
    """Split prose into sentence-like segments."""

    cleaned = text.strip()
    if not cleaned:
        return ()
    return tuple(
        segment.strip()
        for segment in re.split(r"(?<=[.!?])\s+", cleaned)
        if segment.strip()
    )


def split_paragraphs(text: str) -> tuple[str, ...]:
    """Split prose into non-empty paragraphs."""

    cleaned = text.strip()
    if not cleaned:
        return ()
    return tuple(
        paragraph.strip()
        for paragraph in re.split(r"\n\s*\n+", cleaned)
        if paragraph.strip()
    )


def _strip_code_fences(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped

    lines = stripped.splitlines()
    if len(lines) >= 3 and lines[-1].startswith("```"):
        return "\n".join(lines[1:-1])
    return stripped
