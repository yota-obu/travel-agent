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
### 基本情報
- **施設名**: ${hotel_name}
- **タイプ**: ${hotel_type}
- **予算目安**: ${hotel_budget}円（1泊あたり）
- **特徴**: ${hotel_features}

### 詳細情報
${hotel_details}

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
        
        # ホテル予算のバリデーション（宿泊がある場合のみ）
        if plan_data.get('hotel_budget') is not None:
            try:
                hotel_budget = int(str(plan_data.get("hotel_budget", "0")).replace(",", "").replace("円", ""))
                if hotel_budget < 0:  # 0円は許可する
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
                #top_p=0.8,
                #top_k=40
            )
        )
        return response.text.strip()
    except Exception as e:
        logger.error(f"目的地提案でエラーが発生: {str(e)}")
        return "東京"  # デフォルトの目的地

def get_hotel_recommendations(location: str, max_price_level: int = 3, budget_per_night: int = None) -> List[Dict]:
    """Google Maps APIを使用してホテルを検索する"""
    try:
        # 場所の検索
        geocode_result = gmaps.geocode(location)
        if not geocode_result:
            logger.error(f"場所が見つかりません: {location}")
            # 都道府県レベルで再検索
            prefecture = location.split()[0]  # 最初の都道府県名を取得
            geocode_result = gmaps.geocode(prefecture)
            if not geocode_result:
                logger.error(f"都道府県も見つかりません: {prefecture}")
                return []

        location_lat_lng = geocode_result[0]['geometry']['location']
        
        # 予算に応じた検索条件の設定
        search_params = []
        if budget_per_night:
            if budget_per_night < 20000:  # 1万円未満：格安プラン
                search_params = [
                    {'keyword': 'ビジネスホテル', 'radius': 20000},
                    {'keyword': '民宿', 'radius': 30000},
                    {'keyword': '格安ホテル', 'radius': 20000}
                ]
            elif budget_per_night < 50000:  # 3万円未満：標準プラン
                search_params = [
                    {'keyword': '温泉旅館', 'radius': 20000},
                    {'keyword': '旅館', 'radius': 30000},
                    {'keyword': 'ホテル', 'radius': 20000}
                ]
            else:  # 3万円以上：高級プラン
                search_params = [
                    {'keyword': '高級温泉旅館', 'radius': 30000},
                    {'keyword': 'リゾートホテル', 'radius': 40000},
                    {'keyword': '高級ホテル', 'radius': 30000}
                ]
        else:  # 予算指定なし：標準プラン
            search_params = [
                {'keyword': '温泉旅館', 'radius': 20000},
                {'keyword': 'ホテル', 'radius': 30000},
                {'keyword': '旅館', 'radius': 20000}
            ]

        hotels = []
        seen_hotels = set()  # 重複チェック用

        for param in search_params:
            try:
                logger.info(f"検索条件: {param}")
                # ホテルの検索
                places_result = gmaps.places_nearby(
                    location=location_lat_lng,
                    radius=param['radius'],
                    type='lodging',
                    keyword=param['keyword'],
                    language='ja'
                )

                if not places_result.get('results'):
                    logger.warning(f"検索条件 {param} で結果が見つかりませんでした")
                    continue

                logger.info(f"検索結果件数: {len(places_result.get('results', []))}")

                for place in places_result.get('results', []):
                    if len(hotels) >= 5:  # 最大5件まで
                        break

                    try:
                        # 場所の詳細情報を取得
                        details = get_hotel_details(place['place_id'])
                        if not details:
                            logger.warning(f"ホテル詳細が取得できませんでした: {place.get('name', '不明')}")
                            continue

                        # 重複チェック
                        if details.get('name') in seen_hotels:
                            continue
                        seen_hotels.add(details.get('name'))

                        # 評価数が少ないものはスキップ
                        if details.get('user_ratings_total', 0) < 50:  # 最小評価数を増やす
                            continue

                        # 評価が低いものはスキップ
                        if details.get('rating', 0) < 3.5:  # 最小評価を設定
                            continue

                        hotel = {
                            'name': details.get('name', ''),
                            'rating': details.get('rating', 0),
                            'price_level': details.get('price_level', 2),
                            'formatted_address': details.get('formatted_address', ''),
                            'website': details.get('website', ''),
                            'phone': details.get('formatted_phone_number', ''),
                            'total_ratings': details.get('user_ratings_total', 0),
                            'photos': [],
                            'reviews': []
                        }

                        # 写真の取得（最大3枚）
                        if 'photos' in details:
                            for photo in details['photos'][:3]:
                                photo_url = f"https://maps.googleapis.com/maps/api/place/photo?maxwidth=800&photoreference={photo['photo_reference']}&key={GOOGLE_MAPS_API_KEY}"
                                hotel['photos'].append(photo_url)

                        # レビューの取得（最大3件、日本語優先）
                        if 'reviews' in details:
                            ja_reviews = [r for r in details['reviews'] if r.get('language') == 'ja']
                            other_reviews = [r for r in details['reviews'] if r.get('language') != 'ja']
                            selected_reviews = (ja_reviews + other_reviews)[:3]
                            
                            for review in selected_reviews:
                                hotel['reviews'].append({
                                    'rating': review.get('rating', 0),
                                    'text': review.get('text', ''),
                                    'time': review.get('relative_time_description', ''),
                                    'language': review.get('language', '')
                                })

                        hotels.append(hotel)
                        logger.info(f"ホテルを追加: {hotel['name']}")

                    except Exception as e:
                        logger.warning(f"個別のホテル詳細取得でエラー: {str(e)}")
                        continue

            except Exception as e:
                logger.warning(f"検索パラメータ {param} でのホテル検索でエラー: {str(e)}")
                continue

            if len(hotels) >= 3:  # 十分なホテルが見つかった場合は次の検索条件をスキップ
                break

        # 評価とレビュー数でスコアを計算してソート
        for hotel in hotels:
            hotel['score'] = (hotel['rating'] * math.log10(hotel['total_ratings'] + 1)) / 5.0

        hotels.sort(key=lambda x: x['score'], reverse=True)
        
        # 予算に応じてフィルタリング
        if budget_per_night:
            hotels = [h for h in hotels if h['price_level'] <= max_price_level]

        logger.info(f"最終的なホテル件数: {len(hotels)}")
        return hotels[:5]  # 上位5件を返す

    except Exception as e:
        logger.error(f"ホテル検索でエラー: {str(e)}")
        return []

