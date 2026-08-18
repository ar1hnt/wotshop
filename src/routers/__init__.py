from aiogram import Router

from src.routers.admin import router as admin_router
from src.routers.common import router as common_router
from src.routers.user import router as user_router


def setup_routers() -> Router:
    router = Router(name="root")
    router.include_router(common_router)
    router.include_router(user_router)
    router.include_router(admin_router)
    return router
