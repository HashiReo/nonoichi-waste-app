-- backend/app/db/schema.sql

PRAGMA foreign_keys = ON;

-- ===========================================================
-- 出典・更新管理
-- ===========================================================
CREATE TABLE IF NOT EXISTS sources (
    source_id   TEXT PRIMARY KEY,
    source_type TEXT NOT NULL, -- web|pdf|manual|generated
    title       TEXT NOT NULL,
    url         TEXT,          -- 取得元URL
    file_path   TEXT,          -- 取得元ファイルパス
    fetched_at  TEXT,          -- 取得日時
    sha256      TEXT           -- ファイルや内容のハッシュ（改ざん検知・同一性確認に便利）
);

-- ===========================================================
-- 家庭ごみ区分（締切時間）
-- ===========================================================
CREATE TABLE IF NOT EXISTS categories (
    category_id           TEXT PRIMARY KEY,
    name                  TEXT NOT NULL UNIQUE,
    deadline_time         TEXT, -- ex) 07:00 / 07:30
    disposal_instructions TEXT,
    source_id             TEXT,
    updated_at            TEXT,
    FOREIGN KEY(source_id) REFERENCES sources(source_id)
);
-- ===========================================================
-- 地区
-- ===========================================================
CREATE TABLE IF NOT EXISTS areas (
    area_id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    note TEXT,
    source_id TEXT,
    updated_at TEXT,
    FOREIGN KEY(source_id) REFERENCES sources(source_id)
);
-- ===========================================================
-- 地区グループ
-- ===========================================================
CREATE TABLE IF NOT EXISTS area_groups (
  area_group_id TEXT PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  note TEXT,
  source_id TEXT,
  updated_at TEXT,
  FOREIGN KEY(source_id) REFERENCES sources(source_id)
);
-- ===========================================================
-- 地区グループに含まれる地区一覧
-- ===========================================================
CREATE TABLE IF NOT EXISTS area_group_members (
  area_group_id TEXT NOT NULL,
  area_id TEXT NOT NULL,
  PRIMARY KEY (area_group_id, area_id),
  FOREIGN KEY(area_group_id) REFERENCES area_groups(area_group_id) ON DELETE CASCADE,
  FOREIGN KEY(area_id) REFERENCES areas(area_id) ON DELETE CASCADE
);
-- ===========================================================
-- 収集スケジュールパターン
-- ===========================================================
CREATE TABLE IF NOT EXISTS schedule_groups (
    schedule_group_id TEXT PRIMARY KEY,
    category_id TEXT NOT NULL,
    name TEXT NOT NULL UNIQUE,
    rule_type TEXT NOT NULL, -- weekly | month_dates
    note TEXT,
    source_id TEXT,
    updated_at TEXT,
    FOREIGN KEY(source_id) REFERENCES sources(source_id),
    FOREIGN KEY(category_id) REFERENCES categories(category_id) ON DELETE CASCADE
);
-- ===========================================================
-- 収集パターングループ(schedule_groups) ←→ 地区グループ(area_groups) の対応
-- ===========================================================
CREATE TABLE IF NOT EXISTS area_group_schedule_links (
  area_group_id TEXT NOT NULL,
  schedule_group_id TEXT NOT NULL,
  PRIMARY KEY (area_group_id, schedule_group_id),
  FOREIGN KEY(area_group_id) REFERENCES area_groups(area_group_id) ON DELETE CASCADE,
  FOREIGN KEY(schedule_group_id) REFERENCES schedule_groups(schedule_group_id) ON DELETE CASCADE
);

-- 収集ルールテーブル
CREATE TABLE IF NOT EXISTS collection_rules (
    rule_id TEXT PRIMARY KEY,
    group_id TEXT NOT NULL,
    category_id TEXT NOT NULL,
    rule_type TEXT NOT NULL, -- weekly | month_dates
    rule_json TEXT NOT NULL, -- ルールの詳細をJSONで保存
    effective_start TEXT,
    effective_end TEXT,
    note TEXT,
    source_id TEXT,
    updated_at TEXT,
    FOREIGN KEY(group_id) REFERENCES area_groups(group_id) ON DELETE CASCADE,
    FOREIGN KEY(category_id) REFERENCES categories(category_id) ON DELETE CASCADE,
    FOREIGN KEY(source_id) REFERENCES sources(source_id)
);

-- アプリが最終的に引く「具体的な収集日（カレンダー）」
CREATE TABLE IF NOT EXISTS collection_events (
  event_id INTEGER PRIMARY KEY AUTOINCREMENT,
  area_id  TEXT NOT NULL,
  category_id TEXT NOT NULL,
  collection_date TEXT NOT NULL,    -- YYYY-MM-DD
  deadline_time   TEXT,             -- 例: 07:00/07:30
  note      TEXT,
  source_id TEXT,
  UNIQUE(area_id, category_id, collection_date),
  FOREIGN KEY(area_id) REFERENCES areas(area_id) ON DELETE CASCADE,
  FOREIGN KEY(category_id) REFERENCES categories(category_id) ON DELETE CASCADE,
  FOREIGN KEY(source_id) REFERENCES sources(source_id)
);

-- 分別辞典（collectorのCSVから入れる）
CREATE TABLE IF NOT EXISTS items (
  item_id   TEXT PRIMARY KEY,
  name      TEXT NOT NULL,
  name_norm TEXT NOT NULL UNIQUE,    -- 完全一致用（正規化キー）
  category_id TEXT NOT NULL,
  note      TEXT,
  source_id TEXT,
  source_url TEXT,
  fetched_at TEXT,
  updated_at TEXT,
  FOREIGN KEY(category_id) REFERENCES categories(category_id),
  FOREIGN KEY(source_id) REFERENCES sources(source_id)
);

-- 手入力時の同義語（PET→ペットボトルなど）
CREATE TABLE IF NOT EXISTS item_aliases (
  alias_id INTEGER PRIMARY KEY AUTOINCREMENT,
  item_id  TEXT NOT NULL,
  alias    TEXT NOT NULL,
  alias_norm TEXT NOT NULL UNIQUE,
  FOREIGN KEY(item_id) REFERENCES items(item_id) ON DELETE CASCADE
);

-- Phase2/3用：モデルのlabel→DBのIDの対応（将来のため）
CREATE TABLE IF NOT EXISTS model_label_maps (
  model_version TEXT NOT NULL,
  label_index   INTEGER NOT NULL,
  target_type   TEXT NOT NULL CHECK (target_type IN ('category','item')),
  target_id     TEXT NOT NULL,
  PRIMARY KEY(model_version, label_index)
);

CREATE INDEX IF NOT EXISTS idx_events_area_date ON collection_events(area_id, collection_date);
CREATE INDEX IF NOT EXISTS idx_items_category  ON items(category_id);