# database.py
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Replace these credentials with your actual database parameters
DB_HOST = os.getenv("POSTGRES_HOST", "localhost")
DB_NAME = os.getenv("POSTGRES_DB", "assignment_db")  # Default database name for testing
DB_USER = os.getenv("POSTGRES_USER", "postgres")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "password")
DB_PORT = os.getenv("POSTGRES_PORT", "5432")

@contextmanager
def get_db_connection():
    """Context manager ensuring safe allocation and cleanup of database connections."""
    conn = None
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            port=DB_PORT
        )
        yield conn
    except Exception as e:
        print(f"Database connection establishment failure: {str(e)}")
        raise e
    finally:
        if conn:
            conn.close()