def format_hotel_info(hotels: List[Dict]) -> str:
    """ホテル情報を文字列にフォーマット"""
    if not hotels:
        return "申し訳ありません。条件に合う宿泊施設が見つかりませんでした。"

    info = "\n\n## おすすめの宿泊施設\n"
    price_level_map = {
        0: "不明",
        1: "お手頃（〜10,000円）",
        2: "中程度（10,000円〜20,000円）",
        3: "高級（20,000円〜40,000円）",
        4: "超高級（40,000円〜）"
    }

    for i, hotel in enumerate(hotels, 1):
        info += f"\n### {i}. {hotel['name']}\n"
        info += f"**評価**: ★{hotel['rating']:.1f} ({hotel['total_ratings']}件のレビュー)\n"
        info += f"**価格帯**: {price_level_map.get(hotel['price_level'], '不明')}\n"
        info += f"**住所**: {hotel['formatted_address']}\n"
        
        if hotel['phone']:
            info += f"**電話**: {hotel['phone']}\n"
        
        if hotel['website']:
            info += f"**ウェブサイト**: {hotel['website']}\n"
        
        if hotel['reviews']:
            info += "\n**レビュー抜粋**:\n"
            for review in hotel['reviews']:
                # 日本語のレビューを優先して表示
                lang_mark = "🇯🇵" if review['language'] == 'ja' else "🌐"
                info += f"- {lang_mark} ★{review['rating']} - {review['time']}\n"
                info += f"  「{review['text'][:150]}」\n"
                if len(review['text']) > 150:
                    info += "  ...\n"
        
        if hotel['photos']:
            info += "\n**施設写真**:\n"
            for photo_url in hotel['photos']:
                info += f"- {photo_url}\n"
        
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
    """一人当たりの予算を計算する"""
    return {
        "per_person": total_budget,  # 一人当たりの総予算（入力値をそのまま使用）
        "transport_budget": int(total_budget * 0.3),  # 30%を交通費に
        "accommodation_budget": int(total_budget * 0.4),  # 40%を宿泊費に
        "food_budget": int(total_budget * 0.15),  # 15%を食事代に
        "activity_budget": int(total_budget * 0.1),  # 10%をアクティビティに
        "extra_budget": int(total_budget * 0.05)  # 5%を予備費に
    }

