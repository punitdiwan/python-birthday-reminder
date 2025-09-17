from typing import List, Dict, Any
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from contextlib import contextmanager
import logging
import os

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database connection pool
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "dbname=postgres user=postgres password=your-super-secret-and-long-postgres-password host=studio.maitretech.com port=5432"
)
pool: ConnectionPool = ConnectionPool(conninfo=DATABASE_URL, min_size=1, max_size=10)

# Context manager for database connections: Get a connection from the pool
@contextmanager
def _get_db_connection() -> Any:
    conn = pool.getconn()
    try:
        logger.info("Databse Connected")
        yield conn  # <-- give back the connection to the caller
    finally:
        pool.putconn(conn)   # <-- always run after `with` block ends

# Execute a query and return results as a list of dictionaries
def execute_query(query: str, params: tuple = ()) -> List[Dict[str, Any]]:
    """
    Execute a SQL query and return results as list of dictionaries.
    Uses connection pooling for efficiency.
    """
    logger.info(f"Executing query: {query} with params: {params}")
    try:    
        with _get_db_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(query, params)
                results = cur.fetchall()
                return results
    except Exception as e:
        logger.error(f"Error executing query: {e}")
        return []

__all__ = ["execute_query"]  # only this is public

