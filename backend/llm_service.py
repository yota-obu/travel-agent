import os
from typing import List, Dict, Tuple, Optional
import google.generativeai as genai
from dotenv import load_dotenv
import logging
import json
import time
import random
from tenacity import retry, stop_after_attempt, wait_exponential
import requests
from datetime import datetime, timedelta
import googlemaps
from googlemaps import places
from string import Template
import math
from pathlib import Path
from maps_service import get_hotel_details

# ロギングの設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# カスタムエラークラスの定義
class TravelPlanError(Exception):
    """旅行プラン生成に関するカスタムエラー"""
    def __init__(self, message: str, error_code: str = None, details: dict = None):
        super().__init__(message)
        self.message = message
        self.error_code = error_code or 'TRAVEL_PLAN_ERROR'
        self.details = details or {}

class ValidationError(TravelPlanError):
    """バリデーションエラー"""
    def __init__(self, message: str, error_code: str = 'VALIDATION_ERROR', details: dict = None):
        super().__init__(
            message=message,
            error_code=error_code,
            details=details or {}
        )

class APIError(TravelPlanError):
    """外部APIエラー"""
    def __init__(self, message: str, api_name: str = 'Gemini'):
        super().__init__(
            message=message,
            error_code='API_ERROR',
            details={'api_name': api_name}
        )

class BudgetError(TravelPlanError):
    """予算関連のエラー"""
    def __init__(self, message: str, budget_info: dict = None):
        super().__init__(
            message=message,
            error_code='BUDGET_ERROR',
            details={'budget_info': budget_info} if budget_info else {}
        )

# 環境変数の読み込み
env_path = Path(__file__).parent / '.env'
load_dotenv(dotenv_path=env_path)

# 環境変数の検証
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
GOOGLE_MAPS_API_KEY = os.getenv('GOOGLE_MAPS_API_KEY')

if not GOOGLE_API_KEY:
    logger.error("GOOGLE_API_KEYが設定されていません")
    raise APIError("Google API Keyが設定されていません", "Gemini")

if not GOOGLE_MAPS_API_KEY:
    logger.error("GOOGLE_MAPS_API_KEYが設定されていません")
    raise APIError("Google Maps API Keyが設定されていません", "Google Maps")

# Gemini APIの設定
try:
    genai.configure(api_key=GOOGLE_API_KEY)
    model = genai.GenerativeModel('gemini-2.0-flash')
    logger.info("Gemini APIの設定が完了しました")
except Exception as e:
    logger.error(f"Gemini APIの設定に失敗しました: {str(e)}")
    raise APIError(f"Gemini APIの設定に失敗しました: {str(e)}", "Gemini")

# Google Maps APIの設定
try:
    gmaps = googlemaps.Client(key=GOOGLE_MAPS_API_KEY)
    logger.info("Google Maps APIの設定が完了しました")
except Exception as e:
    logger.error(f"Google Maps APIの設定に失敗しました: {str(e)}")
    raise APIError(f"Google Maps APIの設定に失敗しました: {str(e)}", "Google Maps")

# 旅行プランのテンプレート
TRAVEL_PLAN_TEMPLATE = """# 旅行プラン

## 目的地情報
**目的地**: ${destination}  
**特徴**: ${destination_features}

## 季節の見どころ
**${month}月の気候と見どころ**  
${seasonal_highlights}

## グループ特性
**MBTIタイプに合わせたポイント**  
${mbti_points}

## 交通手段
### おすすめの交通手段
${recommended_transport}

### 交通手段の詳細比較
#### 新幹線・電車での移動
- **所要時間**: ${train_duration}
- **メリット**: ${train_pros}
- **デメリット**: ${train_cons}

#### 飛行機での移動
- **所要時間**: ${plane_duration}
- **メリット**: ${plane_pros}
- **デメリット**: ${plane_cons}

#### レンタカーでの移動
- **所要時間**: ${car_duration}
- **メリット**: ${car_pros}
- **デメリット**: ${car_cons}

## 宿泊グレード
**選択されたグレード**: ${accommodation_grade}
**グレード詳細**: ${grade_description}

## 宿泊施設
${hotel_details}

## 観光プラン
### 1日目
#### 午前（${day1_morning_time}）
${day1_morning_desc}

**見どころ**: ${day1_morning_highlights}  
**所要時間**: ${day1_morning_duration}

#### 午後（${day1_afternoon_time}）
${day1_afternoon_desc}

**見どころ**: ${day1_afternoon_highlights}  
**所要時間**: ${day1_afternoon_duration}

#### 夜（${day1_evening_time}）
${day1_evening_desc}

**見どころ**: ${day1_evening_highlights}  
**所要時間**: ${day1_evening_duration}

### 2日目
#### 午前（${day2_morning_time}）
${day2_morning_desc}

**見どころ**: ${day2_morning_highlights}  
**所要時間**: ${day2_morning_duration}

#### 午後（${day2_afternoon_time}）
${day2_afternoon_desc}

**見どころ**: ${day2_afternoon_highlights}  
**所要時間**: ${day2_afternoon_duration}

#### 夜（${day2_evening_time}）
${day2_evening_desc}

**見どころ**: ${day2_evening_highlights}  
**所要時間**: ${day2_evening_duration}"""

