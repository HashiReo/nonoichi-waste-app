# /backend/collector/fetch_test.py
# Webページ取得テストスクリプト

import requests  #「Web通信ライブラリ」

# 1. アクセスしたい場所（コピーしたURLをここに貼る）
# 例: url = "https://gb.hn-kouiki.jp/nonoichi/50on.php?gyo=あ"
url = "https://gb.hn-kouiki.jp/nonoichi"

print(f"アクセス中: {url}")

try:
    # 2. requests.get() でサーバーに「ページを見せて」とお願いします
    # timeout=10 は「10秒待っても返事がなかったら諦める」という設定です
    response = requests.get(url, timeout=10)

    # 3. 結果の診断（ステータスコード）
    # 200番台なら成功、400/500番台ならエラー
    print(f"ステータスコード: {response.status_code}")

    if response.status_code == 200:
        print("成功！ページデータを取得できました。")
        # 取得したHTMLの中身を少しだけ（最初の500文字）表示してみます
        print("\n--- HTMLデータの一部 ---")
        print(response.text[:500]) 
        print("------------------------")
    else:
        print("失敗... ページが見つからないか、アクセスが拒否されました。")

except Exception as e:
    # URLが間違っている時や、ネットが繋がっていない時のエラーを表示
    print(f"エラーが発生しました: {e}")