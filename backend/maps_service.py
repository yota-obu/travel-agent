import os
import logging
import googlemaps
from dotenv import load_dotenv
from typing import Dict, List
from pathlib import Path
import json

# ロギングの設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 環境変数の読み込み
env_path = Path(__file__).parent / '.env'
load_dotenv(dotenv_path=env_path)

# Google Maps APIの設定
GOOGLE_MAPS_API_KEY = os.getenv('GOOGLE_MAPS_API_KEY')
if not GOOGLE_MAPS_API_KEY:
    logger.error("GOOGLE_MAPS_API_KEYが設定されていません")
    raise Exception("Google Maps API Keyが設定されていません")

logger.info(f"Google Maps APIキーが正しく設定されました")
gmaps = googlemaps.Client(key=GOOGLE_MAPS_API_KEY)

def get_hotel_details(place_id: str) -> Dict:
    """ホテルの詳細情報を取得する"""
    try:
        fields = [
            'name',
            'rating',
            'formatted_address',
            'price_level',
            'user_ratings_total',
            'reviews',
            'photo',
            'website',
            'formatted_phone_number',
            'opening_hours'
        ]
        
        result = gmaps.place(
            place_id,
            fields=fields,
            language='ja'
        )
        
        place_data = result.get('result', {})
        
        # 必要なデータ構造に変換
        hotel_data = {
            'name': place_data.get('name', ''),
            'rating': place_data.get('rating', 0),
            'total_ratings': place_data.get('user_ratings_total', 0),
            'price_level': place_data.get('price_level', 0),
            'formatted_address': place_data.get('formatted_address', ''),
            'website': place_data.get('website', ''),
            'phone': place_data.get('formatted_phone_number', ''),
            'category': 'ホテル',  # デフォルトカテゴリー
            'photos': []
        }
        
        # 写真の取得（最大3枚）
        if 'photos' in place_data:
            for photo in place_data['photos'][:3]:
                photo_url = f"https://maps.googleapis.com/maps/api/place/photo?maxwidth=800&photoreference={photo['photo_reference']}&key={GOOGLE_MAPS_API_KEY}"
                hotel_data['photos'].append(photo_url)
        
        logger.info(f"ホテル詳細の取得に成功: {hotel_data['name']}")
        return hotel_data
    except Exception as e:
        logger.error(f"ホテル詳細の取得でエラー: {str(e)}")
        return {}

def get_hotel_recommendations(location: str, max_price_level: int = 3, budget_per_night: int = None) -> List[Dict]:
    """Google Maps APIを使用してホテルを検索する"""
    try:
        logger.info(f"ホテル検索開始 - 場所: {location}")
        
        # 検索パラメータの設定
        search_params = [
            {
                "keyword": "ホテル",
                "type": "lodging",
                "language": "ja",
                "radius": 5000  # 5km
            },
            {
                "keyword": "旅館",
                "type": "lodging",
                "language": "ja",
                "radius": 5000  # 5km
            }
        ]

        # 予算に応じた価格レベルの設定
        if budget_per_night:
            if budget_per_night >= 30000:
                min_price_level = 3
                max_price_level = 4
            elif budget_per_night >= 15000:
                min_price_level = 2
                max_price_level = 3
            else:
                min_price_level = 1
                max_price_level = 2
        else:
            min_price_level = 1
            max_price_level = 4

        # 場所の位置情報を取得
        geocode_result = gmaps.geocode(location, language='ja')
        if not geocode_result:
            logger.error(f"位置情報が取得できません: {location}")
            return []

        location_data = geocode_result[0]['geometry']['location']
        logger.info(f"位置情報を取得: {json.dumps(location_data, ensure_ascii=False)}")

        all_hotels = []
        seen_hotels = set()

        # 各検索パラメータで検索を実行
        for param in search_params:
            try:
                places_result = gmaps.places_nearby(
                    location=location_data,
                    **param
                )

                if not places_result.get('results'):
                    logger.warning(f"検索結果なし - パラメータ: {json.dumps(param, ensure_ascii=False)}")
                    continue

                hotels = []
                for place in places_result.get('results', []):
                    try:
                        # 詳細情報を取得
                        details = gmaps.place(
                            place['place_id'],
                            language='ja',
                            fields=['name', 'rating', 'price_level', 'formatted_address',
                                   'website', 'formatted_phone_number', 'user_ratings_total',
                                   'photos', 'reviews']
                        )['result']

                        # 評価とレビュー数の最低基準
                        min_rating = 4.0
                        min_reviews = 100

                        # 基準を満たさないものはスキップ
                        if details.get('rating', 0) < min_rating or \
                           details.get('user_ratings_total', 0) < min_reviews:
                            continue

                        # 重複チェック
                        if details.get('name') in seen_hotels:
                            continue
                        seen_hotels.add(details.get('name'))

                        # 価格レベルのチェック
                        price_level = details.get('price_level', 2)
                        if price_level < min_price_level or price_level > max_price_level:
                            continue

                        hotel = {
                            'name': details.get('name', ''),
                            'rating': details.get('rating', 0),
                            'price_level': price_level,
                            'formatted_address': details.get('formatted_address', ''),
                            'website': details.get('website', ''),
                            'phone': details.get('formatted_phone_number', ''),
                            'total_ratings': details.get('user_ratings_total', 0),
                            'photos': [],
                            'category': param['keyword']
                        }

                        # 写真の取得（最大3枚）
                        if 'photos' in details:
                            for photo in details['photos'][:3]:
                                photo_url = f"https://maps.googleapis.com/maps/api/place/photo?maxwidth=800&photoreference={photo['photo_reference']}&key={GOOGLE_MAPS_API_KEY}"
                                hotel['photos'].append(photo_url)

                        hotels.append(hotel)

                    except Exception as e:
                        logger.warning(f"個別のホテル詳細取得でエラー: {str(e)}")
                        continue

                # スコアの計算とソート
                for hotel in hotels:
                    base_score = hotel['rating'] * 2
                    review_weight = min(hotel['total_ratings'] / 100, 2.0)
                    price_adjustment = 0
                    
                    if budget_per_night:
                        if budget_per_night >= 30000:
                            price_adjustment = hotel['price_level'] * 0.2
                        elif budget_per_night < 15000:
                            price_adjustment = (4 - hotel['price_level']) * 0.2
                    
                    hotel['score'] = (base_score * 0.6) + (review_weight * 0.3) + (price_adjustment * 0.1)

                hotels.sort(key=lambda x: x['score'], reverse=True)
                all_hotels.extend(hotels[:2])  # 各カテゴリから上位2件を追加

            except Exception as e:
                logger.warning(f"検索パラメータ {param} でのホテル検索でエラー: {str(e)}")
                continue

        logger.info(f"検索完了 - 合計{len(all_hotels)}件のホテルが見つかりました")
        return all_hotels

    except Exception as e:
        logger.error(f"ホテル検索でエラー: {str(e)}")
        return [] 