from fastapi import APIRouter

from .models import router as models_router

router = APIRouter()

router.include_router(models_router)
