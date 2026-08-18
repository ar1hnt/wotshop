from aiogram import Router

from src.routers.admin.faq import router as faq_router
from src.routers.admin.panel import router as panel_router
from src.routers.admin.products import router as products_router
from src.routers.admin.statistics import router as statistics_router
from src.routers.admin.transactions import router as transactions_router
from src.routers.admin.users import router as users_router

router = Router(name="admin")
router.include_router(panel_router)
router.include_router(faq_router)
router.include_router(products_router)
router.include_router(statistics_router)
router.include_router(transactions_router)
router.include_router(users_router)
