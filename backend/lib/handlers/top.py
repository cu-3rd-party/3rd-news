from fastapi import APIRouter

from lib.handlers import health

api_router = APIRouter()
api_router.include_router(health.router)