# 出発地（都道府県）の選択肢を定義
DEPARTURE_PREFECTURES = [
    {
        "id": "hokkaido",
        "name": "北海道",
        "region": "北海道"
    },
    {
        "id": "aomori",
        "name": "青森県",
        "region": "東北"
    },
    {
        "id": "iwate",
        "name": "岩手県",
        "region": "東北"
    },
    {
        "id": "miyagi",
        "name": "宮城県",
        "region": "東北"
    },
    {
        "id": "akita",
        "name": "秋田県",
        "region": "東北"
    },
    {
        "id": "yamagata",
        "name": "山形県",
        "region": "東北"
    },
    {
        "id": "fukushima",
        "name": "福島県",
        "region": "東北"
    },
    {
        "id": "ibaraki",
        "name": "茨城県",
        "region": "関東"
    },
    {
        "id": "tochigi",
        "name": "栃木県",
        "region": "関東"
    },
    {
        "id": "gunma",
        "name": "群馬県",
        "region": "関東"
    },
    {
        "id": "saitama",
        "name": "埼玉県",
        "region": "関東"
    },
    {
        "id": "chiba",
        "name": "千葉県",
        "region": "関東"
    },
    {
        "id": "tokyo",
        "name": "東京都",
        "region": "関東"
    },
    {
        "id": "kanagawa",
        "name": "神奈川県",
        "region": "関東"
    },
    {
        "id": "niigata",
        "name": "新潟県",
        "region": "中部"
    },
    {
        "id": "toyama",
        "name": "富山県",
        "region": "中部"
    },
    {
        "id": "ishikawa",
        "name": "石川県",
        "region": "中部"
    },
    {
        "id": "fukui",
        "name": "福井県",
        "region": "中部"
    },
    {
        "id": "yamanashi",
        "name": "山梨県",
        "region": "中部"
    },
    {
        "id": "nagano",
        "name": "長野県",
        "region": "中部"
    },
    {
        "id": "gifu",
        "name": "岐阜県",
        "region": "中部"
    },
    {
        "id": "shizuoka",
        "name": "静岡県",
        "region": "中部"
    },
    {
        "id": "aichi",
        "name": "愛知県",
        "region": "中部"
    },
    {
        "id": "mie",
        "name": "三重県",
        "region": "関西"
    },
    {
        "id": "shiga",
        "name": "滋賀県",
        "region": "関西"
    },
    {
        "id": "kyoto",
        "name": "京都府",
        "region": "関西"
    },
    {
        "id": "osaka",
        "name": "大阪府",
        "region": "関西"
    },
    {
        "id": "hyogo",
        "name": "兵庫県",
        "region": "関西"
    },
    {
        "id": "nara",
        "name": "奈良県",
        "region": "関西"
    },
    {
        "id": "wakayama",
        "name": "和歌山県",
        "region": "関西"
    },
    {
        "id": "tottori",
        "name": "鳥取県",
        "region": "中国"
    },
    {
        "id": "shimane",
        "name": "島根県",
        "region": "中国"
    },
    {
        "id": "okayama",
        "name": "岡山県",
        "region": "中国"
    },
    {
        "id": "hiroshima",
        "name": "広島県",
        "region": "中国"
    },
    {
        "id": "yamaguchi",
        "name": "山口県",
        "region": "中国"
    },
    {
        "id": "tokushima",
        "name": "徳島県",
        "region": "四国"
    },
    {
        "id": "kagawa",
        "name": "香川県",
        "region": "四国"
    },
    {
        "id": "ehime",
        "name": "愛媛県",
        "region": "四国"
    },
    {
        "id": "kochi",
        "name": "高知県",
        "region": "四国"
    },
    {
        "id": "fukuoka",
        "name": "福岡県",
        "region": "九州"
    },
    {
        "id": "saga",
        "name": "佐賀県",
        "region": "九州"
    },
    {
        "id": "nagasaki",
        "name": "長崎県",
        "region": "九州"
    },
    {
        "id": "kumamoto",
        "name": "熊本県",
        "region": "九州"
    },
    {
        "id": "oita",
        "name": "大分県",
        "region": "九州"
    },
    {
        "id": "miyazaki",
        "name": "宮崎県",
        "region": "九州"
    },
    {
        "id": "kagoshima",
        "name": "鹿児島県",
        "region": "九州"
    },
    {
        "id": "okinawa",
        "name": "沖縄県",
        "region": "沖縄"
    }
]

def get_departure_prefectures() -> List[Dict]:
    """出発地（都道府県）の選択肢を取得する"""
    return DEPARTURE_PREFECTURES

def clean_response_text(text: str) -> str:
    """Gemini APIのレスポンステキストをクリーンアップする"""
    try:
        # テキストの前処理
        text = text.strip()
        
        # JSONブロックの抽出
        if "```json" in text:
            # JSONブロックの開始と終了を見つける
            start = text.find("```json") + 7
            end = text.find("```", start)
            if end != -1:
                text = text[start:end]
        elif "```" in text:
            # 一般的なコードブロックの処理
            start = text.find("```") + 3
            end = text.find("```", start)
            if end != -1:
                text = text[start:end]
        
        # 余分な空白と改行の削除
        text = text.strip()
        
        # JSONとして解析
        try:
            # 最初にJSONとして解析を試みる
            return json.dumps(json.loads(text), ensure_ascii=False)
        except json.JSONDecodeError:
            # 文字列内のエスケープ処理
            text = text.replace('\n', '\\n').replace('\r', '\\r')
            # 再度JSONとして解析
            return json.dumps(json.loads(text), ensure_ascii=False)
            
    except json.JSONDecodeError as e:
        logger.error(f"JSONパースエラー: {str(e)}")
        logger.error(f"パース対象のテキスト: {text}")
        raise ValidationError("レスポンスのJSON形式が不正です", details={'error': str(e), 'text': text})
    except Exception as e:
        logger.error(f"予期せぬエラー: {str(e)}")
        raise ValidationError("レスポンスの処理中にエラーが発生しました", details={'error': str(e), 'text': text})

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    retry_error_callback=lambda _: {"error": "旅行プランの生成に失敗しました。"}
)
def generate_content_with_retry(prompt: str, max_tokens: int = 2048) -> str:
    """リトライ機能付きでGemini APIを呼び出す"""
    try:
        logger.info("Gemini APIを呼び出します")
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.2,
                max_output_tokens=max_tokens,
                #top_p=0.8,
                #top_k=40
            )
        )
        logger.info(f"APIレスポンス: {response.text}")
        cleaned_text = clean_response_text(response.text)
        logger.info(f"クリーニング後のテキスト: {cleaned_text}")
        return cleaned_text
    except Exception as e:
        logger.error(f"Gemini API呼び出しエラー: {str(e)}")
        raise APIError(f"Gemini APIエラー: {str(e)}")

