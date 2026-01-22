from __future__ import annotations

import sqlite3
from pathlib import Path

# backend/ を基準にパスを決める
BACKEND_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BACKEND_DIR / "data"
DB_PATH = DATA_DIR / "db" / "nonoichi_waste.db"
SCHEMA_PATH = Path(__file__).with_name("schema.sql")

def connect(db_path: Path = DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def apply_schema(conn: sqlite3.Connection, schema_path: Path= SCHEMA_PATH) -> None:
    sql = schema_path.read_text(encoding="utf-8")
    conn.executescript(sql)
    conn.commit()

def main() -> None:
    if not SCHEMA_PATH.exists():
        raise FileNotFoundError(f"schema.sql not found: {SCHEMA_PATH}")
    
    conn = connect()
    apply_schema(conn)
    conn.close()

    print(f"✅ created: {DB_PATH}")

if __name__ == "__main__":
    main()