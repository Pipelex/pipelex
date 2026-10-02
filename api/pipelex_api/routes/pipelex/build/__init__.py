from fastapi import APIRouter

from .inputs import router as inputs_router
from .output import router as output_router
from .runner import router as runner_router

router = APIRouter()

router.include_router(inputs_router)
router.include_router(output_router)
router.include_router(runner_router)
