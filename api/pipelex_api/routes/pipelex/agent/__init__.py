from fastapi import APIRouter

from .concept import router as concept_router
from .models import router as models_router
from .pipe_spec import router as pipe_spec_router

router = APIRouter()

router.include_router(models_router)
router.include_router(concept_router)
router.include_router(pipe_spec_router)
