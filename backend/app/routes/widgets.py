"""
API routes for widget management and AI chat.

Provides CRUD operations for widgets, data execution,
and AI-powered chat for widget configuration.
"""

import json
import logging
import re
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db, SessionLocal
from app.models import (
    Widget,
    WidgetFilter,
    ChatMessage,
    DBConnection,
)
from app.schemas import (
    WidgetCreate,
    WidgetUpdate,
    WidgetResponse,
    ChatMessageSend,
    ChatMessageResponse,
    ChatResponse,
    FilterResponse,
)
from app.services import db_connector
from app.services.agents import (
    orchestrate_chat,
    orchestrate_chat_stream,
)
from app.services.query_engine import render_query

router = APIRouter(prefix="/api/widgets", tags=["widgets"])


def _serialize_widget(widget: Widget) -> Dict[str, Any]:
    """
    Serialize a widget model to a dictionary with parsed JSON fields.

    Parameters:
        widget (Widget): The widget model instance.

    Returns:
        dict: Serialized widget data with parsed JSON configs.
    """
    filters = []
    for f in widget.filters:
        filter_data = {
            "id": f.id,
            "widget_id": f.widget_id,
            "param_name": f.param_name,
            "label": f.label,
            "filter_type": f.filter_type,
            "source_table": f.source_table,
            "source_column": f.source_column,
            "options_query": f.options_query,
            "default_value": f.default_value,
            "is_required": f.is_required,
            "sort_order": f.sort_order,
        }
        try:
            filter_data["options"] = json.loads(f.options or "[]")
        except (json.JSONDecodeError, TypeError):
            filter_data["options"] = []
        try:
            filter_data["config"] = json.loads(f.config or "{}")
        except (json.JSONDecodeError, TypeError):
            filter_data["config"] = {}
        filters.append(filter_data)

    try:
        chart_config = json.loads(widget.chart_config or "{}")
    except (json.JSONDecodeError, TypeError):
        chart_config = {}

    try:
        layout_config = json.loads(widget.layout_config or "{}")
    except (json.JSONDecodeError, TypeError):
        layout_config = {}

    return {
        "id": widget.id,
        "connection_id": widget.connection_id,
        "name": widget.name,
        "description": widget.description,
        "chart_type": widget.chart_type,
        "has_query": bool(widget.query_template),
        "chart_config": chart_config,
        "layout_config": layout_config,
        "is_active": widget.is_active,
        "filters": filters,
        "created_at": widget.created_at,
        "updated_at": widget.updated_at,
    }


def _internal_widget_data(widget: Widget) -> Dict[str, Any]:
    """
    Build an internal widget dict for the AI orchestrator.

    Includes ``query_template`` and ``chat_summary`` which
    are intentionally excluded from the public API response.

    Parameters:
        widget (Widget): The widget model instance.

    Returns:
        dict: Full widget data for agent context.
    """
    data = _serialize_widget(widget)
    data["query_template"] = widget.query_template or ""
    data["chat_summary"] = widget.chat_summary or ""
    return data


# Patterns that must NEVER appear in executable SQL.
_DANGEROUS_SQL_RE = re.compile(
    r"\b(DROP|DELETE|TRUNCATE|UPDATE|INSERT|ALTER|CREATE|"
    r"REPLACE|GRANT|REVOKE|EXEC|EXECUTE|CALL|LOAD|INTO\s+OUTFILE"
    r")\b",
    re.IGNORECASE,
)


def validate_query(sql: str) -> None:
    """
    Reject SQL that contains write / DDL statements.

    Parameters:
        sql (str): Rendered SQL about to be executed.

    Raises:
        HTTPException: 400 if the query is unsafe.
    """
    match = _DANGEROUS_SQL_RE.search(sql)
    if match:
        raise HTTPException(
            status_code=400,
            detail="Query contains disallowed statement",
        )


