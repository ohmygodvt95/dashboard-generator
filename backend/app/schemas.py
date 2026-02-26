"""
Pydantic schemas for API request/response validation.

Provides data validation, serialization, and documentation
for all API endpoints.
"""

from typing import Optional, List, Any, Dict
from datetime import datetime
from pydantic import BaseModel, Field, field_validator


# --- Allowed type enums --------------------------------

CHART_TYPES = {
    "bar", "line", "pie", "doughnut", "area",
    "scatter", "radar", "polarArea", "bubble",
}

FILTER_TYPES = {
    "select", "text", "number", "date",
    "date_range", "slider",
}


# --- DB Connection Schemas ---

class ConnectionCreate(BaseModel):
    """Schema for creating a new database connection."""

    name: str = Field(..., min_length=1, max_length=255)
    host: str = Field(default="localhost", max_length=255)
    port: int = Field(default=3306, ge=1, le=65535)
    username: str = Field(..., max_length=255)
    password: str = Field(default="")
    database_name: str = Field(..., min_length=1, max_length=255)


class ConnectionUpdate(BaseModel):
    """Schema for updating a database connection."""

    name: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    username: Optional[str] = None
    password: Optional[str] = None
    database_name: Optional[str] = None


class ConnectionResponse(BaseModel):
    """Schema for database connection API response."""

    id: str
    name: str
    host: str
    port: int
    username: str
    database_name: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ConnectionTestResult(BaseModel):
    """Schema for connection test result."""

    success: bool
    message: str


class ColumnInfo(BaseModel):
    """Schema for a database column."""

    name: str
    type: str
    nullable: bool = True
    primary_key: bool = False


class TableInfo(BaseModel):
    """Schema for a database table with its columns."""

    name: str
    columns: List[ColumnInfo] = []


class SchemaResponse(BaseModel):
    """Schema for database schema introspection response."""

    database: str
    tables: List[TableInfo] = []


# --- Widget Schemas ---

class WidgetCreate(BaseModel):
    """Schema for creating a new widget."""

    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = ""
    connection_id: Optional[str] = None


class WidgetUpdate(BaseModel):
    """Schema for updating a widget."""

    name: Optional[str] = None
    description: Optional[str] = None
    connection_id: Optional[str] = None
    chart_type: Optional[str] = None
    query_template: Optional[str] = None
    chart_config: Optional[Dict[str, Any]] = None
    layout_config: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None

    @field_validator("chart_type")
    @classmethod
    def validate_chart_type(
        cls, v: Optional[str],
    ) -> Optional[str]:
        """Reject unknown chart types."""
        if v is not None and v not in CHART_TYPES:
            raise ValueError(
                f"Unsupported chart_type '{v}'. "
                f"Allowed: {sorted(CHART_TYPES)}"
            )
        return v


class FilterResponse(BaseModel):
    """Schema for widget filter API response."""

    id: str
    widget_id: str
    param_name: str
    label: str
    filter_type: str
    source_table: Optional[str] = None
    source_column: Optional[str] = None
    options_query: Optional[str] = None
    default_value: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    options: Optional[Any] = None
    is_required: bool = False
    sort_order: int = 0

    model_config = {"from_attributes": True}


class WidgetResponse(BaseModel):
    """Schema for widget API response.

    Note: ``query_template`` is intentionally excluded to
    avoid exposing raw SQL to the browser.  Frontend code
    should use ``has_query`` to decide whether data can be
    fetched.
    """

    id: str
    connection_id: Optional[str] = None
    name: str
    description: Optional[str] = ""
    chart_type: Optional[str] = "bar"
    has_query: bool = False
    chart_config: Optional[Any] = None
    layout_config: Optional[Any] = None
    is_active: bool = False
    filters: List[FilterResponse] = []
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# --- Chat Schemas ---

class ChatMessageSend(BaseModel):
    """Schema for sending a chat message."""

    message: str = Field(..., min_length=1)


class ChatMessageResponse(BaseModel):
    """Schema for a single chat message response."""

    id: str
    role: str
    content: str
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ChatResponse(BaseModel):
    """Schema for AI chat response with updated widget."""

    messages: List[ChatMessageResponse]
    widget: Optional[WidgetResponse] = None
