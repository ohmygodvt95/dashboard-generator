"""
Agent orchestrator.

Coordinates the multi-agent pipeline:

1. **Request Analyzer** → classifies intent, decides routing.
2. **Schema Analyzer**  → semantic schema analysis (cached).
3. **Query Builder**    → Jinja2 SQL template.
4. **Filter Builder**   → filter definitions + validation.
5. **Chart Builder**    → chart type + Chart.js config.

Returns a response in the same format as the legacy
``ai_chat.chat_with_ai()`` so the existing chat endpoint
can use it as a drop-in replacement.

Also provides a streaming variant (``orchestrate_chat_stream``)
that yields Server-Sent Events for real-time UI feedback.
"""

import json
import logging
from typing import Dict, Any, List, Optional, Generator

from sqlalchemy.orm import Session

from app.services.agents.request_analyzer import (
    RequestAnalyzerAgent,
)
from app.services.agents.schema_analyzer import (
    SchemaAnalyzerAgent,
)
from app.services.agents.query_builder import (
    QueryBuilderAgent,
)
from app.services.agents.filter_builder import (
    FilterBuilderAgent,
)
from app.services.agents.chart_builder import (
    ChartBuilderAgent,
)
from app.services.agents.summarizer import (
    SummarizerAgent,
    estimate_tokens,
)
from app.config import settings

logger = logging.getLogger(__name__)

# Singleton agent instances (stateless — safe to reuse)
_request_analyzer = RequestAnalyzerAgent()
_schema_analyzer = SchemaAnalyzerAgent()
_query_builder = QueryBuilderAgent()
_filter_builder = FilterBuilderAgent()
_chart_builder = ChartBuilderAgent()
_summarizer = SummarizerAgent()


def _sse_event(
    event: str,
    data: Any,
) -> str:
    """
    Format a Server-Sent Event string.

    Parameters:
        event (str): Event name.
        data: Payload (will be JSON-serialised).

    Returns:
        str: SSE-formatted string.
    """
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


def _maybe_summarize(
    chat_history: List[Dict[str, str]],
    widget_data: Optional[Dict],
    db: Optional[Session],
    widget_id: Optional[str] = None,
) -> tuple:
    """
    Check if the chat history exceeds the token limit and
    summarize if needed.

    Returns a (possibly compressed) chat_history and the
    updated summary string.  Also persists the new summary
    to ``Widget.chat_summary`` when a DB session is available.

    Parameters:
        chat_history (list[dict]): Full chat message list.
        widget_data (dict | None): Serialised widget (may
            contain prior ``chat_summary``).
        db (Session | None): SQLAlchemy session for persistence.
        widget_id (str | None): Widget UUID for DB update.

    Returns:
        tuple[list[dict], str | None, bool]:
            (effective_history, summary_text, did_summarize)
    """
    token_limit = settings.context_token_limit
    tokens = estimate_tokens(chat_history)

    if tokens <= token_limit:
        return chat_history, None, False

    logger.info(
        "[orchestrator] context too long (%d tokens > %d), "
        "running summarizer",
        tokens,
        token_limit,
    )

    previous_summary = ""
    if widget_data:
        previous_summary = widget_data.get(
            "chat_summary", ""
        ) or ""

    result = _summarizer.run({
        "chat_history": chat_history,
        "previous_summary": previous_summary,
    })
    new_summary = result.get("summary", "")

    # Persist to DB
    if db and widget_id:
        from app.models import Widget as WidgetModel
        widget_obj = db.query(WidgetModel).filter(
            WidgetModel.id == widget_id,
        ).first()
        if widget_obj:
            widget_obj.chat_summary = new_summary
            db.commit()

    # Replace history with summary + last few messages
    # Keep last 4 messages for immediate context
    recent = chat_history[-4:] if len(chat_history) > 4 else chat_history
    compressed = [
        {
            "role": "system",
            "content": (
                f"[Conversation summary]\n{new_summary}"
            ),
        },
        *recent,
    ]

    return compressed, new_summary, True


