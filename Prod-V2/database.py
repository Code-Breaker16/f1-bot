from db import get_connection, release_connection


def execute(query, params=None):

    conn = get_connection()
    cur = conn.cursor()

    try:
        cur.execute(query, params)

    finally:
        cur.close()
        release_connection(conn)


def execute_commit(query, params=None):

    conn = get_connection()
    cur = conn.cursor()

    try:

        cur.execute(query, params)

        conn.commit()

    except Exception:

        conn.rollback()

        raise

    finally:

        cur.close()

        release_connection(conn)


def fetchone(query, params=None):

    conn = get_connection()
    cur = conn.cursor()

    try:

        cur.execute(query, params)

        return cur.fetchone()

    finally:

        cur.close()

        release_connection(conn)


def fetchall(query, params=None):

    conn = get_connection()
    cur = conn.cursor()

    try:

        cur.execute(query, params)

        return cur.fetchall()

    finally:

        cur.close()

        release_connection(conn)