def validate_time_format(time_str: str) -> Tuple[bool, Optional[str]]:
    """時間形式が正しいかチェックする"""
    if not time_str:
        return False, "時間が指定されていません"
    
    if time_str == "利用不可":
        return True, None
    
    if "時間" in time_str:
        parts = time_str.split("時間")
        if len(parts) != 2:
            return False, "時間形式が不正です（例: 2時間30分）"
        try:
            hours = int(parts[0])
            if parts[1]:
                minutes = int(parts[1].replace("分", ""))
                if not (0 <= minutes < 60):
                    return False, "分は0-59の範囲で指定してください"
            return True, None
        except ValueError:
            return False, "時間と分は数値で指定してください"
    
    return False, "時間形式が不正です（例: 2時間30分）"

def validate_travel_plan(plan_data: Dict) -> Tuple[bool, Optional[Dict]]:
    """生成された旅行プランのバリデーション"""
    errors = {}
    
    try:
        logger.info(f"プランのバリデーションを開始: {json.dumps(plan_data, ensure_ascii=False)}")
        
        # 必須フィールドのチェック
        required_fields = [
            "destination",
            "destination_features",
            "seasonal_highlights",
            "recommended_transport"
        ]
        
        missing_fields = [field for field in required_fields if not plan_data.get(field)]
        if missing_fields:
            logger.error(f"必須フィールドが不足: {missing_fields}")
            errors['missing_fields'] = missing_fields
        
        # 時間形式のバリデーション
        time_fields = [
            "day1_morning_time",
            "day1_afternoon_time",
            "day1_evening_time"
        ]
        
        time_errors = {}
        for field in time_fields:
            if field in plan_data and plan_data[field]:
                time_str = plan_data[field]
                if not isinstance(time_str, str) or ":" not in time_str:
                    logger.error(f"時間形式エラー - {field}: {time_str}")
                    time_errors[field] = "時間は「HH:MM」形式で指定してください"
        
        if time_errors:
            errors['time_format'] = time_errors
        
        is_valid = len(errors) == 0
        logger.info(f"バリデーション結果: valid={is_valid}, errors={json.dumps(errors, ensure_ascii=False)}")
        return is_valid, errors
    
    except Exception as e:
        logger.error(f"バリデーション中の予期せぬエラー: {str(e)}")
        return False, {'unexpected_error': str(e)}

def analyze_group_preferences(members: List[Dict]) -> Dict[str, float]:
    """グループの特性を分析し、旅行の傾向スコアを計算する"""
    scores = {
        'activity': 0.0,  # アクティブな活動への興味
        'culture': 0.0,   # 文化的な活動への興味
        'nature': 0.0,    # 自然への興味
        'urban': 0.0,     # 都市的な活動への興味
        'relaxation': 0.0 # リラックス志向
    }
    
    # MBTIタイプに基づくスコアリング
    mbti_preferences = {
        'E': {'activity': 0.3, 'urban': 0.2},
        'I': {'culture': 0.2, 'nature': 0.2, 'relaxation': 0.1},
        'S': {'urban': 0.2, 'culture': 0.1},
        'N': {'nature': 0.2, 'activity': 0.1},
        'T': {'culture': 0.2, 'urban': 0.1},
        'F': {'nature': 0.2, 'relaxation': 0.2},
        'J': {'culture': 0.2, 'urban': 0.1},
        'P': {'activity': 0.2, 'nature': 0.1}
    }
    
    for member in members:
        mbti = member['mbti']
        for letter in mbti:
            if letter in mbti_preferences:
                for category, score in mbti_preferences[letter].items():
                    scores[category] += score / len(members)
    
    # 年齢による調整
    for member in members:
        age = int(member['age'])
        if age < 30:
            scores['activity'] += 0.1 / len(members)
            scores['urban'] += 0.1 / len(members)
        elif age > 50:
            scores['relaxation'] += 0.1 / len(members)
            scores['culture'] += 0.1 / len(members)
    
    return scores