def _allowed_filter_params(widget: Widget) -> set:
    """
    Build a set of parameter names the widget's declared
    filters allow.  Values outside this set are ignored so
    users cannot inject arbitrary query-string params.

    For ``date_range`` filters the set includes both
    ``<param>_start`` and ``<param>_end``.

    Parameters:
        widget (Widget): The widget model instance.

    Returns:
        set[str]: Allowed parameter names.
    """
    allowed: set = set()
    for f in widget.filters:
        if f.filter_type == "date_range":
            allowed.add(f"{f.param_name}_start")
            allowed.add(f"{f.param_name}_end")
        else:
            allowed.add(f.param_name)
    return allowed


# Filter types that produce a simple scalar param.
_SCALAR_FILTER_TYPES = {
    "text", "number", "select", "date", "slider",
}


@router.get(
    "",
    response_model=List[WidgetResponse],
    summary="List all widgets",
)
def list_widgets(db: Session = Depends(get_db)):
    """Retrieve all widgets with their filter configurations."""
    widgets = db.query(Widget).all()
    return [_serialize_widget(w) for w in widgets]


@router.post(
    "",
    response_model=WidgetResponse,
    status_code=201,
    summary="Create a new widget",
)
def create_widget(
    data: WidgetCreate,
    db: Session = Depends(get_db),
):
    """
    Create a new widget with basic information.

    The widget starts as a draft and can be configured
    via the AI chat interface.
    """
    widget = Widget(
        name=data.name,
        description=data.description or "",
        connection_id=data.connection_id,
    )
    db.add(widget)
    db.commit()
    db.refresh(widget)
    return _serialize_widget(widget)


@router.get(
    "/{widget_id}",
    response_model=WidgetResponse,
    summary="Get a widget by ID",
)
def get_widget(
    widget_id: str,
    db: Session = Depends(get_db),
):
    """Retrieve a specific widget with its full configuration."""
    widget = db.query(Widget).filter(
        Widget.id == widget_id
    ).first()
    if not widget:
        raise HTTPException(
            status_code=404,
            detail="Widget not found",
        )
    return _serialize_widget(widget)


@router.put(
    "/{widget_id}",
    response_model=WidgetResponse,
    summary="Update a widget",
)
def update_widget(
    widget_id: str,
    data: WidgetUpdate,
    db: Session = Depends(get_db),
):
    """Update an existing widget's configuration."""
    widget = db.query(Widget).filter(
        Widget.id == widget_id
    ).first()
    if not widget:
        raise HTTPException(
            status_code=404,
            detail="Widget not found",
        )

    update_data = data.model_dump(exclude_unset=True)

    # query_template must only be set by the AI pipeline,
    # never directly via the REST API.
    update_data.pop("query_template", None)

    # Serialize JSON fields to strings for storage
    if "chart_config" in update_data and update_data["chart_config"]:
        update_data["chart_config"] = json.dumps(
            update_data["chart_config"]
        )
    if "layout_config" in update_data and update_data["layout_config"]:
        update_data["layout_config"] = json.dumps(
            update_data["layout_config"]
        )

    for key, value in update_data.items():
        setattr(widget, key, value)

    db.commit()
    db.refresh(widget)
    return _serialize_widget(widget)


@router.delete(
    "/{widget_id}",
    status_code=204,
    summary="Delete a widget",
)
def delete_widget(
    widget_id: str,
    db: Session = Depends(get_db),
):
    """Delete a widget and all its related data."""
    widget = db.query(Widget).filter(
        Widget.id == widget_id
    ).first()
    if not widget:
        raise HTTPException(
            status_code=404,
            detail="Widget not found",
        )
    db.delete(widget)
    db.commit()


