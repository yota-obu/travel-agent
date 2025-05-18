# 旅行プランナー

MBTIと年齢に基づいて最適な旅行プランを提案するWebアプリケーション

## 機能

- メンバーの情報入力（年齢、性別、MBTI）
- 出発地、旅行月、宿泊数、予算の設定
- 最適な目的地の提案
- 交通手段ごとの費用計算
- 宿泊費の提案
- 詳細な旅行プランの生成

## 技術スタック

### バックエンド
- Python 3.8+
- FastAPI
- Pydantic
- scikit-learn

### フロントエンド
- React
- Material-UI
- Axios

## セットアップ手順

### バックエンド

1. Pythonの仮想環境を作成し、有効化します：
```bash
python -m venv venv
source venv/bin/activate  # Unix/macOS
# または
.\venv\Scripts\activate  # Windows
```

2. 依存関係をインストールします：
```bash
pip install -r requirements.txt
```

3. サーバーを起動します：
```bash
cd backend
uvicorn main:app --reload
```

### フロントエンド

1. 依存関係をインストールします：
```bash
cd frontend
npm install
```

2. 開発サーバーを起動します：
```bash
npm start
```

## 使用方法

1. ブラウザで http://localhost:3000 にアクセス
2. メンバー情報を入力
3. 旅行の基本情報（出発地、月、宿泊数、予算）を入力
4. 「プランを生成」ボタンをクリック
5. 生成された旅行プランを確認 