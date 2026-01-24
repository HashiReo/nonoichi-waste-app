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
import calendar

# backend/ を基準にパスを決める
BACKEND_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BACKEND_DIR / "data"
EXPORT_DIR = DATA_DIR / "export"
DB_PATH = DATA_DIR / "db" / "nonoichi_waste.db"
SCHEDULE_PATH = DATA_DIR / "manual" / "schedule_r7.yaml"
RAW_ITEMS_CSV = DATA_DIR / "raw" / "nonoichi_garbage.csv"

WEEKDAY_MAP = {"MON": 0, "TUE": 1, "WED": 2, "THU": 3, "FRI": 4, "SAT": 5, "SUN": 6}

def nth_weekday_of_month(year: int, month: int, weekday: int, nth: int) -> date | None:
    # weekday: 0=Mon..6=Sun
    count = 0
    for day in range(1, calendar.monthrange(year, month)[1] + 1):
        d = date(year, month, day)
        if d.weekday() == weekday:
            count += 1
            if count == nth:
                return d
    return None

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

    elif rtype == "monthly_nth_weekday":
        weekday = WEEKDAY_MAP[rule["weekday"]]
        nth = int(rule["nth"])
        y, m = start.year, start.month
        while (y, m) <= (end.year, end.month):
            d = nth_weekday_of_month(y, m, weekday, nth)
            if d and start <= d <= end:
                out.append(d)
            m += 1
            if m == 13:
                y += 1
                m = 1

    elif rtype == "monthly_multiple_nth_weekday":
        weekday = WEEKDAY_MAP[rule["weekday"]]
        nth_list = [int(x) for x in rule["nth"]]
        y, m = start.year, start.month
        while (y, m) <= (end.year, end.month):
            for nth in nth_list:
                d = nth_weekday_of_month(y, m, weekday, nth)
                if d and start <= d <= end:
                    out.append(d)
            m += 1
            if m == 13:
                y += 1
                m = 1
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
        category_id = c["id"]
        conn.execute(
            """
            INSERT OR REPLACE INTO categories(category_id, name, deadline_time, disposal_instructions, source_id, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (category_id, name, deadline_time, c.get("disposal_instructions"), source_id, now),
        )
    conn.commit()

def upsert_schedule_groups(conn: sqlite3.Connection, schedule: dict, source_id: str) -> None:
    now = datetime.utcnow().isoformat(timespec="seconds")
    for g in schedule["schedule_groups"]:
        sg_id = g["id"]
        category_id = g["category_id"]
        name = g["name"]
        rule = g["rule"]
        rule_type = rule["type"]
        rule_json = json.dumps(rule, ensure_ascii=False)

        # YAMLは notes / note どちらでも受けられるようにする
        note_obj = g.get("notes", g.get("note"))
        note = json.dumps(note_obj, ensure_ascii=False) if isinstance(note_obj, (dict, list)) else note_obj

        conn.execute(
            """
            INSERT OR REPLACE INTO schedule_groups(
              schedule_group_id, category_id, name, rule_type, rule_json, note, source_id, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (sg_id, category_id, name, rule_type, rule_json, note, source_id, now),
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
            INSERT OR REPLACE INTO area_groups(area_group_id, name, source_id, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (gid, gname, source_id, now),
        )
        # membersは入れ直し（再実行できるように）
        conn.execute("DELETE FROM area_group_members WHERE area_group_id=?", (gid,))
        for area_name in g.get("areas", []) or []:
            conn.execute(
                "INSERT OR IGNORE INTO area_group_members(area_group_id, area_id) VALUES (?, ?)",
                (gid, area_id_by_name[area_name]),
            )

    conn.commit()

def upsert_area_group_schedule_links(conn: sqlite3.Connection, schedule: dict) -> None:
    # schedule_groups の category_id 整合チェック用
    sg_cat = {g["id"]: g["category_id"] for g in schedule["schedule_groups"]}

    for link in schedule["area_group_schedule_links"]:
        agid = link["area_group_id"]

        # 再実行できるようにいったん削除
        conn.execute("DELETE FROM area_group_schedule_links WHERE area_group_id=?", (agid,))

        for s in link["schedules"]:
            sgid = s["schedule_id"]
            # YAMLに書かれた category_id と schedule_groups.category_id が一致するか検証
            if sg_cat.get(sgid) != s["category_id"]:
                raise ValueError(f"link mismatch: area_group={agid} schedule={sgid} category_id={s['category_id']} != {sg_cat.get(sgid)}")

            conn.execute(
                """
                INSERT OR IGNORE INTO area_group_schedule_links(area_group_id, schedule_group_id)
                VALUES (?, ?)
                """,
                (agid, sgid),
            )
    conn.commit()

def upsert_events_from_links(conn: sqlite3.Connection, schedule: dict, source_id: str) -> None:
    start = date.fromisoformat(schedule["effective_start"])
    end = date.fromisoformat(schedule["effective_end"])

    # 既存events（このsource分）を削除してから再生成（ルール変更に強い）
    conn.execute("DELETE FROM collection_events WHERE source_id=?", (source_id,))

    # schedule_group_id -> rule/category
    sg_by_id = {g["id"]: g for g in schedule["schedule_groups"]}

    # category_id -> deadline_time
    deadline_by_cat = {
        row[0]: row[1]
        for row in conn.execute("SELECT category_id, deadline_time FROM categories").fetchall()
    }

    # area_group_id -> area_ids
    area_ids_by_group = {}
    for row in conn.execute("SELECT area_group_id, area_id FROM area_group_members").fetchall():
        area_ids_by_group.setdefault(row[0], []).append(row[1])

    # DB links を使って展開（YAMLから直接でも良いが、DBに入ったものを元にした方が整合チェックしやすい）
    links = conn.execute("SELECT area_group_id, schedule_group_id FROM area_group_schedule_links").fetchall()

    for area_group_id, schedule_group_id in links:
        g = sg_by_id[schedule_group_id]
        category_id = g["category_id"]
        rule = g["rule"]
        dates = generate_dates(rule, start, end)

        deadline_time = deadline_by_cat.get(category_id)
        note_obj = g.get("notes", g.get("note"))
        note = json.dumps(note_obj, ensure_ascii=False) if isinstance(note_obj, (dict, list)) else note_obj

        for area_id in area_ids_by_group.get(area_group_id, []):
            for d in dates:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO collection_events(
                      area_id, category_id, collection_date, deadline_time, note, source_id
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (area_id, category_id, d.isoformat(), deadline_time, note, source_id),
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
    "schedule_groups",
    "area_group_schedule_links",
    "collection_events",
    "items",
    "item_aliases",
    ]
    for t in tables:
        df = pd.read_sql_query(f"SELECT * FROM {t}", conn)
        df.to_csv(EXPORT_DIR / f"{t}.csv", index=False, encoding="utf-8-sig")

def seed_items_from_raw_csv(conn: sqlite3.Connection, source_id: str) -> None:
    if not RAW_ITEMS_CSV.exists():
        print(f"⚠️ raw items csv not found: {RAW_ITEMS_CSV} (skip)")
        return

    df = pd.read_csv(RAW_ITEMS_CSV)

    now = datetime.utcnow().isoformat(timespec="seconds")

    # DBに存在するカテゴリ名→category_id
    cat_id_by_name = {
        row[0]: row[1]
        for row in conn.execute("SELECT name, category_id FROM categories").fetchall()
    }

    inserted = 0
    updated = 0

    for _, row in df.iterrows():
        item_name = str(row["item_name"])
        category_name = str(row["category"])
        if category_name == "自己処理" or category_name == "古紙（チラシ・雑誌・本・コピー用紙類）" or category_name == "紙パック" or category_name == "未設定" or category_name == "古着・布類" or category_name == "古紙（新聞紙）" or category_name == "古紙（段ボール）" or category_name == "保留中":
            continue

        note = "" if pd.isna(row.get("note")) else str(row.get("note"))

        # collector側のカテゴリ名がschedule側に存在しない可能性があるので、
        # 無ければ categories に追加して整合を保つ
        if category_name not in cat_id_by_name:
            raise ValueError(f"Unknown category in items CSV: {category_name}")

        item_id = make_id("item", item_name + "|" + category_name)
        name_norm = normalize_text(item_name)
        category_id = cat_id_by_name[category_name]

        # UPSERT（同じname_normが来たら更新）
        cur = conn.execute(
            """
            INSERT INTO items(item_id, name, name_norm, category_id, note, source_id, source_url, fetched_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(name_norm) DO UPDATE SET
              category_id=excluded.category_id,
              note=excluded.note,
              updated_at=excluded.updated_at
            """,
            (
                item_id,
                item_name,
                name_norm,
                category_id,
                note,
                source_id,
                "https://gb.hn-kouiki.jp/nonoichi",
                now,
                now,
            ),
        )
        # sqlite3のrowcountは信用しにくいので概算（今回は確認だけできればOK）
        inserted += 1

    conn.commit()
    print(f"✅ seeded items from raw csv: {inserted} rows")

def main() -> None:
    if not SCHEDULE_PATH.exists():
        raise FileNotFoundError(f"schedule not found: {SCHEDULE_PATH}")

    schedule = load_schedule()
    conn = connect()

    source_id = upsert_source(conn, schedule)
    upsert_categories(conn, schedule, source_id)
    upsert_areas_and_groups(conn, schedule, source_id)
    upsert_schedule_groups(conn, schedule, source_id)
    upsert_area_group_schedule_links(conn, schedule)
    upsert_events_from_links(conn, schedule, source_id)
    # web辞典由来のsource（1行入れる）
    conn.execute(
        "INSERT OR REPLACE INTO sources(source_id, source_type, title, url, fetched_at) VALUES (?,?,?,?,datetime('now'))",
        ("src_web_dict", "web", "分別辞典", "https://gb.hn-kouiki.jp/nonoichi",),
    )
    conn.commit()

    seed_items_from_raw_csv(conn, "src_web_dict")
    export_csv(conn)


    conn.close()
    print(f"✅ seeded sources from {SCHEDULE_PATH.name} as {source_id}")

if __name__ == "__main__":
    main()