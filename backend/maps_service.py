import os
import logging
import googlemaps
from dotenv import load_dotenv
from typing import Dict
from pathlib import Path

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
        
        logger.info(f"ホテル詳細の取得に成功: {result.get('result', {}).get('name', '不明')}")
        return result.get('result', {})
    except Exception as e:
        logger.error(f"ホテル詳細の取得でエラー: {str(e)}")
        return {} 