from aiogram import Router

from src.routers.user.account_refresh import router as account_refresh_router
from src.routers.user.catalog import router as catalog_router
from src.routers.user.favorites import router as favorites_router
from src.routers.user.reviews import router as reviews_router

router = Router(name="user")
router.include_router(account_refresh_router)
router.include_router(catalog_router)
router.include_router(favorites_router)
router.include_router(reviews_router)
