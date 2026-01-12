# /backend/collector/analyze_vategories.py
# 野々市市分別辞典カテゴリ分析スクリプト
# 実行 → 分類辞典データを読み込み、カテゴリ一覧を表示・保存

import pandas as pd
import os

# File Paths
INPUT_FILE = os.path.join(os.path.dirname(__file__), '../data/raw/nonoichi_garbage.csv')

# ================
# メイン処理
# ================

def main():
    # CSV読み込み
    df = pd.read_csv(INPUT_FILE)

    # カテゴリ（分類種類）のユニーク値（重複無し値）を取得
    unique_categories = df['category'].unique()
    print(f"=== カテゴリ一覧（全{len(unique_categories)}種類 ===")

    # 分類辞典の各カテゴリごとの件数を表示（意味あるかは知らんが）
    sum_count = 0 # 合計件数カウンタ
    for cat in unique_categories:
        count = len(df[df['category'] == cat] )
        sum_count += count
        print(f"・{cat} ({count}件)")
    print(f"=== 分類区分合計: {len(unique_categories)}, 合計件数: {sum_count}件 ===")
    
    with open('category_list.txt', 'w', encoding='utf-8') as f:
        for cat in unique_categories:
            f.write(f"{cat}\n")

    print(f"\ncategory_list.txt にカテゴリ一覧を保存しました。")

if __name__ == "__main__":
    main()