@router.get(
    "/{widget_id}/data",
    summary="Execute widget query and return data",
)
def get_widget_data(
    widget_id: str,
    request: "Request",
    db: Session = Depends(get_db),
):
    """
    Execute the widget's SQL query against its connected database.

    Accepts query parameters that map to the query template's
    named parameters for filtering.

    Returns:
        list[dict]: Query result rows as dictionaries.
    """
    widget = db.query(Widget).filter(
        Widget.id == widget_id
    ).first()
    if not widget:
        raise HTTPException(
            status_code=404,
            detail="Widget not found",
        )
    if not widget.connection_id:
        raise HTTPException(
            status_code=400,
            detail="Widget has no database connection configured",
        )
    if not widget.query_template:
        raise HTTPException(
            status_code=400,
            detail="Widget has no query template configured",
        )

    conn = db.query(DBConnection).filter(
        DBConnection.id == widget.connection_id
    ).first()
    if not conn:
        raise HTTPException(
            status_code=404,
            detail="Database connection not found",
        )

    try:
        # Only accept params that match declared filters
        allowed_params = _allowed_filter_params(widget)
        raw_params = dict(request.query_params)
        params = {
            k: v for k, v in raw_params.items()
            if k in allowed_params
        }

        # Render the Jinja2 query template — conditional
        # blocks for missing filters are stripped out, so
        # only active filters appear in the final SQL.
        rendered_sql, bound_params = render_query(
            widget.query_template, params
        )

        # Safety check: reject if rendered SQL contains
        # anything other than a SELECT.
        validate_query(rendered_sql)

        data = db_connector.execute_query(
            conn, rendered_sql, bound_params
        )
        return data
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(
            "Widget %s query execution failed: %s",
            widget_id,
            exc,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Query execution failed: {exc}",
        )


# --- Chat Endpoints ---


@router.get(
    "/{widget_id}/filters/{filter_id}/options",
    summary="Search filter options",
)
def get_filter_options(
    widget_id: str,
    filter_id: str,
    search: Optional[str] = Query(
        default=None,
        max_length=200,
        description="Search term for filtering options",
    ),
    limit: int = Query(
        default=50,
        ge=1,
        le=500,
        description="Max options to return",
    ),
    db: Session = Depends(get_db),
):
    """
    Fetch options for a select-type filter with optional
    server-side search.  Useful for large datasets where
    loading all distinct values upfront is impractical.

    Returns:
        list[dict]: Options with 'value' and 'label' keys.
    """
    widget = db.query(Widget).filter(
        Widget.id == widget_id,
    ).first()
    if not widget:
        raise HTTPException(
            status_code=404, detail="Widget not found",
        )

    widget_filter = db.query(WidgetFilter).filter(
        WidgetFilter.id == filter_id,
        WidgetFilter.widget_id == widget_id,
    ).first()
    if not widget_filter:
        raise HTTPException(
            status_code=404, detail="Filter not found",
        )

    conn = db.query(DBConnection).filter(
        DBConnection.id == widget.connection_id,
    ).first()
    if not conn:
        raise HTTPException(
            status_code=400,
            detail="Widget has no database connection",
        )

    try:
        options = db_connector.get_filter_options(
            conn, widget_filter,
            search=search,
            limit=limit,
        )
        return options
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail=str(exc),
        )
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Failed to fetch filter options",
        )


@router.delete(
    "/{widget_id}/filters/{filter_id}",
    status_code=204,
    summary="Delete a single filter",
)
def delete_filter(
    widget_id: str,
    filter_id: str,
    db: Session = Depends(get_db),
):
    """
    Remove an individual filter from a widget.

    The filter's query-template parameter will no longer
    be applied; the Jinja2 conditional block in the query
    simply becomes inactive.
    """
    widget_filter = db.query(WidgetFilter).filter(
        WidgetFilter.id == filter_id,
        WidgetFilter.widget_id == widget_id,
    ).first()
    if not widget_filter:
        raise HTTPException(
            status_code=404, detail="Filter not found",
        )
    db.delete(widget_filter)
    db.commit()


