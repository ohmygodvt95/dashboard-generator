"""
SQLAlchemy models for the Chart Widget Builder.

Defines database tables for widgets, connections, filters,
chat messages, and widget styles.
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    String,
    Text,
    Integer,
    Boolean,
    DateTime,
    ForeignKey,
)
from sqlalchemy.orm import relationship
from app.database import Base


def generate_uuid() -> str:
    """Generate a new UUID string."""
    return str(uuid.uuid4())


def utcnow() -> datetime:
    """Return the current UTC datetime."""
    return datetime.now(timezone.utc)


class DBConnection(Base):
    """
    Model for storing MySQL database connection configurations.

    Each connection stores credentials and host info needed to
    connect to a target MySQL database for data retrieval.
    """

    __tablename__ = "db_connections"

    id = Column(String, primary_key=True, default=generate_uuid)
    name = Column(String(255), nullable=False)
    host = Column(String(255), nullable=False, default="localhost")
    port = Column(Integer, nullable=False, default=3306)
    username = Column(String(255), nullable=False)
    password_enc = Column(Text, nullable=False, default="")
    database_name = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    widgets = relationship(
        "Widget",
        back_populates="connection",
        cascade="all, delete-orphan",
    )


class Widget(Base):
    """
    Main widget configuration model.

    Stores chart type, SQL query template, chart configuration,
    and layout settings for each embeddable widget.
    """

    __tablename__ = "widgets"

    id = Column(String, primary_key=True, default=generate_uuid)
    connection_id = Column(
        String, ForeignKey("db_connections.id"), nullable=True
    )
    name = Column(String(255), nullable=False)
    description = Column(Text, default="")
    chart_type = Column(String(50), default="bar")
    query_template = Column(Text, default="")
    chart_config = Column(Text, default="{}")
    layout_config = Column(Text, default="{}")
    is_active = Column(Boolean, default=False)
    chat_summary = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    connection = relationship("DBConnection", back_populates="widgets")
    filters = relationship(
        "WidgetFilter",
        back_populates="widget",
        cascade="all, delete-orphan",
    )
    chat_messages = relationship(
        "ChatMessage",
        back_populates="widget",
        cascade="all, delete-orphan",
    )
    style = relationship(
        "WidgetStyle",
        back_populates="widget",
        uselist=False,
        cascade="all, delete-orphan",
    )


class WidgetFilter(Base):
    """
    Filter configuration for a widget.

    Filters map to named parameters in the widget's SQL query
    template, allowing end-users to dynamically filter chart data.
    """

    __tablename__ = "widget_filters"

    id = Column(String, primary_key=True, default=generate_uuid)
    widget_id = Column(
        String, ForeignKey("widgets.id"), nullable=False
    )
    param_name = Column(String(100), nullable=False)
    label = Column(String(255), nullable=False)
    filter_type = Column(String(50), nullable=False, default="text")
    source_table = Column(String(255), nullable=True)
    source_column = Column(String(255), nullable=True)
    options_query = Column(Text, nullable=True)
    default_value = Column(Text, nullable=True)
    config = Column(Text, default="{}")
    options = Column(Text, default="[]")
    is_required = Column(Boolean, default=False)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    widget = relationship("Widget", back_populates="filters")


class ChatMessage(Base):
    """
    Chat message in the AI conversation for a widget.

    Stores the full conversation history between the user
    and the AI assistant for each widget's configuration.
    """

    __tablename__ = "chat_messages"

    id = Column(String, primary_key=True, default=generate_uuid)
    widget_id = Column(
        String, ForeignKey("widgets.id"), nullable=False
    )
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    metadata_json = Column(Text, default="{}")
    created_at = Column(DateTime, default=utcnow)

    widget = relationship("Widget", back_populates="chat_messages")


class WidgetStyle(Base):
    """
    Custom styling configuration for a widget.

    Allows per-widget theme and CSS customization.
    """

    __tablename__ = "widget_styles"

    id = Column(String, primary_key=True, default=generate_uuid)
    widget_id = Column(
        String, ForeignKey("widgets.id"), nullable=False, unique=True
    )
    theme = Column(Text, default="{}")
    custom_css = Column(Text, default="")
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    widget = relationship("Widget", back_populates="style")


class SchemaAnalysis(Base):
    """
    Cached AI analysis of a database schema.

    Stores semantic analysis (table descriptions, relationships,
    suggested metrics) so it can be reused across chat sessions
    without re-calling the AI.  Invalidated via schema_hash when
    the underlying schema changes.
    """

    __tablename__ = "schema_analyses"

    id = Column(String, primary_key=True, default=generate_uuid)
    connection_id = Column(
        String,
        ForeignKey("db_connections.id"),
        nullable=False,
        unique=True,
    )
    analysis = Column(Text, nullable=False, default="{}")
    schema_hash = Column(String(64), nullable=False)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)