def suggest_destinations(departure: str, departure_region: str, preferences: Dict[str, float]) -> Dict[str, str]:
    """目的地を提案する"""
    try:
        logger.info(f"目的地提案を開始 - 出発地: {departure}, 地方: {departure_region}")
        logger.info(f"選好度: {json.dumps(preferences, ensure_ascii=False)}")

        # 選好度に基づいて目的地タイプを決定
        destination_types = []
        if preferences['nature'] > 0.4:
            destination_types.extend([
                "自然豊かな観光地",
                "国立公園や自然公園がある地域",
                "山や海に囲まれた観光地"
            ])
        if preferences['culture'] > 0.4:
            destination_types.extend([
                "歴史的・文化的な観光地",
                "伝統工芸や伝統芸能が盛んな地域",
                "歴史的建造物が多い地域"
            ])
        if preferences['urban'] > 0.4:
            destination_types.extend([
                "都市型観光地",
                "近代的な施設が充実した地域",
                "ショッピングや娯楽施設が豊富な地域"
            ])
        if preferences['relaxation'] > 0.4:
            destination_types.extend([
                "リラックスできる観光地",
                "温泉地や保養地",
                "のんびりと過ごせる地域"
            ])
        if not destination_types:
            destination_types = [
                "バランスの取れた観光地",
                "多様な魅力がある地域",
                "観光資源が豊富な地域"
            ]

        # ランダムに2つのタイプを選択して組み合わせる
        selected_types = random.sample(destination_types, min(2, len(destination_types)))
        destination_type = " かつ ".join(selected_types)

        # 地方のマッピング
        region_mapping = {
            "北海道": ["北海道"],
            "東北": ["青森県", "岩手県", "宮城県", "秋田県", "山形県", "福島県"],
            "関東": ["茨城県", "栃木県", "群馬県", "埼玉県", "千葉県", "東京都", "神奈川県"],
            "中部": ["新潟県", "富山県", "石川県", "福井県", "山梨県", "長野県", "岐阜県", "静岡県", "愛知県"],
            "関西": ["三重県", "滋賀県", "京都府", "大阪府", "兵庫県", "奈良県", "和歌山県"],
            "中国": ["鳥取県", "島根県", "岡山県", "広島県", "山口県"],
            "四国": ["徳島県", "香川県", "愛媛県", "高知県"],
            "九州": ["福岡県", "佐賀県", "長崎県", "熊本県", "大分県", "宮崎県", "鹿児島県"],
            "沖縄": ["沖縄県"]
        }

        prompt = f"""
以下の条件に基づいて、具体的な観光地を1つ提案してください。
必ずJSON形式で返してください。

条件：
1. 以下の地域は除外してください：
   - {departure}がある都道府県
   - {departure_region}地方の全ての都道府県（{', '.join(region_mapping.get(departure_region, []))}）
2. {destination_type}を優先的に提案
3. 具体的な市区町村名を提案（例：「金沢市」「函館市」「松江市」「高山市」「別府市」など）
4. 観光地としての知名度が高く、アクセスが比較的容易な場所を選ぶ
5. 以下のような場所を含めることができます：
   - 世界遺産や国宝がある都市
   - 伝統的な祭りや行事で有名な都市
   - 特徴的な食文化がある都市
   - 独自の文化や芸術が息づく都市
   - 美しい自然景観で知られる都市

以下の形式で返してください：
{{
    "destination": "具体的な市区町村名",
    "prefecture": "都道府県名"
}}
"""

        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.7,  # より多様な提案を得るために温度を上げる
                max_output_tokens=150,
                top_p=0.8,
                top_k=40
            )
        )

        response_text = clean_response_text(response.text)
        destination_data = json.loads(response_text)
        
        destination = destination_data["destination"]
        suggested_prefecture = destination_data.get("prefecture", "")

        # 出発地と同じ地方の目的地をチェック
        departure_region_prefectures = region_mapping.get(departure_region, [])
        if (
            departure.lower() in destination.lower() or
            departure.lower() in suggested_prefecture.lower() or
            any(pref.lower() in destination.lower() for pref in departure_region_prefectures) or
            any(pref.lower() in suggested_prefecture.lower() for pref in departure_region_prefectures)
        ):
            logger.warning(f"提案された目的地（{destination}）が出発地と同じ地方です。再試行します。")
            return suggest_destinations(departure, departure_region, preferences)

        logger.info(f"提案された目的地: {destination} ({suggested_prefecture})")
        return {
            "destination": destination,
            "prefecture": suggested_prefecture
        }

    except Exception as e:
        logger.error(f"目的地提案でエラー: {str(e)}")
        raise ValidationError("目的地の提案に失敗しました", details={'error': str(e)})

def get_location_details(destination: str) -> Dict:
    """目的地の詳細な位置情報を取得する"""
    try:
        # 目的地の詳細情報を取得するためのプロンプト
        prompt = f"""
以下の観光地について、都道府県名を返してください：

観光地: {destination}

以下の形式で返してください：
{{
    "prefecture": "都道府県名（例：「東京都」「京都府」など）"
}}
"""
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.2,
                max_output_tokens=150
            )
        )
        
        location_data = json.loads(clean_response_text(response.text))
        logger.info(f"取得した位置情報: {json.dumps(location_data, ensure_ascii=False)}")
        
        return {
            "prefecture": location_data.get("prefecture", "")
        }
    except Exception as e:
        logger.error(f"位置情報の取得でエラー: {str(e)}")
        return {
            "prefecture": ""
        }

def get_hotel_recommendations(location: str, max_price_level: int) -> List[Dict]:
    """
    指定された場所と宿泊グレードに基づいてホテルを検索する
    
    Args:
        location (str): 検索場所
        max_price_level (int): 最大価格レベル
    
    Returns:
        List[Dict]: ホテル情報のリスト
    
    Raises:
        ValidationError: 無効な宿泊グレードが指定された場合
    """
    if not location:
        raise ValidationError("検索場所を指定してください")
        
    try:
        # Google Places APIを使用してホテルを検索
        places_result = gmaps.places(
            query=f"ホテル {location}",
            type="lodging",
            language="ja"
        )
        
        hotels = []
        for place in places_result.get("results", []):
            # 詳細情報を取得
            hotel_details = get_hotel_details(place["place_id"])
            if hotel_details:
                # price_levelが指定されていない場合は含める
                if "price_level" not in hotel_details or hotel_details["price_level"] <= max_price_level:
                    hotels.append(hotel_details)
        
        # 評価の高い順にソート
        hotels.sort(key=lambda x: (x.get("rating", 0), x.get("total_ratings", 0)), reverse=True)
        return hotels[:5]  # 上位5件を返す
        
    except Exception as e:
        logger.error(f"ホテル検索でエラー: {str(e)}", exc_info=True)
        return []

