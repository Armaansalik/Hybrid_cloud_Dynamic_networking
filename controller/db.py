#!/usr/bin/env python3
"""SQLite persistence layer for the Hybrid Cloud-SDN controller."""
import sqlite3
import os
import time

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'events.db')


def get_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL,
            time_str TEXT,
            message TEXT
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS load_samples (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL,
            time_str TEXT,
            backend TEXT,
            load_bytes_per_sec REAL
        )
    ''')
    conn.commit()
    return conn


_conn = get_connection()


def log_event(message):
    now = time.time()
    _conn.execute(
        'INSERT INTO events (ts, time_str, message) VALUES (?, ?, ?)',
        (now, time.strftime('%H:%M:%S', time.localtime(now)), message)
    )
    _conn.commit()


def log_load_sample(backend, load):
    now = time.time()
    _conn.execute(
        'INSERT INTO load_samples (ts, time_str, backend, load_bytes_per_sec) VALUES (?, ?, ?, ?)',
        (now, time.strftime('%H:%M:%S', time.localtime(now)), backend, load)
    )
    _conn.commit()


def recent_events(limit=15):
    cur = _conn.execute(
        'SELECT time_str, message FROM events ORDER BY id DESC LIMIT ?', (limit,)
    )
    return [{'time': row[0], 'message': row[1]} for row in cur.fetchall()]


def event_count():
    cur = _conn.execute('SELECT COUNT(*) FROM events')
    return cur.fetchone()[0]


def sample_count():
    cur = _conn.execute('SELECT COUNT(*) FROM load_samples')
    return cur.fetchone()[0]


def get_long_history(minutes=60, bucket_seconds=60):
    """Return load samples from the last `minutes`, averaged into
    `bucket_seconds`-wide time buckets per backend -- gives a smooth
    long-term chart instead of thousands of raw points."""
    cutoff = time.time() - (minutes * 60)
    cur = _conn.execute(
        'SELECT ts, backend, load_bytes_per_sec FROM load_samples WHERE ts >= ? ORDER BY ts ASC',
        (cutoff,)
    )
    rows = cur.fetchall()

    buckets = {}
    for ts, backend, load in rows:
        bucket_key = int(ts // bucket_seconds) * bucket_seconds
        buckets.setdefault(bucket_key, {}).setdefault(backend, []).append(load)

    result = []
    for bucket_key in sorted(buckets.keys()):
        entry = {'time': time.strftime('%H:%M:%S', time.localtime(bucket_key))}
        for b in ('h2', 'h3', 'h4'):
            vals = buckets[bucket_key].get(b, [])
            entry[b] = round(sum(vals) / len(vals), 1) if vals else 0
        result.append(entry)
    return result
