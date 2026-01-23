from __future__ import annotations

import sqlite3
from datetime import datetime, date, timedelta
from pathlib import Path
import json

import yaml
import hashlib
import re
import unicodedata
import pandas as pd

# backend/ を基準にパスを決める
BACKEND_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BACKEND_DIR / "data"
EXPORT_DIR = DATA_DIR / "export"
DB_PATH = DATA_DIR / "db" / "nonoichi_waste.db"
SCHEDULE_PATH = DATA_DIR / "manual" / "schedule_r7.yaml"

WEEKDAY_MAP = {"MON": 0, "TUE": 1, "WED": 2, "THU": 3, "FRI": 4, "SAT": 5, "SUN": 6}

def generate_dates(rule: dict, start: date, end: date) -> list[date]:
    rtype = rule["type"]
    out: list[date] = []

    if rtype == "weekly":
        weekdays = [WEEKDAY_MAP[w] for w in rule["weekdays"]]
        d = start
        while d <= end:
            if d.weekday() in weekdays:
                out.append(d)
            d += timedelta(days=1)

    elif rtype == "month_dates":
        months = rule["months"]
        for ym, days in months.items():
            y, m = map(int, ym.split("-"))
            for day in days:
                d = date(y, m, int(day))
                if start <= d <= end:
                    out.append(d)
    else:
        raise ValueError(f"unknown rule type: {rtype}")

    return sorted(set(out))

def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def load_schedule() -> dict:
    text = SCHEDULE_PATH.read_text(encoding="utf-8")
    return yaml.safe_load(text)

def upsert_source(conn: sqlite3.Connection, schedule: dict) -> str:
    pdf = schedule["sources"]["pdf"]
    source_id = "src_pdf_r7"
    conn.execute(
        """
        INSERT OR REPLACE INTO sources(source_id, source_type, title, file_path, fetched_at)
        VALUES(?, ?, ?, ?, ?)
        """,
        (
            source_id,
            "pdf",
            pdf["title"],
            pdf["file_path"],
            pdf.get("fetched_at") or datetime.utcnow().isoformat(timespec="seconds"),
        )
    )
    conn.commit()
    return source_id


def normalize_text(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "").strip()
    s = re.sub(r"\s+", " ", s)
    return s

def make_id(prefix: str, seed: str, n: int = 12) -> str:
    h = hashlib.sha1(normalize_text(seed).encode("utf-8")).hexdigest()[:n]
    return f"{prefix}_{h}"

def upsert_categories(conn: sqlite3.Connection, schedule: dict, source_id: str) -> None:
    now = datetime.utcnow().isoformat(timespec="seconds")
    for c in schedule["categories"]:
        name = c["name"]
        deadline_time = c.get("deadline_time")
        category_id = make_id("cat", name)
        conn.execute(
            """
            INSERT OR REPLACE INTO categories(category_id, name, deadline_time, source_id, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (category_id, name, deadline_time, source_id, now),
        )
    conn.commit()

def upsert_areas_and_groups(conn: sqlite3.Connection, schedule: dict, source_id: str) -> None:
    now = datetime.utcnow().isoformat(timespec="seconds")

    # 1) area_groupsに出てくる地区名を集めて areas を作る（YAMLのareasが空でもOK）
    area_names = set()
    for g in schedule["area_groups"]:
        for a in g.get("areas", []) or []:
            area_names.add(a)

    # areas upsert
    area_id_by_name = {}
    for name in sorted(area_names):
        area_id = make_id("area", name)
        area_id_by_name[name] = area_id
        conn.execute(
            """
            INSERT OR REPLACE INTO areas(area_id, name, source_id, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (area_id, name, source_id, now),
        )

    # 2) area_groups upsert + members
    for g in schedule["area_groups"]:
        gid = g["id"]   # YAMLのidをそのまま使う（説明しやすい）
        gname = g["name"]
        conn.execute(
            """
            INSERT OR REPLACE INTO area_groups(group_id, name, source_id, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (gid, gname, source_id, now),
        )
        # membersは入れ直し（再実行できるように）
        conn.execute("DELETE FROM area_group_members WHERE group_id=?", (gid,))
        for area_name in g.get("areas", []) or []:
            conn.execute(
                "INSERT OR IGNORE INTO area_group_members(group_id, area_id) VALUES (?, ?)",
                (gid, area_id_by_name[area_name]),
            )

    conn.commit()

def upsert_rules_and_events(conn: sqlite3.Connection, schedule: dict, source_id: str) -> None:
    now = datetime.utcnow().isoformat(timespec="seconds")
    start = date.fromisoformat(schedule["effective_start"])
    end = date.fromisoformat(schedule["effective_end"])

    # category_id を引けるように map を作る
    cat_id_by_name = {
        row[0]: row[1]
        for row in conn.execute("SELECT name, category_id FROM categories").fetchall()
    }

    for r in schedule["collection_rules"]:
        category_name = r["category"]
        group_id = r["area_group_id"]
        category_id = cat_id_by_name[category_name]

        # rule_id は内容で安定生成（同じYAMLなら同じID）
        rid = make_id("rule", f"{group_id}|{category_name}|{r['rule']['type']}")

        # rule_json：DBに“ルールそのもの”を保存（説明・更新に役立つ）
        rule_json = json.dumps(r["rule"], ensure_ascii=False)

        note = None
        if "notes" in r and r["notes"] is not None:
            note = json.dumps(r["notes"], ensure_ascii=False)

        conn.execute(
            """
            INSERT OR REPLACE INTO collection_rules(
              rule_id, group_id, category_id, rule_type, rule_json,
              effective_start, effective_end, note, source_id, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                rid,
                group_id,
                category_id,
                r["rule"]["type"],
                rule_json,
                schedule["effective_start"],
                schedule["effective_end"],
                note,
                source_id,
                now,
            ),
        )

        # events：groupのmembers（area）に対して日付を展開
        dates = generate_dates(r["rule"], start, end)

        # deadline_time は categories から取る（DBの値を使用）
        deadline_time = conn.execute(
            "SELECT deadline_time FROM categories WHERE category_id=?",
            (category_id,),
        ).fetchone()[0]

        area_ids = [row[0] for row in conn.execute(
            "SELECT area_id FROM area_group_members WHERE group_id=?",
            (group_id,),
        ).fetchall()]

        for area_id in area_ids:
            for d in dates:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO collection_events(
                      area_id, category_id, collection_date, deadline_time, note, source_id
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        area_id,
                        category_id,
                        d.isoformat(),
                        deadline_time,
                        note,
                        source_id,
                    ),
                )

    conn.commit()

def export_csv(conn: sqlite3.Connection) -> None:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    tables = [
        "sources",
        "categories",
        "areas",
        "area_groups",
        "area_group_members",
        "collection_rules",
        "collection_events",
    ]
    for t in tables:
        df = pd.read_sql_query(f"SELECT * FROM {t}", conn)
        df.to_csv(EXPORT_DIR / f"{t}.csv", index=False, encoding="utf-8-sig")

def main() -> None:
    if not SCHEDULE_PATH.exists():
        raise FileNotFoundError(f"schedule not found: {SCHEDULE_PATH}")

    schedule = load_schedule()
    conn = connect()

    source_id = upsert_source(conn, schedule)
    upsert_categories(conn, schedule, source_id)
    upsert_areas_and_groups(conn, schedule, source_id)
    upsert_rules_and_events(conn, schedule, source_id)
    export_csv(conn)


    conn.close()
    print(f"✅ seeded sources from {SCHEDULE_PATH.name} as {source_id}")

if __name__ == "__main__":
    main()