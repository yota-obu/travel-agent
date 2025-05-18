from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict, Any
from enum import Enum
from llm_service import generate_travel_plan, TravelPlanError, ValidationError, APIError, BudgetError
import os
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
import logging
import traceback
from datetime import datetime

# ロギングの設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ファイルハンドラーの追加
file_handler = logging.FileHandler('app.log')
file_handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

load_dotenv()

app = FastAPI()

# CORSミドルウェアの設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://frontend:3000"],  # フロントエンドのURL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# エラーハンドリングミドルウェア
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = datetime.now()
    try:
        response = await call_next(request)
        process_time = (datetime.now() - start_time).total_seconds()
        logger.info(
            f"Path: {request.url.path} "
            f"Method: {request.method} "
            f"Status: {response.status_code} "
            f"Process Time: {process_time:.3f}s"
        )
        return response
    except Exception as e:
        process_time = (datetime.now() - start_time).total_seconds()
        logger.error(
            f"Path: {request.url.path} "
            f"Method: {request.method} "
            f"Error: {str(e)} "
            f"Process Time: {process_time:.3f}s"
        )
        logger.error(f"詳細なエラー情報: {traceback.format_exc()}")
        raise

class Gender(str, Enum):
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"

class MBTI(str, Enum):
    UNKNOWN = "UNKNOWN"
    INTJ = "INTJ"
    INTP = "INTP"
    ENTJ = "ENTJ"
    ENTP = "ENTP"
    INFJ = "INFJ"
    INFP = "INFP"
    ENFJ = "ENFJ"
    ENFP = "ENFP"
    ISTJ = "ISTJ"
    ISFJ = "ISFJ"
    ESTJ = "ESTJ"
    ESFJ = "ESFJ"
    ISTP = "ISTP"
    ISFP = "ISFP"
    ESTP = "ESTP"
    ESFP = "ESFP"

class TravelMember(BaseModel):
    age: int
    gender: Gender
    mbti: MBTI

class ErrorResponse(BaseModel):
    message: str
    error_code: str
    details: Dict[str, Any] | None = None

class AccommodationGrade(str, Enum):
    BUDGET = "エコノミー"
    MODERATE = "スタンダード"
    LUXURY = "ラグジュアリー"
    ULTRA_LUXURY = "ウルトララグジュアリー"

class TravelRequest(BaseModel):
    members: List[TravelMember]
    departure_location: str = Field(..., min_length=1)
    departure_region: str = Field(..., min_length=1)
    travel_month: int = Field(..., ge=1, le=12)
    nights: int = Field(..., ge=0, le=1)  # 0（日帰り）または1泊のみ許可
    accommodation_grade: AccommodationGrade

    @validator('members')
    def validate_members(cls, v):
        if not v:
            raise ValueError('少なくとも1人のメンバーを指定してください')
        return v

    @validator('departure_region')
    def validate_departure_region(cls, v):
        valid_regions = ['北海道', '東北', '関東', '中部', '関西', '中国', '四国', '九州', '沖縄']
        if v not in valid_regions:
            raise ValueError('有効な地方を指定してください')
        return v

class TravelResponse(BaseModel):
    travel_plan: str

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.error(f"リクエストバリデーションエラー: {str(exc)}")
    return JSONResponse(
        status_code=422,
        content={
            "message": "リクエストデータが不正です",
            "error_code": "VALIDATION_ERROR",
            "details": {"errors": exc.errors()}
        }
    )

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    logger.error(f"HTTPエラー: {str(exc)}")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "message": str(exc.detail),
            "error_code": "HTTP_ERROR",
            "details": {"status_code": exc.status_code}
        }
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.error(f"予期せぬエラー: {str(exc)}")
    logger.error(f"詳細なエラー情報: {traceback.format_exc()}")
    return JSONResponse(
        status_code=500,
        content={
            "message": "サーバー内部でエラーが発生しました",
            "error_code": "INTERNAL_SERVER_ERROR",
            "details": {"error": str(exc)}
        }
    )

@app.post("/api/travel-plan", response_model=TravelResponse)
async def create_travel_plan(request: TravelRequest):
    try:
        members_dict = [
            {
                "age": member.age,
                "gender": member.gender,
                "mbti": member.mbti
            }
            for member in request.members
        ]

        travel_plan = generate_travel_plan(
            members_dict,
            request.departure_location,
            request.departure_region,
            request.travel_month,
            request.nights,
            request.accommodation_grade
        )

        return {
            "travel_plan": travel_plan
        }

    except ValidationError as e:
        return JSONResponse(
            status_code=422,
            content={
                "message": e.message,
                "error_code": e.error_code,
                "details": e.details
            }
        )
    
    except BudgetError as e:
        return JSONResponse(
            status_code=400,
            content={
                "message": e.message,
                "error_code": e.error_code,
                "details": e.details
            }
        )
    
    except APIError as e:
        return JSONResponse(
            status_code=503,
            content={
                "message": e.message,
                "error_code": e.error_code,
                "details": e.details
            }
        )
    
    except TravelPlanError as e:
        return JSONResponse(
            status_code=400,
            content={
                "message": e.message,
                "error_code": e.error_code,
                "details": e.details
            }
        )
    
    except Exception as e:
        logger.error(f"予期せぬエラー: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={
                "message": "予期せぬエラーが発生しました",
                "error_code": "INTERNAL_SERVER_ERROR",
                "details": {"error": str(e)}
            }
        )

@app.get("/")
async def root():
    return {"message": "Travel Agent API is running"} 