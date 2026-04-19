"""Render prompt templates with `{{variable}}` placeholders."""

import re
from typing import Any


_VAR_PATTERN = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")


def render_template_text(template: str, variables: dict[str, Any]) -> str:
    def _sub(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in variables:
            return match.group(0)
        return str(variables[key])

    return _VAR_PATTERN.sub(_sub, template)
