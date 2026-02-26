"""
Dynamic query template engine using Jinja2.

Renders SQL query templates with conditional blocks so that
filters are only included when the user provides a value.
This avoids the fragile `(:param IS NULL OR ...)` pattern
and produces cleaner, more performant SQL.

Example template:
    SELECT category, SUM(amount) as total
    FROM orders
    WHERE 1=1
    {% if date_start %} AND created_at >= :date_start {% endif %}
    {% if status %} AND status = :status {% endif %}
    GROUP BY category

When called with params={"date_start": "2025-01-01"} the engine
renders only the date_start condition; the status clause is
stripped entirely.
"""

import re
from typing import Dict, Any, Tuple, List
from jinja2.sandbox import SandboxedEnvironment


# Sandboxed Jinja2 environment — no file access, no imports,
# no attribute/item access on objects.
_jinja_env = SandboxedEnvironment(
    autoescape=False,
    keep_trailing_newline=True,
)


def _normalize_template(template_str: str) -> str:
    """
    Fix double-escaped Jinja2 tags produced by some LLMs.

    Converts ``{%% if x %%}`` → ``{% if x %}`` and similar
    patterns so the Jinja2 parser can handle them.

    Parameters:
        template_str (str): Raw SQL template string.

    Returns:
        str: Template with normalised Jinja2 delimiters.
    """
    # {%% ... %%}  →  {% ... %}
    template_str = re.sub(r"\{%%", "{%", template_str)
    template_str = re.sub(r"%%}", "%}", template_str)
    return template_str


def render_query(
    template_str: str,
    params: Dict[str, Any],
) -> Tuple[str, Dict[str, Any]]:
    """
    Render a Jinja2 SQL template and return the final SQL
    with only the relevant bound parameters.

    1. Normalise double-escaped Jinja2 delimiters.
    2. Evaluate Jinja2 conditionals using *boolean-only*
       context — actual param values are never passed into
       the template so user input cannot be evaluated as
       Jinja2 expressions.
    3. Extract :param_name placeholders from the rendered SQL.
    4. Return only the params that actually appear in the
       final SQL.

    Parameters:
        template_str (str): Jinja2-enhanced SQL template.
        params (dict): All available parameter values.

    Returns:
        tuple[str, dict]: (rendered_sql, filtered_params)
    """
    # Normalise templates that contain double-escaped
    # Jinja2 delimiters (e.g. {%% if x %%} → {% if x %}).
    template_str = _normalize_template(template_str)

    # SECURITY: Only pass booleans into the Jinja2 context so
    # user-supplied strings are never evaluated as expressions.
    context = {k: bool(v) for k, v in params.items()}

    template = _jinja_env.from_string(template_str)
    rendered_sql = template.render(**context)

    # Clean up extra blank lines produced by removed blocks
    # and strip trailing semicolons that some AI models add.
    rendered_sql = re.sub(r"\n\s*\n", "\n", rendered_sql).strip()
    rendered_sql = rendered_sql.rstrip(";").strip()

    # Detect placeholders still present in the rendered SQL.
    used_placeholders = set(
        re.findall(r":([a-zA-Z_][a-zA-Z0-9_]*)", rendered_sql)
    )

    # Start with only the supplied params that are referenced.
    # Coerce numeric strings to int/float so that MySQL
    # clauses like LIMIT work correctly (they reject strings).
    filtered_params = {}
    for k, v in params.items():
        if k not in used_placeholders:
            continue
        filtered_params[k] = _coerce_numeric(v)

    # Backward compat: for non-Jinja templates (old-style
    # `(:param IS NULL OR ...)` pattern), default any
    # unreferenced placeholders to None so SQLAlchemy won't
    # complain about missing bind values.
    if not is_jinja_template(template_str):
        for placeholder in used_placeholders:
            if placeholder not in filtered_params:
                filtered_params[placeholder] = None

    return rendered_sql, filtered_params


def is_jinja_template(template_str: str) -> bool:
    """
    Check whether a query template contains Jinja2 syntax.

    Parameters:
        template_str (str): The SQL template string.

    Returns:
        bool: True if the template contains Jinja2 blocks.
    """
    return bool(re.search(r"\{[%{#]", template_str))


def extract_all_params(template_str: str) -> List[str]:
    """
    Extract all :param_name placeholders from a raw template.

    Works on both Jinja2 templates and plain SQL — scans the
    full text regardless of conditional blocks.

    Parameters:
        template_str (str): The SQL template string.

    Returns:
        list[str]: Unique parameter names found.
    """
    return list(set(
        re.findall(r":([a-zA-Z_][a-zA-Z0-9_]*)", template_str)
    ))


def _coerce_numeric(value: Any) -> Any:
    """
    Convert a string value to int or float if it looks numeric.

    Query-string params arrive as strings, but MySQL clauses
    like ``LIMIT`` require integers.  This helper coerces
    cleanly without silently changing non-numeric values.

    Parameters:
        value: The raw parameter value.

    Returns:
        The original value, or an int/float if convertible.
    """
    if not isinstance(value, str):
        return value
    # Try int first (covers LIMIT, OFFSET, etc.)
    try:
        return int(value)
    except ValueError:
        pass
    # Then float
    try:
        return float(value)
    except ValueError:
        return value
