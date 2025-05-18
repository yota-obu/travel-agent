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

# ロギングの設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

load_dotenv()

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

# じゃらんAPIの設定
JALAN_API_KEY = os.getenv('JALAN_API_KEY')
JALAN_API_URL = "https://app.jalan.net/jalan/api/hotelSearch/V1/"

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
- **概算費用**: ${train_cost}（${train_cost_per}あたり・往復）
- **メリット**: ${train_pros}
- **デメリット**: ${train_cons}

#### 飛行機での移動
- **所要時間**: ${plane_duration}
- **概算費用**: ${plane_cost}（${plane_cost_per}あたり・往復）
- **メリット**: ${plane_pros}
- **デメリット**: ${plane_cons}

#### レンタカーでの移動
- **所要時間**: ${car_duration}
- **概算費用**: ${car_cost}（${car_cost_per}あたり・往復）
- **メリット**: ${car_pros}
- **デメリット**: ${car_cons}

## 宿泊施設
### おすすめの宿泊施設
- **施設名**: ${hotel_name}
- **タイプ**: ${hotel_type}
- **予算目安**: ${hotel_budget}円（1泊あたり）
- **特徴**: ${hotel_features}

## 観光プラン
### 1日目
#### 午前（${day1_morning_time}）
${day1_morning_desc}

**見どころ**: ${day1_morning_highlights}  
**所要時間**: ${day1_morning_duration}  
**予算目安**: ${day1_morning_budget}円

#### 午後（${day1_afternoon_time}）
${day1_afternoon_desc}

**見どころ**: ${day1_afternoon_highlights}  
**所要時間**: ${day1_afternoon_duration}  
**予算目安**: ${day1_afternoon_budget}円

#### 夜（${day1_evening_time}）
${day1_evening_desc}

**見どころ**: ${day1_evening_highlights}  
**所要時間**: ${day1_evening_duration}  
**予算目安**: ${day1_evening_budget}円

### 2日目
#### 午前（${day2_morning_time}）
${day2_morning_desc}

**見どころ**: ${day2_morning_highlights}  
**所要時間**: ${day2_morning_duration}  
**予算目安**: ${day2_morning_budget}円

#### 午後（${day2_afternoon_time}）
${day2_afternoon_desc}

**見どころ**: ${day2_afternoon_highlights}  
**所要時間**: ${day2_afternoon_duration}  
**予算目安**: ${day2_afternoon_budget}円

#### 夜（${day2_evening_time}）
${day2_evening_desc}

**見どころ**: ${day2_evening_highlights}  
**所要時間**: ${day2_evening_duration}  
**予算目安**: ${day2_evening_budget}円

## 予算配分
| 項目 | 金額 |
|------|------|
| 交通費 | ${transport_budget}円 |
| 宿泊費 | ${accommodation_budget}円 |
| 食事代 | ${food_budget}円 |
| 観光・アクティビティ | ${activity_budget}円 |
| 予備費 | ${extra_budget}円 |
| **合計** | ${total_budget}円 |"""

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

def clean_response_text(text: str) -> str:
    """Gemini APIのレスポンステキストをクリーンアップする"""
    try:
        # コードブロックの削除
        text = text.strip()
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        
        # 余分な空白と改行の削除
        text = text.strip()
        
        # JSONとして解析できるか確認
        json.loads(text)
        
        return text
    except json.JSONDecodeError as e:
        logger.error(f"JSONパースエラー: {str(e)}")
        logger.error(f"パース対象のテキスト: {text}")
        raise ValidationError("レスポンスのJSON形式が不正です", details={'error': str(e), 'text': text})

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
                top_p=0.8,
                top_k=40
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
            "destination", "destination_features", "seasonal_highlights",
            "recommended_transport", "hotel_name", "hotel_budget",
            "day1_morning_time", "day1_morning_desc",
            "day1_afternoon_time", "day1_afternoon_desc",
            "day1_evening_time", "day1_evening_desc"
        ]
        
        missing_fields = [field for field in required_fields if field not in plan_data]
        if missing_fields:
            logger.error(f"必須フィールドが不足: {missing_fields}")
            errors['missing_fields'] = missing_fields
        
        # ホテル予算のバリデーション
        try:
            hotel_budget = int(str(plan_data.get("hotel_budget", "0")).replace(",", "").replace("円", ""))
            if hotel_budget <= 0:
                logger.error(f"不正なホテル予算: {hotel_budget}")
                errors['hotel_budget'] = "ホテル予算が不正です"
        except (ValueError, TypeError) as e:
            logger.error(f"ホテル予算の変換エラー: {str(e)}")
            errors['hotel_budget'] = "ホテル予算は数値で指定してください"
        
        # 時間形式のバリデーション
        time_fields = [
            "day1_morning_time",
            "day1_afternoon_time",
            "day1_evening_time"
        ]
        
        time_errors = {}
        for field in time_fields:
            if field in plan_data:
                time_str = plan_data[field]
                if not time_str or not isinstance(time_str, str) or ":" not in time_str:
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

def suggest_destinations(departure: str, month: int, scores: Dict[str, float]) -> str:
    """グループの特性と条件に基づいて目的地を提案する"""
    prompt = f"""
