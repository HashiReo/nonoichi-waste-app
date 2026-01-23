from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from backend.app.db.seed_schedule import normalize_text  # 既存の正規化を流用

BACKEND_DIR = Path(__file__).resolve().parents[1]  # backend/app
DB_PATH = BACKEND_DIR / "data" / "db" / "nonoichi_waste.db"




@dataclass
class ItemHit:
    name: str
    category: str
    note: str


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def find_item_exact(conn: sqlite3.Connection, query: str) -> ItemHit | None:
    qn = normalize_text(query)
    row = conn.execute(
        """
        SELECT i.name, c.name, COALESCE(i.note,'')
        FROM items i
        JOIN categories c ON c.category_id = i.category_id
        WHERE i.name_norm = ?
        LIMIT 1
        """,
        (qn,),
    ).fetchone()
    if not row:
        return None
    return ItemHit(*row)


def find_item_alias(conn: sqlite3.Connection, query: str) -> ItemHit | None:
    qn = normalize_text(query)
    row = conn.execute(
        """
        SELECT i.name, c.name, COALESCE(i.note,'')
        FROM item_aliases a
        JOIN items i ON i.item_id = a.item_id
        JOIN categories c ON c.category_id = i.category_id
        WHERE a.alias_norm = ?
        LIMIT 1
        """,
        (qn,),
    ).fetchone()
    if not row:
        return None
    return ItemHit(*row)


def suggest_items_prefix(conn: sqlite3.Connection, query: str, k: int = 10) -> list[ItemHit]:
    # SQLiteだけで軽い候補提示（前方一致）
    # 本格あいまい検索は後でRapidFuzz等でやる
    qn = normalize_text(query)
    rows = conn.execute(
        """
        SELECT i.name, c.name, COALESCE(i.note,'')
        FROM items i
        JOIN categories c ON c.category_id = i.category_id
        WHERE i.name_norm LIKE ?
        ORDER BY LENGTH(i.name_norm) ASC
        LIMIT ?
        """,
        (qn + "%", k),
    ).fetchall()
    return [ItemHit(*r) for r in rows]


def main():
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("text", help="品目名（例: ペットボトル）")
    p.add_argument("--k", type=int, default=10, help="候補数")
    args = p.parse_args()

    conn = connect()
    try:
        hit = find_item_exact(conn, args.text) or find_item_alias(conn, args.text)
        if hit:
            print("HIT:", hit)
            return

        print("NO HIT. Suggestions:")
        for s in suggest_items_prefix(conn, args.text, k=args.k):
            print(" -", s)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
