from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel


class LivenessResponse(BaseModel):
    status: Literal["ok"] = "ok"


router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live", response_model=LivenessResponse)
def get_liveness() -> LivenessResponse:
    return LivenessResponse()
