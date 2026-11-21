"""Metadata index. JSON/NPZ recordings remain usable if the index is lost."""
import json
import sqlite3
from contextlib import closing
from pathlib import Path


class Database:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as con, con:
            con.execute('''CREATE TABLE IF NOT EXISTS recordings (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TEXT NOT NULL,
                duration_ms REAL NOT NULL, frame_count INTEGER NOT NULL,
                directory TEXT UNIQUE NOT NULL, metadata_json TEXT NOT NULL)''')

    def add(self, metadata, directory):
        with closing(sqlite3.connect(self.path)) as con, con:
            con.execute('INSERT INTO recordings VALUES (?,?,?,?,?,?,?)', (
                metadata['id'], metadata['name'], metadata['created_at'],
                metadata['duration_ms'], metadata['frame_count'],
                str(Path(directory).resolve()), json.dumps(metadata, allow_nan=False)))

    def lookup(self, name_or_id):
        with closing(sqlite3.connect(self.path)) as con:
            con.row_factory = sqlite3.Row
            rows = con.execute('SELECT * FROM recordings WHERE id=? OR name=? '
                               'ORDER BY created_at DESC', (name_or_id, name_or_id)).fetchall()
        return [dict(row) for row in rows]