以下の条件に基づいて、最適な旅行先を1つ提案してください。
提案は具体的な地名（市町村レベル）で、理由も含めて返してください。

出発地: {departure}
旅行月: {month}月

グループの特性スコア（0-1のスケール）:
アクティビティ志向: {scores['activity']:.2f}
文化的活動志向: {scores['culture']:.2f}
自然志向: {scores['nature']:.2f}
都市的活動志向: {scores['urban']:.2f}
リラックス志向: {scores['relaxation']:.2f}

注意点：
1. 季節に適した目的地を選んでください
2. 出発地からのアクセスを考慮してください
3. グループの特性スコアを重視してください
4. 具体的な地名を1つだけ提案してください
"""
    
    try:
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.2,
                max_output_tokens=150,
                top_p=0.8,
                top_k=40
            )
        )
        return response.text.strip()
    except Exception as e:
        logger.error(f"目的地提案でエラーが発生: {str(e)}")
        return "東京"  # デフォルトの目的地

def get_hotel_recommendations(location: str, max_price_level: int = 3) -> List[Dict]:
    """Google Maps APIを使用してホテルを検索する"""
    try:
        # 場所の検索
        geocode_result = gmaps.geocode(location)
        if not geocode_result:
            logger.error(f"場所が見つかりません: {location}")
            return []

        location_lat_lng = geocode_result[0]['geometry']['location']
        
        # ホテルの検索
        places_result = gmaps.places_nearby(
            location=location_lat_lng,
            radius=5000,  # 5km以内
            type='lodging',  # ホテル・宿泊施設
            keyword='ホテル OR 旅館',
            language='ja'
        )

        hotels = []
        for place in places_result.get('results', [])[:5]:  # 上位5件を処理
            # 場所の詳細情報を取得
            details = gmaps.place(place['place_id'], language='ja')['result']
            
            hotel = {
                'name': details.get('name', ''),
                'rating': details.get('rating', 0),
                'price_level': details.get('price_level', 0),
                'formatted_address': details.get('formatted_address', ''),
                'photos': [],
                'reviews': []
            }

            # 写真の取得（最大3枚）
            if 'photos' in details:
                for photo in details['photos'][:3]:
                    photo_url = f"https://maps.googleapis.com/maps/api/place/photo?maxwidth=400&photoreference={photo['photo_reference']}&key={GOOGLE_MAPS_API_KEY}"
                    hotel['photos'].append(photo_url)

            # レビューの取得（最大3件）
            if 'reviews' in details:
                for review in details['reviews'][:3]:
                    hotel['reviews'].append({
                        'rating': review.get('rating', 0),
                        'text': review.get('text', ''),
                        'time': review.get('relative_time_description', '')
                    })

            hotels.append(hotel)

        # 評価でソート
        hotels.sort(key=lambda x: x['rating'], reverse=True)
        return hotels[:3]  # 上位3件を返す

    except Exception as e:
        logger.error(f"ホテル検索エラー: {str(e)}")
        return []

def format_hotel_info(hotels: List[Dict]) -> str:
    """ホテル情報を文字列にフォーマット"""
    if not hotels:
        return ""

    info = "\n\n【おすすめの宿泊施設】\n"
    price_level_map = {
        0: "不明",
        1: "お手頃",
        2: "中程度",
        3: "高級",
        4: "超高級"
    }

    for i, hotel in enumerate(hotels, 1):
        info += f"{i}. {hotel['name']}\n"
        info += f"   住所: {hotel['formatted_address']}\n"
        info += f"   評価: {hotel['rating']}点\n"
        info += f"   価格帯: {price_level_map.get(hotel['price_level'], '不明')}\n"
        
        if hotel['reviews']:
            info += "   最新のレビュー:\n"
            for review in hotel['reviews'][:1]:  # 最新の1件のみ表示
                info += f"   「{review['text'][:100]}...」\n"
                info += f"   （評価: {review['rating']}点, {review['time']}）\n"
        
        info += "\n"

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

def calculate_per_person_budget(total_budget: int, num_members: int) -> Dict[str, int]:
    """グループ予算から一人あたりの予算を計算する"""
    return {
        "per_person": total_budget // num_members,
        "transport_budget": (total_budget * 0.3) // num_members,
        "accommodation_budget": (total_budget * 0.4) // num_members,
        "food_budget": (total_budget * 0.15) // num_members,
        "activity_budget": (total_budget * 0.1) // num_members,
        "extra_budget": (total_budget * 0.05) // num_members
    }

def generate_travel_plan(members: List[Dict], departure: str, month: int, nights: int, budget: int) -> str:
    """旅行プランを生成する"""
    try:
        logger.info("旅行プラン生成を開始します")
        logger.info(f"入力パラメータ: 出発地={departure}, 月={month}, 宿泊数={nights}, グループ予算={budget}円")
        
        if not members:
            raise ValidationError("メンバー情報が指定されていません", details={'field': 'members'})
        
        if not departure:
            raise ValidationError("出発地が指定されていません", details={'field': 'departure'})
        
        if not (1 <= month <= 12):
            raise ValidationError("月は1-12の範囲で指定してください", details={'field': 'month'})
        
        if nights <= 0:
            raise ValidationError("宿泊数は1泊以上で指定してください", details={'field': 'nights'})
        
        if budget <= 0:
            raise BudgetError("予算は0円より大きい値を指定してください")
        
        # グループの特性を分析
        preference_scores = analyze_group_preferences(members)
        logger.info(f"グループ特性スコア: {preference_scores}")
        
        # 目的地を提案
        try:
            destination = suggest_destinations(departure, month, preference_scores)
            logger.info(f"提案された目的地: {destination}")
        except Exception as e:
            raise APIError(f"目的地の提案に失敗しました: {str(e)}")
        
        # メンバー情報を文字列に変換
        members_info = "\n".join([
            f"メンバー{i+1}: 年齢{m['age']}歳, 性別{m['gender']}, MBTI{m['mbti']}"
            for i, m in enumerate(members)
        ])
        
        # 予算計算
        num_members = len(members)
        budget_info = calculate_per_person_budget(budget, num_members)
        
        # Google Maps APIでホテルを検索
        hotels = []
        if nights > 0:  # 日帰りでない場合のみホテルを検索
            # 予算に応じて価格帯を設定
            if budget_info["accommodation_budget"] < 10000:
                price_level = 1
            elif budget_info["accommodation_budget"] < 20000:
                price_level = 2
            else:
                price_level = 3
                
            hotels = get_hotel_recommendations(departure, price_level)
        
        # プロンプトの生成と旅行プラン取得
        base_prompt = f"""
