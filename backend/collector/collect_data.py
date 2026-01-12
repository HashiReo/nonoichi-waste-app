# /backend/collector/collect_data.py
# 野々市市分別辞典データ収集スクリプト

import pandas as pd
import requests
import time
import os
import random
import re
from bs4 import BeautifulSoup

# 保存先の設定
# os.path.dirname(__file__)は、このファイルが置かれているディレクトリを指す
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), '../data/raw')
OUTPUT_FILE = os.path.join(OUTPUT_DIR, 'nonoichi_garbage.csv')
FAILED_PAGES_FILE = os.path.join(OUTPUT_DIR, 'failed_pages.txt')

# 野々市市の分別辞典URL(ベースURL)
BASE_URL = "https://gb.hn-kouiki.jp/nonoichi"

# ページ総数をループする形式で取得
# データが取れなくなったら終了
START_PAGE = 1
MAX_PAGE = 90 # 2026/01時点で84ページだが保険

# User-Agent: どんなクライアントがアクセスしているか
# Mozilla/5.0: 一般的なブラウザを装う
# NonoichiWasteCollector/1.0: 独自のクライアント名
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; NonoichiWasteCollector/1.0)"
}

EXPECTED_COLS = {"品　目", "分別種類"}

# ================
# ユーティリティ
# ================

def parse_total_pages(html: str) -> int | None:
    # HTML内の「全〇ページ/件数：〇件」から総ページ数を取得
    match = re.search(r"全\s*([0-9]+)\s*ページ", html)
    return int(match.group(1)) if match else None

def fetch_page(session: requests.Session, page_num:int, max_retries:int=3) -> str:
    # BASE_URLにpage_num（START_PAGE）を渡す
    params = {"page": page_num}
    # 失敗原因を保存
    last_err = None

    for attempt in range(1, max_retries + 1):
        try:
            r = session.get(BASE_URL, params=params, timeout=10)
            # HTTP 4xx/5xxの時に発生
            r.raise_for_status()
            # HTML文字列を返す
            print(f" -> Page {page_num} 通信成功")
            return r.text
        # ネットワーク/タイムアウト/4xx,5xxエラー
        except requests.exceptions.RequestException as e:
            last_err = e
            # バックオフ
            time.sleep(1.0 * attempt + random.random())
            print(f" -> Attempt {attempt} failed: {e} - retrying...")
    raise last_err # 全リトライ失敗時

def parse_table_rows(html:str) -> pd.DataFrame:
    soup = BeautifulSoup(html, "lxml")

    table = soup.select_one("table.table.table-striped.table-hover")
    if table is None:
        ValueError("target table not found")

    rows = []
    for tr in table.select("tbody tr"):
        tds = tr.find_all("td")
        if len(tds) < 2:
            continue

        item = tds[0].get_text(" ", strip=True)
        # category: 2つ目のtd以降
        td_category = [t.strip() for t in tds[1].find_all(string=True, recursive=False) if t.strip()]
        category = td_category[0] if td_category else tds[1].get_text(" ", strip=True)

        # note: divがあればテキスト化
        div = tds[1].find("div")
        note = div.get_text("\n", strip=True) if div else ""

        rows.append({
            "item_name": item,
            "category": category,
            "note": note,
        })

    return pd.DataFrame(rows)

def normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    # 目的列チェック
    if not EXPECTED_COLS.issubset(set(df.columns)):
        raise ValueError(f"Unexpected columns: {df.columns.tolist()}")
    
def atomic_write_csv(df: pd.DataFrame, path: str, encoding: str = "utf-8-sig") -> None:
    """
    一時ファイルに書いてから置換する（途中で落ちてもCSVが壊れにくい）
    """
    tmp = path + ".tmp"
    df.to_csv(tmp, index=False, encoding=encoding)
    os.replace(tmp, path)


# ================
# メイン処理
# ================

def main():
    print("=== データ収集を開始します (ページ番号順) ===")
    os.makedirs(OUTPUT_DIR, exist_ok = True)

    all_data =[]
    error_count = 0 # 連続エラーカウント
    failed_pages = [] # 取得失敗ページリスト

    with requests.Session() as session:
        session.headers.update(HEADERS)


    # 1ページ目を処理
    try:
        # BASE_URLから総ページ数を取得する
        print(f"[Page {START_PAGE}] を取得中...")
        html1 = fetch_page(session, START_PAGE)
        total_pages = parse_total_pages(html1) or MAX_PAGE
        print(f"総ページ数（推定/取得）: {total_pages}")

        # HTML文字列内の<table>タグを表としてDataFrameに読み込む
        df1 = parse_table_rows(html1)
        if len(df1) == 0:
            print("[Page 1]データがありません。終了します。")
            return
        all_data.append(df1.assign(page=START_PAGE))
        print(f"[Page {START_PAGE}] -> {len(df1)} 件のデータを見つけました。")

    except ValueError as e:
        print(f"[Page {START_PAGE}] -> 表データが見つかりません。終了します。")

    # 2ページ目以降をループ処理
    for page_num in range(START_PAGE + 1, total_pages + 1):
        print(f"[Page {page_num}] を取得中...")

        # アクセスマナー
        time.sleep(1.0)

        # 取得
        try:
            html = fetch_page(session, page_num)
        except requests.exceptions.RequestException as e:
            failed_pages.append(page_num)
            print(f"[Page {page_num}] -> 取得失敗: {e}")
            if len(error_count) >= 4:
                print(" -> 連続エラーが多いため終了します。")
                break
            else:
                continue
        
        # 解析
        try:
            df = parse_table_rows(html)
        except ValueError as e:
            print(f"[Page {page_num}] -> 表データが見つかりません。終了します。")
            failed_pages.append(page_num)
            print("HTML構造が想定外の可能性があるため停止します。")
            break

        # 終了判定
        if len(df) == 0:
            print(f"[Page {page_num}] -> データがありません。終了します。")
            break

        all_data.append(df.assign(page=page_num))
        print(f"[Page {page_num}] -> {len(df)} 件のデータを見つけました。")

    # 保存処理
    if len(all_data) > 0:
        print("\n=== 全データを結合しています ===")
        final_df = pd.concat(all_data, ignore_index=True)
        atomic_write_csv(final_df, OUTPUT_FILE)
        print(f"保存完了！場所: {OUTPUT_FILE}")
        print(f"データ総数: {len(final_df)} 件")

        # 失敗ページを記録
        if failed_pages:
            with open(FAILED_PAGES_FILE, "w", encoding="utf-8") as f:
                for p in failed_pages:
                    f.write(f"{p}\n")
            print(f"取得失敗ページを保存しました: {FAILED_PAGES_FILE} (件数: {len(failed_pages)}")
        # 先頭確認
        print("先頭5件")        
        print(final_df.head())
    else:
        print("取得したデータがありません。")

if __name__ == "__main__":
    main()