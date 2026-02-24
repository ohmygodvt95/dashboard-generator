"""
API routes for database connection management.

Provides CRUD operations, connection testing, and schema
introspection for target MySQL databases.
"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import DBConnection
from app.schemas import (
    ConnectionCreate,
    ConnectionUpdate,
    ConnectionResponse,
    ConnectionTestResult,
    SchemaResponse,
)
from app.services import db_connector

router = APIRouter(prefix="/api/connections", tags=["connections"])


@router.get(
    "",
    response_model=List[ConnectionResponse],
    summary="List all database connections",
)
def list_connections(db: Session = Depends(get_db)):
    """Retrieve all stored database connections."""
    return db.query(DBConnection).all()


@router.post(
    "",
    response_model=ConnectionResponse,
    status_code=201,
    summary="Create a new database connection",
)
def create_connection(
    data: ConnectionCreate,
    db: Session = Depends(get_db),
):
    """
    Create a new database connection configuration.

    Stores the connection credentials for later use
    with widgets.
    """
    conn = DBConnection(
        name=data.name,
        host=data.host,
        port=data.port,
        username=data.username,
        password_enc=data.password,
        database_name=data.database_name,
    )
    db.add(conn)
    db.commit()
    db.refresh(conn)
    return conn


@router.get(
    "/{connection_id}",
    response_model=ConnectionResponse,
    summary="Get a database connection by ID",
)
def get_connection(
    connection_id: str,
    db: Session = Depends(get_db),
):
    """Retrieve a specific database connection by its ID."""
    conn = db.query(DBConnection).filter(
        DBConnection.id == connection_id
    ).first()
    if not conn:
        raise HTTPException(
            status_code=404,
            detail="Connection not found",
        )
    return conn


@router.put(
    "/{connection_id}",
    response_model=ConnectionResponse,
    summary="Update a database connection",
)
def update_connection(
    connection_id: str,
    data: ConnectionUpdate,
    db: Session = Depends(get_db),
):
    """Update an existing database connection configuration."""
    conn = db.query(DBConnection).filter(
        DBConnection.id == connection_id
    ).first()
    if not conn:
        raise HTTPException(
            status_code=404,
            detail="Connection not found",
        )

    update_data = data.model_dump(exclude_unset=True)
    # Map 'password' field to 'password_enc' column
    if "password" in update_data:
        update_data["password_enc"] = update_data.pop("password")

    for key, value in update_data.items():
        setattr(conn, key, value)

    db.commit()
    db.refresh(conn)
    return conn


@router.delete(
    "/{connection_id}",
    status_code=204,
    summary="Delete a database connection",
)
def delete_connection(
    connection_id: str,
    db: Session = Depends(get_db),
):
    """Delete a database connection and its related data."""
    conn = db.query(DBConnection).filter(
        DBConnection.id == connection_id
    ).first()
    if not conn:
        raise HTTPException(
            status_code=404,
            detail="Connection not found",
        )
    db.delete(conn)
    db.commit()


@router.post(
    "/{connection_id}/test",
    response_model=ConnectionTestResult,
    summary="Test a database connection",
)
def test_connection_endpoint(
    connection_id: str,
    db: Session = Depends(get_db),
):
    """
    Test connectivity to the target MySQL database.

    Attempts to connect and execute a simple query
    to verify the connection works.
    """
    conn = db.query(DBConnection).filter(
        DBConnection.id == connection_id
    ).first()
    if not conn:
        raise HTTPException(
            status_code=404,
            detail="Connection not found",
        )
    result = db_connector.test_connection(conn)
    return result


@router.get(
    "/{connection_id}/schema",
    response_model=SchemaResponse,
    summary="Get database schema",
)
def get_connection_schema(
    connection_id: str,
    db: Session = Depends(get_db),
):
    """
    Introspect the target database schema.

    Returns all tables, columns, types, and key information
    for the connected MySQL database.
    """
    conn = db.query(DBConnection).filter(
        DBConnection.id == connection_id
    ).first()
    if not conn:
        raise HTTPException(
            status_code=404,
            detail="Connection not found",
        )
    try:
        schema = db_connector.get_schema(conn)
        return schema
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to read schema: {str(e)}",
        )