以下の条件に基づいて旅行プランを作成し、必ず以下のJSON形式で返してください。
余計な説明は一切不要です。必ずJSONオブジェクトのみを返してください。

必須フィールド:
- destination (目的地)
- destination_features (目的地の特徴)
- seasonal_highlights (季節の見どころ)
- mbti_points (MBTIタイプに合わせたポイント)
- recommended_transport (おすすめの交通手段)
- train_duration (電車での所要時間)
- train_cost (電車での費用)
- train_cost_per (電車での費用の単位)
- train_pros (電車のメリット)
- train_cons (電車のデメリット)
- plane_duration (飛行機での所要時間)
- plane_cost (飛行機での費用)
- plane_cost_per (飛行機での費用の単位)
- plane_pros (飛行機のメリット)
- plane_cons (飛行機のデメリット)
- car_duration (車での所要時間)
- car_cost (車での費用)
- car_cost_per (車での費用の単位)
- car_pros (車のメリット)
- car_cons (車のデメリット)
- hotel_name (ホテル名)
- hotel_type (ホテルタイプ)
- hotel_budget (ホテル予算)
- hotel_features (ホテルの特徴)
- day1_morning_time (1日目午前の時間)
- day1_morning_desc (1日目午前の説明)
- day1_morning_highlights (1日目午前の見どころ)
- day1_morning_duration (1日目午前の所要時間)
- day1_morning_budget (1日目午前の予算)
- day1_afternoon_time (1日目午後の時間)
- day1_afternoon_desc (1日目午後の説明)
- day1_afternoon_highlights (1日目午後の見どころ)
- day1_afternoon_duration (1日目午後の所要時間)
- day1_afternoon_budget (1日目午後の予算)
- day1_evening_time (1日目夜の時間)
- day1_evening_desc (1日目夜の説明)
- day1_evening_highlights (1日目夜の見どころ)
- day1_evening_duration (1日目夜の所要時間)
- day1_evening_budget (1日目夜の予算)
- day2_morning_time (2日目午前の時間)
- day2_morning_desc (2日目午前の説明)
- day2_morning_highlights (2日目午前の見どころ)
- day2_morning_duration (2日目午前の所要時間)
- day2_morning_budget (2日目午前の予算)
- day2_afternoon_time (2日目午後の時間)
- day2_afternoon_desc (2日目午後の説明)
- day2_afternoon_highlights (2日目午後の見どころ)
- day2_afternoon_duration (2日目午後の所要時間)
- day2_afternoon_budget (2日目午後の予算)
- day2_evening_time (2日目夜の時間)
- day2_evening_desc (2日目夜の説明)
- day2_evening_highlights (2日目夜の見どころ)
- day2_evening_duration (2日目夜の所要時間)
- day2_evening_budget (2日目夜の予算)