def orchestrate_chat(
    user_message: str,
    chat_history: List[Dict[str, str]],
    schema: Optional[Dict] = None,
    widget_data: Optional[Dict] = None,
    connection_id: Optional[str] = None,
    db: Optional[Session] = None,
) -> Dict[str, Any]:
    """
    Run the multi-agent pipeline and return a merged result.

    The returned dict has the same shape as the legacy
    ``ai_chat.chat_with_ai()`` response so the chat endpoint
    can apply it unchanged::

        {
            "message": "...",
            "widget_update": {
                "chart_type": "...",
                "query_template": "...",
                "chart_config": {...}
            },
            "filters": [...]
        }

    Parameters:
        user_message (str): The user's natural language input.
        chat_history (list[dict]): Previous messages
            (role / content dicts).
        schema (dict, optional): Raw DB schema.
        widget_data (dict, optional): Current serialised widget.
        connection_id (str, optional): UUID of the DB connection.
        db (Session, optional): SQLAlchemy session for cache.

    Returns:
        dict: Merged response ready for the chat endpoint.
    """
    has_connection = bool(connection_id and schema)
    widget_id = widget_data.get("id") if widget_data else None

    # ---- 0. Summarize if context is too long --------------------
    chat_history, _, _ = _maybe_summarize(
        chat_history, widget_data, db, widget_id,
    )

    # ---- 1. Request Analyzer ----------------------------------------
    logger.info("[orchestrator] step 1 — request analyzer")
    routing = _request_analyzer.run({
        "user_message": user_message,
        "chat_history": chat_history,
        "widget_data": widget_data,
        "has_connection": has_connection,
    })
    logger.info(
        "[orchestrator] intent=%s  query=%s  filter=%s  "
        "chart=%s  schema=%s",
        routing["intent"],
        routing["needs_query"],
        routing["needs_filters"],
        routing["needs_chart"],
        routing["needs_schema_analysis"],
    )

    # If no agents needed (greeting / question), return early.
    if not any([
        routing["needs_query"],
        routing["needs_filters"],
        routing["needs_chart"],
    ]):
        return {
            "message": routing.get("message") or routing.get(
                "summary", "OK"
            ),
            "widget_update": None,
            "filters": [],
        }

    # ---- 2. Schema Analyzer (cached) --------------------------------
    schema_analysis = None
    if routing["needs_schema_analysis"] and schema:
        logger.info("[orchestrator] step 2 — schema analyzer")
        schema_analysis = _schema_analyzer.run({
            "schema": schema,
            "connection_id": connection_id,
            "db": db,
        })

    # ---- Shared context for downstream agents -----------------------
    summary = routing.get("summary", "")
    base_ctx: Dict[str, Any] = {
        "user_message": user_message,
        "chat_history": chat_history,
        "widget_data": widget_data,
        "schema_analysis": schema_analysis,
        "summary": summary,
    }

    # ---- 3. Query Builder -------------------------------------------
    query_result = None
    query_template = (
        widget_data.get("query_template", "")
        if widget_data else ""
    )
    output_columns: list = []

    if routing["needs_query"]:
        logger.info("[orchestrator] step 3 — query builder")
        query_result = _query_builder.run(base_ctx)
        query_template = query_result.get(
            "query_template", query_template
        )
        output_columns = query_result.get(
            "output_columns", []
        )

    # ---- 4. Filter Builder ------------------------------------------
    filter_result = None
    if routing["needs_filters"]:
        logger.info("[orchestrator] step 4 — filter builder")
        filter_ctx = {
            **base_ctx,
            "query_template": query_template,
        }
        filter_result = _filter_builder.run(filter_ctx)

    # ---- 5. Chart Builder -------------------------------------------
    chart_result = None
    if routing["needs_chart"]:
        logger.info("[orchestrator] step 5 — chart builder")
        chart_ctx = {
            **base_ctx,
            "output_columns": output_columns,
        }
        chart_result = _chart_builder.run(chart_ctx)

    # ---- 6. Merge results -------------------------------------------
    return _merge(
        routing, query_result, filter_result, chart_result
    )


