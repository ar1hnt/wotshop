from aiogram import Router

from src.routers.common.navigation import router as navigation_router

router = Router(name="common")
router.include_router(navigation_router)