【基本情報】
目的地: {destination}
出発地: {departure}
旅行月: {month}月
宿泊数: {nights}泊
グループ予算: {budget}円（{num_members}人で合計）
一人あたり予算: {budget_info["per_person"]}円

【グループ特性】
{members_info}

グループの傾向:
- アクティビティ志向: {preference_scores['activity']:.2f}
- 文化的活動志向: {preference_scores['culture']:.2f}
- 自然志向: {preference_scores['nature']:.2f}
- 都市的活動志向: {preference_scores['urban']:.2f}
- リラックス志向: {preference_scores['relaxation']:.2f}

【プラン作成の制約条件】
1. グループ全体の予算は{budget}円以内に必ず収めること
2. 交通費は往復料金を計算すること
3. 食事代は1人1食あたり1000-5000円の範囲で設定すること
4. 各アクティビティは具体的な所要時間と予算を含めること
5. 移動時間は実際の所要時間を反映させること（○時間○分の形式で記載）
6. 季節に応じた活動を提案すること
7. グループの特性スコアを考慮した活動を提案すること
8. 時間は「HH:MM」形式で指定すること（例: 09:00）
9. 所要時間は「○時間○分」形式で指定すること（例: 2時間30分）
10. 予算は数値のみで指定すること（例: 3000）