def format_hotel_info(hotels: List[Dict]) -> str:
    """ホテル情報を文字列にフォーマット"""
    if not hotels:
        return "申し訳ありません。条件に合う宿泊施設が見つかりませんでした。"

    info = "\n\n## おすすめの宿泊施設\n"
    price_level_map = {
        0: "予算情報なし",
        1: "お手頃価格（〜15,000円）",
        2: "中価格帯（15,000円〜30,000円）",
        3: "高価格帯（30,000円〜50,000円）",
        4: "超高級（50,000円〜）"
    }

    # カテゴリーごとにホテルをグループ化
    categorized_hotels = {}
    for hotel in hotels:
        category = hotel.get('category', 'その他')
        if category not in categorized_hotels:
            categorized_hotels[category] = []
        categorized_hotels[category].append(hotel)

    # カテゴリーごとに表示
    for category, hotels_in_category in categorized_hotels.items():
        info += f"\n### ■ {category}タイプ\n"
        
        # 各カテゴリーで最大2件表示
        for i, hotel in enumerate(hotels_in_category[:2], 1):
            info += f"\n#### {i}. {hotel['name']}\n"
            info += f"**評価**: ★{hotel['rating']:.1f} ({hotel['total_ratings']}件のレビュー)\n"
            
            # 価格情報の表示
            price_level = hotel.get('price_level')
            price_info = price_level_map.get(price_level, "予算情報なし")
            info += f"**価格帯**: {price_info}\n"
            
            info += f"**住所**: {hotel['formatted_address']}\n"
            
            if hotel['phone']:
                info += f"**電話**: {hotel['phone']}\n"
            
            if hotel['website']:
                info += f"**詳細**: [施設の公式サイトを見る]({hotel['website']})\n"
            
            # 特徴や設備情報の表示（もしあれば）
            if hotel.get('photos'):
                info += "\n**施設写真**:\n\n"
                for photo_url in hotel['photos'][:3]:  # 最大3枚まで
                    info += f"![{hotel['name']}の写真]({photo_url}) "
                info += "\n\n"
            
            info += "---\n"

    return info

def add_randomness_to_prompt(prompt: str) -> str:
    """プロンプトにランダム性を追加する"""
    variations = [
        "できるだけユニークで面白い提案を含めてください。",
        "定番の観光スポットだけでなく、穴場スポットも提案してください。",
        "季節ならではの特別な体験を重視してください。",
        "地元の人しか知らないような魅力的なスポットを含めてください。",
        "アクティブな活動と静かな観光のバランスを考慮してください。"
    ]
    
    time_variations = [
        "朝早めのスタートで効率的に回る行程",
        "ゆっくり目の出発でリラックスした行程",
        "夜遅くまで楽しめる行程",
        "食事時間をメインに考えた行程",
        "天候に左右されにくい行程"
    ]
    
    selected_variation = random.choice(variations)
    selected_time_variation = random.choice(time_variations)
    
    return f"{prompt}\n\n追加の要望：\n1. {selected_variation}\n2. {selected_time_variation}"

# 宿泊グレードの定義
ACCOMMODATION_GRADES = {
    "エコノミー": {
        "description": "リーズナブルな価格で快適な滞在",
        "price_level": 1
    },
    "スタンダード": {
        "description": "快適さと利便性のバランス",
        "price_level": 2
    },
    "ラグジュアリー": {
        "description": "高級な設備とサービス",
        "price_level": 3
    },
    "ウルトララグジュアリー": {
        "description": "最高級の設備とサービス",
        "price_level": 4
    }
}