@router.get(
    "/{widget_id}/chat",
    response_model=List[ChatMessageResponse],
    summary="Get chat history for a widget",
)
def get_chat_history(
    widget_id: str,
    db: Session = Depends(get_db),
):
    """Retrieve the full AI chat history for a widget."""
    widget = db.query(Widget).filter(
        Widget.id == widget_id
    ).first()
    if not widget:
        raise HTTPException(
            status_code=404,
            detail="Widget not found",
        )
    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.widget_id == widget_id)
        .order_by(ChatMessage.created_at)
        .all()
    )
    return messages


@router.post(
    "/{widget_id}/chat",
    response_model=ChatResponse,
    summary="Send a chat message to AI",
)
def send_chat_message(
    widget_id: str,
    data: ChatMessageSend,
    db: Session = Depends(get_db),
):
    """
    Send a natural language message to the AI assistant.

    The AI will analyze the database schema and current widget
    configuration to generate or update the chart/query setup.

    Returns the AI response along with any widget updates applied.
    """
    widget = db.query(Widget).filter(
        Widget.id == widget_id
    ).first()
    if not widget:
        raise HTTPException(
            status_code=404,
            detail="Widget not found",
        )

    # Save user message
    user_msg = ChatMessage(
        widget_id=widget_id,
        role="user",
        content=data.message,
    )
    db.add(user_msg)
    db.commit()
    db.refresh(user_msg)

    # Get schema if connection exists
    schema = None
    conn = None
    if widget.connection_id:
        conn = db.query(DBConnection).filter(
            DBConnection.id == widget.connection_id
        ).first()
        if conn:
            try:
                schema = db_connector.get_schema(conn)
            except Exception:
                pass

    # Get chat history
    history = (
        db.query(ChatMessage)
        .filter(ChatMessage.widget_id == widget_id)
        .order_by(ChatMessage.created_at)
        .all()
    )
    chat_history = [
        {"role": m.role, "content": m.content}
        for m in history[:-1]  # Exclude the just-added message
    ]

    # Build current widget data for AI context
    widget_data = _internal_widget_data(widget)

    # Run multi-agent pipeline
    ai_response = orchestrate_chat(
        user_message=data.message,
        chat_history=chat_history,
        schema=schema,
        widget_data=widget_data,
        connection_id=widget.connection_id,
        db=db,
    )

    assistant_msg = _apply_ai_response(
        ai_response, widget, widget_id, db,
    )
    db.refresh(user_msg)

    return {
        "messages": [user_msg, assistant_msg],
        "widget": _serialize_widget(widget),
    }


def _apply_ai_response(
    ai_response: Dict[str, Any],
    widget: Widget,
    widget_id: str,
    db: "Session",
) -> ChatMessage:
    """
    Apply the merged AI response to the widget model and
    save the assistant chat message.

    Parameters:
        ai_response (dict): Merged response from orchestrator.
        widget (Widget): The widget model instance.
        widget_id (str): Widget UUID.
        db (Session): Active SQLAlchemy session.

    Returns:
        ChatMessage: The saved assistant message.
    """
    # Apply widget updates if provided
    if ai_response.get("widget_update"):
        update = ai_response["widget_update"]
        if update.get("chart_type"):
            widget.chart_type = update["chart_type"]
        if update.get("query_template"):
            try:
                validate_query(update["query_template"])
            except HTTPException:
                update.pop("query_template")
            else:
                widget.query_template = (
                    update["query_template"]
                )
        if update.get("chart_config"):
            widget.chart_config = json.dumps(
                update["chart_config"]
            )

    # Apply filter updates if provided
    if ai_response.get("filters"):
        db.query(WidgetFilter).filter(
            WidgetFilter.widget_id == widget_id
        ).delete()
        for i, f in enumerate(ai_response["filters"]):
            new_filter = WidgetFilter(
                widget_id=widget_id,
                param_name=f.get("param_name", ""),
                label=f.get("label", ""),
                filter_type=f.get("filter_type", "text"),
                source_table=f.get("source_table"),
                source_column=f.get("source_column"),
                options_query=f.get("options_query"),
                default_value=f.get("default_value"),
                config=json.dumps(f.get("config") or {}),
                options=json.dumps(f.get("options", [])),
                sort_order=i,
            )
            db.add(new_filter)

    # Save assistant message
    assistant_msg = ChatMessage(
        widget_id=widget_id,
        role="assistant",
        content=ai_response.get("message", "Done."),
        metadata_json=json.dumps(ai_response),
    )
    db.add(assistant_msg)
    db.commit()
    db.refresh(widget)
    db.refresh(assistant_msg)
    return assistant_msg


