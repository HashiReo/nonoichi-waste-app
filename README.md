# nonoichi-waste-app

構成
- スマホアプリ（Frontend）: Fluttter
  - iphoneとandroidを同時に作る。カメラの機能も実装しやすく、動作が高速。
- APIサーバー(Backend): Python(FastAPI)
  - アプリから送られてきた写真を受け取り、AIで判定し、結果を返す。
- データベース: SQLite or JSONファイル
  - 野々市市の分別データを格納する。

開発ロードマップ
- Phase1: データ収集とデータベース構築
  - 作業場所: Python DeV Container
  - to do
    1. requestsとBeautifulSoupライブラリを使用し、分別時点サイトから「品目名」と「分別区分（燃やすごみ、プラ等）」のペアを全件取得（スクレイピング）する。
    2. 取得したデータをCSVまたはデータベース（SQLite）に保存する。
    3. PDFの情報を元に、「分別区分」ごとの「捨て方・曜日」のテキストデータを作成する。
  - 成果物: 「品目名を入力すると、捨て方が帰ってくる」プログラム

- Phase2: 自作AIモデルの構築   
    「画像」から「品目（または分別区分）」を判別するAIを作成。
  - 作業場所: Python Dev Container
  - to do:
    1. **画像収集**: ネット上の画像検索や、自分でごみの写真を撮って集める。（例: ペットボトル、空き缶、食品トレイなど、野々市市の分別カテゴリごとにフォルダ分けする）
    2. **学習**: TensorFlow または PyTorchを使い、画像分類モデルを作成。
        - ゼロから作ると大変なので「転移学習」を使用。
    3. **評価**: 未知の画像を見せて、正しく分類できるかテストします。
  - 成果物: 「ごみの写真データを入れると、カテゴリIDを返す」AIモデルfile（.h5や.pth）

- Phase3: APIサーバー構築
    Phase1, Phase2のAIを合体させ、外部から使えるようにする。
    - 作業場所、現在のPython Dev Container
    - to do:
        1. FastAPI フレームワークを使ってWebサーバーを作成。
        2. スマホから画像を受け取る POST /predict という窓口（エンドポイント）を作成。
        3. 画像を受け取る → AIで解析 → データベースで詳細を検索 → 「燃やすごみです（火曜・金曜）」というJSONを返す処理を書く。
    - 成果物: Web上で動くAI判定サーバー 

- Phase4: スマホアプリ開発(Flutter)
    最後にユーザーが触る画面を作成する。
    - 作業場所: PC本体（または別のDev Container）できれば Dev Containerで開発したい。
    - to do:
        1. Flutter環境を構築
        2. カメラを起動して写真を撮る画面を作る。
        3. 撮った写真をPhase3のサーバーに送信し、結果を表示させる画面を作る。
    - 成果物: iPhone/Androidアプリ

## ディレクトリ構成

```
nonoichi-waste-app/
├── .devcontainer/
│   └── devcontainer.json   # Python用の環境設定
├── backend/
│   ├── requirements.txt
│   ├── collector/          # データ収集（Phase 1）
│   │   └── fetch_test.py
│   ├── ml/                 # AI学習（Phase 2）
│   ├── app/                # APIサーバー （Phase 3）
│   └── data/               # 収集データ
│
├── mobile_app/             # Dlutter環境
│   ├── android/            # Android用設定
│   ├── ios/                # iOS用設定
│   ├── lib/                # アプリ画面のプログラム
│   │   ├── main.dart
│   │   └── screens/
│   └── pubspec.yml         # Flutterのライブラリ設定
│
└── README.md               # プロジェクト全体の説明書
```