def orchestrate_chat_stream(
    user_message: str,
    chat_history: List[Dict[str, str]],
    schema: Optional[Dict] = None,
    widget_data: Optional[Dict] = None,
    connection_id: Optional[str] = None,
    db: Optional[Session] = None,
) -> Generator[str, None, Dict[str, Any]]:
    """
    Streaming variant of ``orchestrate_chat``.

    Yields SSE event strings as each agent starts/finishes,
    then returns the final merged result (accessible to the
    caller via ``generator.send()`` or by capturing the
    ``StopIteration.value``).

    SSE events emitted:

    - ``agent_start``  → ``{"agent": "...", "step": N}``
    - ``agent_done``   → ``{"agent": "...", "step": N}``
    - ``result``       → full chat response dict

    Parameters:
        (same as ``orchestrate_chat``)

    Yields:
        str: SSE-formatted event strings.

    Returns:
        dict: Merged chat response (same as orchestrate_chat).
    """
    has_connection = bool(connection_id and schema)
    step = 0
    widget_id = widget_data.get("id") if widget_data else None

    # ---- 0. Summarize if context is too long --------------------
    chat_history, summary_text, did_summarize = (
        _maybe_summarize(
            chat_history, widget_data, db, widget_id,
        )
    )
    if did_summarize:
        yield _sse_event("agent_done", {
            "agent": "summarizer",
            "label": "Compressed chat context",
            "step": 0,
        })

    # ---- 1. Request Analyzer ------------------------------------
    step += 1
    yield _sse_event("agent_start", {
        "agent": "request_analyzer",
        "label": "Analyzing request…",
        "step": step,
    })
    routing = _request_analyzer.run({
        "user_message": user_message,
        "chat_history": chat_history,
        "widget_data": widget_data,
        "has_connection": has_connection,
    })
    yield _sse_event("agent_done", {
        "agent": "request_analyzer",
        "step": step,
        "summary": routing.get("summary", ""),
    })

    if not any([
        routing["needs_query"],
        routing["needs_filters"],
        routing["needs_chart"],
    ]):
        result = {
            "message": routing.get("message")
            or routing.get("summary", "OK"),
            "widget_update": None,
            "filters": [],
        }
        yield _sse_event("result", result)
        return result

    # ---- 2. Schema Analyzer -------------------------------------
    schema_analysis = None
    if routing["needs_schema_analysis"] and schema:
        step += 1
        yield _sse_event("agent_start", {
            "agent": "schema_analyzer",
            "label": "Analyzing database schema…",
            "step": step,
        })
        schema_analysis = _schema_analyzer.run({
            "schema": schema,
            "connection_id": connection_id,
            "db": db,
        })
        yield _sse_event("agent_done", {
            "agent": "schema_analyzer",
            "step": step,
        })

    # ---- Shared context -----------------------------------------
    summary = routing.get("summary", "")
    base_ctx: Dict[str, Any] = {
        "user_message": user_message,
        "chat_history": chat_history,
        "widget_data": widget_data,
        "schema_analysis": schema_analysis,
        "summary": summary,
    }

    # ---- 3. Query Builder ---------------------------------------
    query_result = None
    query_template = (
        widget_data.get("query_template", "")
        if widget_data else ""
    )
    output_columns: list = []

    if routing["needs_query"]:
        step += 1
        yield _sse_event("agent_start", {
            "agent": "query_builder",
            "label": "Building SQL query…",
            "step": step,
        })
        query_result = _query_builder.run(base_ctx)
        query_template = query_result.get(
            "query_template", query_template
        )
        output_columns = query_result.get(
            "output_columns", []
        )
        yield _sse_event("agent_done", {
            "agent": "query_builder",
            "step": step,
        })

    # ---- 4. Filter Builder --------------------------------------
    filter_result = None
    if routing["needs_filters"]:
        step += 1
        yield _sse_event("agent_start", {
            "agent": "filter_builder",
            "label": "Designing filters…",
            "step": step,
        })
        filter_ctx = {
            **base_ctx,
            "query_template": query_template,
        }
        filter_result = _filter_builder.run(filter_ctx)
        yield _sse_event("agent_done", {
            "agent": "filter_builder",
            "step": step,
        })

    # ---- 5. Chart Builder ---------------------------------------
    chart_result = None
    if routing["needs_chart"]:
        step += 1
        yield _sse_event("agent_start", {
            "agent": "chart_builder",
            "label": "Configuring chart…",
            "step": step,
        })
        chart_ctx = {
            **base_ctx,
            "output_columns": output_columns,
        }
        chart_result = _chart_builder.run(chart_ctx)
        yield _sse_event("agent_done", {
            "agent": "chart_builder",
            "step": step,
        })

    # ---- 6. Merge -----------------------------------------------
    result = _merge(
        routing, query_result, filter_result, chart_result
    )
    yield _sse_event("result", result)
    return result


# ----- internal helpers -----------------------------------------------


def _merge(
    routing: Dict[str, Any],
    query_result: Optional[Dict[str, Any]],
    filter_result: Optional[Dict[str, Any]],
    chart_result: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Combine agent outputs into the canonical response format.

    Parameters:
        routing (dict): Request analyser output.
        query_result (dict | None): Query builder output.
        filter_result (dict | None): Filter builder output.
        chart_result (dict | None): Chart builder output.

    Returns:
        dict: ``message``, ``widget_update``, ``filters``.
    """
    widget_update: Dict[str, Any] = {}
    filters: list = []
    explanations: List[str] = []

    if query_result:
        qt = query_result.get("query_template", "")
        if qt:
            widget_update["query_template"] = qt
        exp = query_result.get("explanation", "")
        if exp:
            explanations.append(f"📊 Query: {exp}")

    if chart_result:
        ct = chart_result.get("chart_type", "")
        if ct:
            widget_update["chart_type"] = ct
        cc = chart_result.get("chart_config")
        if cc:
            widget_update["chart_config"] = cc
        exp = chart_result.get("explanation", "")
        if exp:
            explanations.append(f"📈 Chart: {exp}")

    if filter_result:
        filters = filter_result.get("filters", [])
        exp = filter_result.get("explanation", "")
        if exp:
            explanations.append(f"🔍 Filters: {exp}")
        warns = filter_result.get("warnings", [])
        for w in warns:
            explanations.append(f"⚠️ {w}")

    message = "\n".join(explanations) if explanations else (
        routing.get("summary", "Done.")
    )

    return {
        "message": message,
        "widget_update": widget_update or None,
        "filters": filters,
    }
