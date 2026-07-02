import os
from dotenv import load_dotenv
from psycopg2.pool import SimpleConnectionPool

load_dotenv(".env.test")

DATABASE_URL = os.getenv("DATABASE_URL")

db_pool = SimpleConnectionPool(
    minconn=1,
    maxconn=10,
    dsn=DATABASE_URL
)

def get_connection():
    return db_pool.getconn()

def release_connection(conn):
    db_pool.putconn(conn)

def close_pool():
    db_pool.closeall()

import atexit

atexit.register(close_pool)