@router.post(
    "/{widget_id}/chat/stream",
    summary="Send a chat message (SSE stream)",
)
def send_chat_message_stream(
    widget_id: str,
    data: ChatMessageSend,
):
    """
    SSE streaming variant of the chat endpoint.

    Emits ``agent_start`` / ``agent_done`` events so the UI
    can display real-time progress, followed by a final
    ``done`` event with the complete response.

    The DB session is managed inside the generator because
    ``StreamingResponse`` consumes the iterator **after**
    FastAPI has cleaned up ``Depends``-based sessions.
    """

    def _sse(event: str, data_obj: Any) -> str:
        """Format a Server-Sent Event string."""
        payload = json.dumps(data_obj, ensure_ascii=False)
        return f"event: {event}\ndata: {payload}\n\n"

    def event_stream():
        """Yield SSE events from the orchestrator."""
        db = SessionLocal()
        try:
            widget = db.query(Widget).filter(
                Widget.id == widget_id
            ).first()
            if not widget:
                yield _sse(
                    "error", {"message": "Widget not found"},
                )
                return

            # Save user message
            user_msg = ChatMessage(
                widget_id=widget_id,
                role="user",
                content=data.message,
            )
            db.add(user_msg)
            db.commit()
            db.refresh(user_msg)

            # Get schema
            schema = None
            if widget.connection_id:
                conn = db.query(DBConnection).filter(
                    DBConnection.id == widget.connection_id
                ).first()
                if conn:
                    try:
                        schema = db_connector.get_schema(
                            conn,
                        )
                    except Exception:
                        pass

            # Chat history (exclude the just-added msg)
            history = (
                db.query(ChatMessage)
                .filter(
                    ChatMessage.widget_id == widget_id
                )
                .order_by(ChatMessage.created_at)
                .all()
            )
            chat_history = [
                {"role": m.role, "content": m.content}
                for m in history[:-1]
            ]

            widget_data = _internal_widget_data(widget)

            ai_response = None
            gen = orchestrate_chat_stream(
                user_message=data.message,
                chat_history=chat_history,
                schema=schema,
                widget_data=widget_data,
                connection_id=widget.connection_id,
                db=db,
            )

            for sse_event in gen:
                yield sse_event
                # Capture the result event payload
                if sse_event.startswith("event: result"):
                    line = sse_event.split(
                        "data: ", 1
                    )[1]
                    ai_response = json.loads(
                        line.split("\n")[0]
                    )

            # Apply the result to the widget and save
            if ai_response:
                assistant_msg = _apply_ai_response(
                    ai_response, widget, widget_id, db,
                )
                final = {
                    "messages": [
                        {
                            "id": user_msg.id,
                            "role": user_msg.role,
                            "content": user_msg.content,
                            "created_at": str(
                                user_msg.created_at
                            ),
                        },
                        {
                            "id": assistant_msg.id,
                            "role": assistant_msg.role,
                            "content": (
                                assistant_msg.content
                            ),
                            "created_at": str(
                                assistant_msg.created_at
                            ),
                        },
                    ],
                    "widget": _serialize_widget(widget),
                }
                yield (
                    f"event: done\n"
                    f"data: "
                    f"{json.dumps(final, default=str)}"
                    f"\n\n"
                )
        except Exception as exc:
            yield _sse(
                "error", {"message": str(exc)},
            )
        finally:
            db.close()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