以下の形式で回答してください:
{{
    "destination": "目的地名",
    "destination_features": "目的地の特徴説明",
    "seasonal_highlights": "季節の見どころ説明",
    "mbti_points": "MBTIタイプに合わせたポイント",
    "recommended_transport": "おすすめの交通手段",
    "train_duration": "電車での所要時間",
    "train_cost": "電車での費用",
    "train_cost_per": "電車での費用の単位",
    "train_pros": "電車のメリット",
    "train_cons": "電車のデメリット",
    "plane_duration": "飛行機での所要時間",
    "plane_cost": "飛行機での費用",
    "plane_cost_per": "飛行機での費用の単位",
    "plane_pros": "飛行機のメリット",
    "plane_cons": "飛行機のデメリット",
    "car_duration": "車での所要時間",
    "car_cost": "車での費用",
    "car_cost_per": "車での費用の単位",
    "car_pros": "車のメリット",
    "car_cons": "車のデメリット",
    "hotel_name": "ホテル名",
    "hotel_type": "ホテルタイプ",
    "hotel_budget": "ホテル予算（数値）",
    "hotel_features": "ホテルの特徴",
    "day1_morning_time": "1日目午前の時間（HH:MM形式）",
    "day1_morning_desc": "1日目午前の説明",
    "day1_morning_highlights": "1日目午前の見どころ",
    "day1_morning_duration": "1日目午前の所要時間",
    "day1_morning_budget": "1日目午前の予算（数値）",
    "day1_afternoon_time": "1日目午後の時間（HH:MM形式）",
    "day1_afternoon_desc": "1日目午後の説明",
    "day1_afternoon_highlights": "1日目午後の見どころ",
    "day1_afternoon_duration": "1日目午後の所要時間",
    "day1_afternoon_budget": "1日目午後の予算（数値）",
    "day1_evening_time": "1日目夜の時間（HH:MM形式）",
    "day1_evening_desc": "1日目夜の説明",
    "day1_evening_highlights": "1日目夜の見どころ",
    "day1_evening_duration": "1日目夜の所要時間",
    "day1_evening_budget": "1日目夜の予算（数値）",
    "day2_morning_time": "2日目午前の時間（HH:MM形式）",
    "day2_morning_desc": "2日目午前の説明",
    "day2_morning_highlights": "2日目午前の見どころ",
    "day2_morning_duration": "2日目午前の所要時間",
    "day2_morning_budget": "2日目午前の予算（数値）",
    "day2_afternoon_time": "2日目午後の時間（HH:MM形式）",
    "day2_afternoon_desc": "2日目午後の説明",
    "day2_afternoon_highlights": "2日目午後の見どころ",
    "day2_afternoon_duration": "2日目午後の所要時間",
    "day2_afternoon_budget": "2日目午後の予算（数値）",
    "day2_evening_time": "2日目夜の時間（HH:MM形式）",
    "day2_evening_desc": "2日目夜の説明",
    "day2_evening_highlights": "2日目夜の見どころ",
    "day2_evening_duration": "2日目夜の所要時間",
    "day2_evening_budget": "2日目夜の予算（数値）"
}}
"""

        # ランダム性を追加
        prompt = add_randomness_to_prompt(base_prompt)
        
        # ホテル情報がある場合は追加
        if hotels:
            hotel_info = format_hotel_info(hotels)
            prompt += hotel_info
        
        response_text = generate_content_with_retry(prompt)
        
        try:
            plan_data = json.loads(response_text)
            is_valid, validation_errors = validate_travel_plan(plan_data)
            
            if not is_valid:
                raise ValidationError(
                    "プランの内容が不正です",
                    details=validation_errors
                )
            
            # 予算情報を追加
            plan_data.update({
                "month": month,
                "total_budget": budget,
                "transport_budget": budget_info["transport_budget"],
                "accommodation_budget": budget_info["accommodation_budget"],
                "food_budget": budget_info["food_budget"],
                "activity_budget": budget_info["activity_budget"],
                "extra_budget": budget_info["extra_budget"]
            })
            
            # テンプレートに適用
            template = Template(TRAVEL_PLAN_TEMPLATE)
            formatted_plan = template.safe_substitute(plan_data)
            
            logger.info("旅行プランの生成が完了しました")
            return formatted_plan
            
        except json.JSONDecodeError as e:
            logger.error(f"JSONパースエラー: {str(e)}")
            logger.error(f"受信したテキスト: {response_text}")
            raise ValidationError("プランの形式が不正です: JSONパースエラー")
            
    except TravelPlanError:
        raise
    except Exception as e:
        logger.error(f"予期せぬエラー: {str(e)}")
        raise TravelPlanError(
            message="予期せぬエラーが発生しました",
            error_code="UNEXPECTED_ERROR",
            details={'error': str(e)}
        ) 