def generate_travel_plan(members: List[Dict], departure: str, month: int, nights: int, budget: int) -> str:
    try:
        logger.info("旅行プラン生成を開始します")
        logger.info(f"入力パラメータ: 出発地={departure}, 月={month}, 宿泊数={nights}, 一人当たり予算={budget}円")
        
        # グループの特性を分析
        preference_scores = analyze_group_preferences(members)
        logger.info(f"グループ特性スコア: {preference_scores}")
        
        # 目的地を提案
        try:
            destination = suggest_destinations(departure, month, preference_scores)
            logger.info(f"提案された目的地: {destination}")
        except Exception as e:
            raise APIError(f"目的地の提案に失敗しました: {str(e)}")
        
        # MBTIタイプに基づく特性を分析
        mbti_types = [member['mbti'] for member in members]
        mbti_points = "グループのMBTIタイプ分析：\n"
        for mbti in mbti_types:
            if mbti == "ENFP":
                mbti_points += "- 新しい体験を好み、自由な行動を好む傾向\n"
            elif mbti == "UNKNOWN":
                mbti_points += "- 一般的な観光スポットと地元の穴場スポットをバランスよく\n"
        
        # 交通手段の詳細を設定
        transport_info = {
            "train_duration": "2時間30分",
            "train_cost": "12000",
            "train_cost_per": "人",
            "train_pros": "定時性が高く、移動中も快適",
            "train_cons": "駅から観光地までの二次交通が必要",
            
            "plane_duration": "利用不可",
            "plane_cost": "利用不可",
            "plane_cost_per": "人",
            "plane_pros": "近距離のため利用不推奨",
            "plane_cons": "近距離のため費用対効果が低い",
            
            "car_duration": "3時間00分",
            "car_cost": "15000",
            "car_cost_per": "台",
            "car_pros": "観光地を自由に周遊可能",
            "car_cons": "交通渋滞の可能性あり、駐車場の確保が必要"
        }
        
        # 基本情報を設定
        plan_data = {
            "destination": destination,
            "destination_features": "自然豊かな温泉地として知られる観光地。河津桜や梅林など季節の花々、浄蓮の滝などの自然スポットが点在。",
            "seasonal_highlights": f"{month}月は春の訪れを感じる季節。河津桜や梅の花が見頃を迎え、温暖な気候で観光に最適。",
            "recommended_transport": "東京駅から新幹線で三島駅まで約1時間。その後、伊豆箱根鉄道に乗り換えて修善寺駅へ。",
            "mbti_points": mbti_points,
            
            # 1日目のスケジュール
            "day1_morning_time": "09:00",
            "day1_morning_desc": "修善寺温泉街を散策。竹林の小径や修禅寺を訪れる。",
            "day1_morning_highlights": "風情ある温泉街の雰囲気と歴史的建造物",
            "day1_morning_duration": "2時間00分",
            "day1_morning_budget": "0",
            
            "day1_afternoon_time": "11:30",
            "day1_afternoon_desc": "地元の名物料理を堪能した後、河津桜の名所を巡る。",
            "day1_afternoon_highlights": "季節の花と地元グルメ",
            "day1_afternoon_duration": "3時間00分",
            "day1_afternoon_budget": "3000",
            
            "day1_evening_time": "15:00",
            "day1_evening_desc": "温泉旅館でチェックインと夕食",
            "day1_evening_highlights": "高級旅館の夕食と温泉",
            "day1_evening_duration": "3時間00分",
            "day1_evening_budget": "20000",
            
            # 2日目のスケジュール
            "day2_morning_time": "09:00",
            "day2_morning_desc": "浄蓮の滝と周辺散策",
            "day2_morning_highlights": "迫力ある滝と自然景観",
            "day2_morning_duration": "2時間00分",
            "day2_morning_budget": "500",
            
            "day2_afternoon_time": "11:30",
            "day2_afternoon_desc": "地元の海鮮料理を楽しんだ後、伊豆パノラマパークで絶景を楽しむ",
            "day2_afternoon_highlights": "新鮮な海の幸と富士山の眺望",
            "day2_afternoon_duration": "3時間00分",
            "day2_afternoon_budget": "4000",
            
            "day2_evening_time": "15:00",
            "day2_evening_desc": "お土産購入と帰路",
            "day2_evening_highlights": "地元の特産品",
            "day2_evening_duration": "2時間00分",
            "day2_evening_budget": "3000"
        }
        
        # 交通手段の情報を追加
        plan_data.update(transport_info)
        
        # 予算計算（一人当たり）
        budget_info = calculate_per_person_budget(budget, len(members))
        plan_data.update(budget_info)
        
        # ホテル情報を取得（一人当たりの宿泊予算で検索）
        if nights > 0:
            hotels = get_hotel_recommendations(
                location=destination,
                max_price_level=3,
                budget_per_night=budget_info["accommodation_budget"]
            )
            if hotels:
                hotel = hotels[0]  # 最初のホテルを使用
                plan_data.update({
                    "hotel_name": hotel.get("name", "情報なし"),
                    "hotel_type": "温泉旅館",
                    "hotel_budget": str(budget_info["accommodation_budget"]),
                    "hotel_features": "温泉、日本庭園、会席料理",
                    "hotel_details": format_hotel_info([hotel])
                })
            else:
                plan_data.update({
                    "hotel_name": "情報なし",
                    "hotel_type": "情報なし",
                    "hotel_budget": str(budget_info["accommodation_budget"]),
                    "hotel_features": "情報なし",
                    "hotel_details": "宿泊施設の詳細情報は利用できません。"
                })
        
        # テンプレートに適用
        template = Template(TRAVEL_PLAN_TEMPLATE)
        formatted_plan = template.safe_substitute(plan_data)
        
        logger.info("旅行プランの生成が完了しました")
        return formatted_plan
        
    except Exception as e:
        logger.error(f"旅行プラン生成でエラー: {str(e)}")
        raise TravelPlanError(
            message="旅行プランの生成に失敗しました",
            error_code="GENERATION_ERROR",
            details={"error": str(e)}
        ) 