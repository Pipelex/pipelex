from fastapi import APIRouter

from .agent import router as agent_router
from .codegen import router as codegen_router
from .pipe_io import router as pipe_io_router
from .pipeline import router as pipeline_router
from .resolve import router as resolve_router
from .tools import router as tools_router
from .validate import router as validate_router

router = APIRouter()

router.include_router(pipeline_router)
router.include_router(validate_router)
router.include_router(resolve_router)
router.include_router(pipe_io_router)
router.include_router(codegen_router)
router.include_router(tools_router)
router.include_router(agent_router)