def generate_travel_plan(members: List[Dict], departure: str, departure_region: str, month: int, nights: int, accommodation_grade: str) -> str:
    try:
        logger.info("旅行プラン生成を開始します")
        logger.info(f"入力パラメータ: 出発地={departure}, 地方={departure_region}, 月={month}, 宿泊数={nights}, 宿泊グレード={accommodation_grade}")
        logger.info(f"メンバー情報: {json.dumps(members, ensure_ascii=False)}")

        # 入力値の検証
        if not members:
            raise ValidationError("メンバー情報が必要です")
        if not departure:
            raise ValidationError("出発地が必要です")
        if not departure_region:
            raise ValidationError("出発地の地方情報が必要です")
        if not (1 <= month <= 12):
            raise ValidationError("月は1から12の間で指定してください")
        if nights < 1:
            raise ValidationError("宿泊数は1泊以上で指定してください")
        if accommodation_grade not in ACCOMMODATION_GRADES:
            valid_grades = "、".join(ACCOMMODATION_GRADES.keys())
            raise ValidationError(
                f"有効な宿泊グレードを指定してください。選択可能なグレード：{valid_grades}",
                details={
                    "valid_grades": list(ACCOMMODATION_GRADES.keys()),
                    "provided_grade": accommodation_grade
                }
            )

        # グループの特性を分析
        try:
            preference_scores = analyze_group_preferences(members)
            logger.info(f"グループ特性スコア: {preference_scores}")
            
            # MBTIに基づく特徴を生成
            mbti_points = generate_mbti_characteristics(members)
            logger.info(f"MBTI特性: {mbti_points}")
        except Exception as e:
            logger.error(f"グループ特性分析でエラー: {str(e)}", exc_info=True)
            preference_scores = {
                'activity': 0.5, 
                'culture': 0.5, 
                'nature': 0.5, 
                'urban': 0.5, 
                'relaxation': 0.5
            }
            mbti_points = "グループの多様な性格タイプを考慮した、バランスの取れた旅行プランをご提案します。"

        # 目的地を提案
        try:
            destination_data = suggest_destinations(departure, departure_region, preference_scores)
            logger.info(f"提案された目的地: {destination_data['destination']} ({destination_data['prefecture']})")
            
            # 目的地が長すぎる場合は短くする
            if len(destination_data['destination']) > 20:
                destination_data['destination'] = destination_data['destination'][:20]
                logger.warning(f"目的地名が長すぎるため切り詰め: {destination_data['destination']}")
                
        except Exception as e:
            logger.error(f"目的地の提案でエラー: {str(e)}", exc_info=True)
            destination_data = {
                "destination": "東京",
                "prefecture": "東京都"
            }

        # 目的地の特徴と季節情報を生成
        try:
            destination_prompt = f"""
以下の条件に基づいて、観光地の特徴と季節の見どころを具体的に説明してください：

観光地: {destination_data['destination']}
訪問月: {month}月
グループ特性:
- アクティビティ志向: {preference_scores['activity']:.2f}
- 文化的活動志向: {preference_scores['culture']:.2f}
- 自然志向: {preference_scores['nature']:.2f}
- 都市的活動志向: {preference_scores['urban']:.2f}
- リラックス志向: {preference_scores['relaxation']:.2f}

以下の形式でJSON形式で返してください：
{{
    "destination_features": "この地域の特徴を3-4行で説明（観光スポット、アクセス、雰囲気など）",
    "seasonal_highlights": "この月ならではの見どころ、イベント、気候、おすすめの過ごし方を具体的に説明"
}}

注意点：
1. 地域の特徴は具体的な観光スポットや体験を含めて説明してください
2. 季節の見どころは、その月ならではの体験や注意点を詳しく説明してください
3. グループの特性に合わせた提案を含めてください
"""
            logger.info("目的地情報の生成を開始")
            destination_info = json.loads(generate_content_with_retry(destination_prompt))
            logger.info(f"生成された目的地情報: {json.dumps(destination_info, ensure_ascii=False, indent=2)}")
        except Exception as e:
            logger.error(f"目的地情報の生成に失敗: {str(e)}", exc_info=True)
            destination_info = {
                "destination_features": f"{destination_data['destination']}の観光情報を取得できませんでした。",
                "seasonal_highlights": f"{month}月の季節情報を取得できませんでした。"
            }

        # 交通手段の詳細を生成
        try:
            transport_prompt = f"""
以下の条件に基づいて、交通手段の詳細情報を生成してください：

出発地: {departure}
目的地: {destination_data['destination']}
月: {month}月
グループ人数: {len(members)}人

以下の形式でJSON形式で返してください：
{{
    "recommended_transport": "最適な交通手段の提案と理由",
    "train_duration": "所要時間（〇時間〇分）",
    "train_cost": "費用（数字のみ）",
    "train_cost_per": "人",
    "train_pros": "電車利用のメリット",
    "train_cons": "電車利用のデメリット",
    "plane_duration": "所要時間または利用不可",
    "plane_cost": "費用または利用不可",
    "plane_cost_per": "人",
    "plane_pros": "飛行機利用のメリット",
    "plane_cons": "飛行機利用のデメリット",
    "car_duration": "所要時間（〇時間〇分）",
    "car_cost": "費用（数字のみ）",
    "car_cost_per": "台",
    "car_pros": "車利用のメリット",
    "car_cons": "車利用のデメリット"
}}
"""
            logger.info("交通情報の生成を開始")
            transport_info = json.loads(generate_content_with_retry(transport_prompt))
            logger.info(f"生成された交通情報: {json.dumps(transport_info, ensure_ascii=False, indent=2)}")
        except Exception as e:
            logger.error(f"交通情報の生成に失敗: {str(e)}", exc_info=True)
            transport_info = {
                "recommended_transport": "交通手段の情報を取得できませんでした。",
                "train_duration": "情報なし",
                "train_cost": "0",
                "train_cost_per": "人",
                "train_pros": "情報なし",
                "train_cons": "情報なし",
                "plane_duration": "利用不可",
                "plane_cost": "利用不可",
                "plane_cost_per": "人",
                "plane_pros": "情報なし",
                "plane_cons": "情報なし",
                "car_duration": "情報なし",
                "car_cost": "0",
                "car_cost_per": "台",
                "car_pros": "情報なし",
                "car_cons": "情報なし"
            }

        # 宿泊施設の検索
        try:
            # 宿泊グレードの情報を取得
            grade_info = ACCOMMODATION_GRADES[accommodation_grade]
            grade_description = grade_info["description"]

            hotels = get_hotel_recommendations(
                location=destination_data['destination'],
                max_price_level=grade_info["price_level"]
            )
            
            if hotels:
                hotel = hotels[0]  # 最も評価の高いホテルを選択
                hotel_info = {
                    "hotel_name": hotel['name'],
                    "hotel_type": hotel['category'],
                    "hotel_features": f"評価: ★{hotel['rating']} ({hotel['total_ratings']}件のレビュー)",
                    "hotel_details": format_hotel_info(hotels),
                    "accommodation_grade": accommodation_grade,
                    "grade_description": grade_description
                }
            else:
                hotel_info = {
                    "hotel_name": "条件に合う宿泊施設が見つかりませんでした",
                    "hotel_type": "情報なし",
                    "hotel_features": "情報なし",
                    "hotel_details": "宿泊施設の詳細情報は現在利用できません",
                    "accommodation_grade": accommodation_grade,
                    "grade_description": grade_description
                }
        except Exception as e:
            logger.error(f"宿泊施設の検索でエラー: {str(e)}", exc_info=True)
            hotel_info = {
                "hotel_name": "宿泊施設の検索中にエラーが発生しました",
                "hotel_type": "情報なし",
                "hotel_features": "情報なし",
                "hotel_details": "宿泊施設の詳細情報は現在利用できません",
                "accommodation_grade": accommodation_grade,
                "grade_description": ACCOMMODATION_GRADES[accommodation_grade]["description"]
            }

        # 観光プランの生成
        try:
            # 1日目のプラン生成
            itinerary_prompt_day1 = f"""
以下の条件に基づいて、1日目の観光プランを生成してください：

目的地: {destination_data['destination']}
月: {month}月
グループ特性:
- アクティビティ志向: {preference_scores['activity']:.2f}
- 文化的活動志向: {preference_scores['culture']:.2f}
- 自然志向: {preference_scores['nature']:.2f}
- 都市的活動志向: {preference_scores['urban']:.2f}
- リラックス志向: {preference_scores['relaxation']:.2f}

以下の形式でJSON形式で返してください：
{{
    "morning": {{
        "time": "9:00",
        "description": "午前の活動の詳細な説明（1日目）",
        "highlights": "主な見どころ",
        "duration": "2時間30分"
    }},
    "afternoon": {{
        "time": "13:00",
        "description": "午後の活動の詳細な説明（1日目）",
        "highlights": "主な見どころ",
        "duration": "3時間"
    }},
    "evening": {{
        "time": "18:00",
        "description": "夜の活動の詳細な説明（1日目）",
        "highlights": "主な見どころ",
        "duration": "2時間"
    }}
}}

注意点：
- 1日目は主要な観光スポットや人気の場所を中心に提案してください
- 時間帯に合わせた適切なアクティビティを提案してください
- 移動時間も考慮してください
"""
            itinerary_day1 = json.loads(generate_content_with_retry(itinerary_prompt_day1))
            
            # 2日目のプラン生成（1日目とは異なるプラン）
            itinerary_prompt_day2 = f"""
以下の条件に基づいて、2日目の観光プランを生成してください：

目的地: {destination_data['destination']}
月: {month}月
1日目の訪問場所：
- 午前：{itinerary_day1["morning"]["description"]}
- 午後：{itinerary_day1["afternoon"]["description"]}
- 夜：{itinerary_day1["evening"]["description"]}

グループ特性:
- アクティビティ志向: {preference_scores['activity']:.2f}
- 文化的活動志向: {preference_scores['culture']:.2f}
- 自然志向: {preference_scores['nature']:.2f}
- 都市的活動志向: {preference_scores['urban']:.2f}
- リラックス志向: {preference_scores['relaxation']:.2f}

以下の形式でJSON形式で返してください：
{{
    "morning": {{
        "time": "9:00",
        "description": "午前の活動の詳細な説明（2日目・1日目とは異なる場所）",
        "highlights": "主な見どころ",
        "duration": "2時間30分"
    }},
    "afternoon": {{
        "time": "13:00",
        "description": "午後の活動の詳細な説明（2日目・1日目とは異なる場所）",
        "highlights": "主な見どころ",
        "duration": "3時間"
    }},
    "evening": {{
        "time": "18:00",
        "description": "夜の活動の詳細な説明（2日目・1日目とは異なる場所）",
        "highlights": "主な見どころ",
        "duration": "2時間"
    }}
}}

注意点：
- 1日目とは異なる観光スポットや体験を提案してください
- 穴場スポットや地元ならではの体験を中心に提案してください
- 時間帯に合わせた適切なアクティビティを提案してください
- 移動時間も考慮してください
"""
            itinerary_day2 = json.loads(generate_content_with_retry(itinerary_prompt_day2))
            
            # 1日目の予定を設定
            day1_schedule = {
                "day1_morning_time": itinerary_day1["morning"]["time"],
                "day1_morning_desc": itinerary_day1["morning"]["description"],
                "day1_morning_highlights": itinerary_day1["morning"]["highlights"],
                "day1_morning_duration": itinerary_day1["morning"]["duration"],
                
                "day1_afternoon_time": itinerary_day1["afternoon"]["time"],
                "day1_afternoon_desc": itinerary_day1["afternoon"]["description"],
                "day1_afternoon_highlights": itinerary_day1["afternoon"]["highlights"],
                "day1_afternoon_duration": itinerary_day1["afternoon"]["duration"],
                
                "day1_evening_time": itinerary_day1["evening"]["time"],
                "day1_evening_desc": itinerary_day1["evening"]["description"],
                "day1_evening_highlights": itinerary_day1["evening"]["highlights"],
                "day1_evening_duration": itinerary_day1["evening"]["duration"]
            }
            
            # 2日目の予定を設定（独自のプラン）
            day2_schedule = {
                "day2_morning_time": itinerary_day2["morning"]["time"],
                "day2_morning_desc": itinerary_day2["morning"]["description"],
                "day2_morning_highlights": itinerary_day2["morning"]["highlights"],
                "day2_morning_duration": itinerary_day2["morning"]["duration"],
                
                "day2_afternoon_time": itinerary_day2["afternoon"]["time"],
                "day2_afternoon_desc": itinerary_day2["afternoon"]["description"],
                "day2_afternoon_highlights": itinerary_day2["afternoon"]["highlights"],
                "day2_afternoon_duration": itinerary_day2["afternoon"]["duration"],
                
                "day2_evening_time": itinerary_day2["evening"]["time"],
                "day2_evening_desc": itinerary_day2["evening"]["description"],
                "day2_evening_highlights": itinerary_day2["evening"]["highlights"],
                "day2_evening_duration": itinerary_day2["evening"]["duration"]
            }
            
        except Exception as e:
            logger.error(f"観光プラン生成でエラー: {str(e)}", exc_info=True)
            # デフォルトのスケジュール
            day1_schedule = {
                "day1_morning_time": "9:00",
                "day1_morning_desc": "観光プランの生成中にエラーが発生しました",
                "day1_morning_highlights": "情報なし",
                "day1_morning_duration": "情報なし",
                
                "day1_afternoon_time": "13:00",
                "day1_afternoon_desc": "観光プランの生成中にエラーが発生しました",
                "day1_afternoon_highlights": "情報なし",
                "day1_afternoon_duration": "情報なし",
                
                "day1_evening_time": "18:00",
                "day1_evening_desc": "観光プランの生成中にエラーが発生しました",
                "day1_evening_highlights": "情報なし",
                "day1_evening_duration": "情報なし"
            }
            day2_schedule = {
                "day2_morning_time": "9:00",
                "day2_morning_desc": "観光プランの生成中にエラーが発生しました",
                "day2_morning_highlights": "情報なし",
                "day2_morning_duration": "情報なし",
                
                "day2_afternoon_time": "13:00",
                "day2_afternoon_desc": "観光プランの生成中にエラーが発生しました",
                "day2_afternoon_highlights": "情報なし",
                "day2_afternoon_duration": "情報なし",
                
                "day2_evening_time": "18:00",
                "day2_evening_desc": "観光プランの生成中にエラーが発生しました",
                "day2_evening_highlights": "情報なし",
                "day2_evening_duration": "情報なし"
            }

        # 全ての情報を統合
        plan_data = {
            "destination": destination_data['destination'],
            "prefecture": destination_data['prefecture'],
            "mbti_points": mbti_points,  # MBTIポイントを追加
            **destination_info,
            **transport_info,
            **hotel_info,
            **day1_schedule,
            **day2_schedule
        }

        # デバッグ用に各データの内容を出力
        logger.info("=== プランデータの内容 ===")
        logger.info(f"destination: {destination_data['destination']}")
        logger.info(f"prefecture: {destination_data['prefecture']}")
        logger.info(f"destination_info: {json.dumps(destination_info, ensure_ascii=False, indent=2)}")
        logger.info(f"transport_info: {json.dumps(transport_info, ensure_ascii=False, indent=2)}")
        
        # テンプレートに適用
        try:
            # 全ての値を文字列に変換し、Noneを適切なデフォルト値に置換
            formatted_data = {}
            for k, v in plan_data.items():
                if v is None:
                    formatted_data[k] = "情報なし"
                else:
                    try:
                        formatted_data[k] = str(v)
                    except Exception as str_err:
                        logger.error(f"値の文字列変換でエラー - キー: {k}, 値: {v}, エラー: {str(str_err)}")
                        formatted_data[k] = "情報なし"
            
            logger.info("=== フォーマット済みデータ ===")
            logger.info(f"フォーマット済みデータの長さ: {len(formatted_data)}")
            logger.info(f"フォーマット済みデータのキー: {', '.join(formatted_data.keys())}")
            
            # テンプレート内の全ての変数が存在するか確認
            template = Template(TRAVEL_PLAN_TEMPLATE)
            template_vars = []
            for v in Template.pattern.findall(TRAVEL_PLAN_TEMPLATE):
                var_name = v[1] or v[2]
                template_vars.append(var_name)
                
            logger.info(f"テンプレート内の変数数: {len(template_vars)}")
            logger.info(f"テンプレート内の変数: {', '.join(template_vars)}")
            
            missing_vars = [var for var in template_vars if var not in formatted_data]
            
            if missing_vars:
                logger.warning(f"テンプレートに存在するが、データにない変数: {', '.join(missing_vars)}")
                for var in missing_vars:
                    formatted_data[var] = "情報なし"
            
            try:
                formatted_plan = template.safe_substitute(formatted_data)
                logger.info(f"テンプレート適用結果の長さ: {len(formatted_plan)}")
                logger.info("テンプレートの適用が完了しました")
            except Exception as template_err:
                logger.error(f"テンプレート置換でエラー: {str(template_err)}", exc_info=True)
                raise TravelPlanError(
                    message="テンプレートの置換処理でエラーが発生しました",
                    error_code="TEMPLATE_ERROR",
                    details={"error": str(template_err)}
                )
            
        except Exception as e:
            logger.error(f"テンプレート適用でエラー: {str(e)}", exc_info=True)
            logger.error("=== 利用可能な変数 ===")
            for key in plan_data.keys():
                logger.error(f"{key}")
            raise TravelPlanError(
                message="テンプレートの適用に失敗しました",
                error_code="TEMPLATE_ERROR",
                details={"error": str(e), "available_variables": list(plan_data.keys())}
            )
        
        logger.info("旅行プランの生成が完了しました")
        return formatted_plan
        
    except ValidationError as e:
        logger.error(f"入力値の検証でエラー: {str(e)}")
        raise
    except APIError as e:
        logger.error(f"API呼び出しでエラー: {str(e)}")
        raise
    except BudgetError as e:
        logger.error(f"予算計算でエラー: {str(e)}")
        raise
    except json.JSONDecodeError as e:
        logger.error(f"JSONパースエラー: {str(e)}")
        raise TravelPlanError(
            message="JSONデータの処理に失敗しました",
            error_code="JSON_PARSE_ERROR",
            details={"error": str(e)}
        )
    except Exception as e:
        logger.error(f"予期せぬエラー: {str(e)}", exc_info=True)
        raise TravelPlanError(
            message="旅行プランの生成に失敗しました",
            error_code="GENERATION_ERROR",
            details={"error": str(e)}
        ) 