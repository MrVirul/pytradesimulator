"""Postgres access for the API process. One connection, guarded by a lock."""

import threading

import psycopg

from secure_api.app.config import database_url

_lock = threading.RLock()
_connection = None


def connection():
    global _connection
    with _lock:
        if _connection is None or _connection.closed:
            _connection = psycopg.connect(database_url())
        return _connection


def lock():
    return _lock
