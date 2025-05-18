from fastapi import FastAPI, HTTPException
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

# ロギングの設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

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

class TravelRequest(BaseModel):
    members: List[TravelMember]
    departure_location: str = Field(..., min_length=1)
    travel_month: int = Field(..., ge=1, le=12)
    nights: int = Field(..., ge=0, le=1)  # 0（日帰り）または1泊のみ許可
    budget: int = Field(..., gt=0)

    @validator('members')
    def validate_members(cls, v):
        if not v:
            raise ValueError('少なくとも1人のメンバーを指定してください')
        return v

class TravelResponse(BaseModel):
    travel_plan: str

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    errors = {}
    for error in exc.errors():
        field = error["loc"][-1]
        errors[field] = error["msg"]
    
    return JSONResponse(
        status_code=422,
        content=ErrorResponse(
            message="入力データが不正です",
            error_code="VALIDATION_ERROR",
            details={"validation_errors": errors}
        ).model_dump()
    )

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            message=str(exc.detail),
            error_code="HTTP_ERROR",
            details={"status_code": exc.status_code}
        ).model_dump()
    )

@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            message="予期せぬエラーが発生しました",
            error_code="INTERNAL_SERVER_ERROR",
            details={"error": str(exc)}
        ).model_dump()
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
            request.travel_month,
            request.nights,
            request.budget
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