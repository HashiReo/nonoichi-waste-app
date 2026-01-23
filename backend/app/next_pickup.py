from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from backend.app.query import normalize_text  # 既存の正規化を流用

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "db" / "nonoichi_waste.db"


@dataclass
class NextPickup:
    area: str
    category: str
    collection_date: str
    deadline_time: str


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def category_from_item(conn: sqlite3.Connection, item_name: str) -> str | None:
    qn = normalize_text(item_name)
    row = conn.execute(
        """
        SELECT c.name
        FROM items i
        JOIN categories c ON c.category_id = i.category_id
        WHERE i.name_norm = ?
        LIMIT 1
        """,
        (qn,),
    ).fetchone()
    return row[0] if row else None


def next_pickup(conn: sqlite3.Connection, area_name: str, category_name: str, today: str | None = None) -> NextPickup | None:
    if today is None:
        today = date.today().isoformat()

    row = conn.execute(
        """
        SELECT a.name, c.name, e.collection_date, e.deadline_time
        FROM collection_events e
        JOIN areas a ON a.area_id = e.area_id
        JOIN categories c ON c.category_id = e.category_id
        WHERE a.name = ?
          AND c.name = ?
          AND e.collection_date >= ?
        ORDER BY e.collection_date ASC
        LIMIT 1
        """,
        (area_name, category_name, today),
    ).fetchone()

    return NextPickup(*row) if row else None


def main():
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--area", required=True, help="地区名（例: 本町１丁目）")
    p.add_argument("--item", help="品目名（例: アイロン）")
    p.add_argument("--category", help="区分名（例: 一般ごみ）")
    p.add_argument("--today", help="YYYY-MM-DD（テスト用）")
    args = p.parse_args()

    if not args.item and not args.category:
        raise SystemExit("Either --item or --category is required")

    conn = connect()
    try:
        category = args.category
        if args.item:
            category = category_from_item(conn, args.item)
            if not category:
                raise SystemExit(f"Item not found: {args.item}")

        result = next_pickup(conn, args.area, category, today=args.today)
        if not result:
            print("No upcoming pickup found.")
            return
        print(result)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
