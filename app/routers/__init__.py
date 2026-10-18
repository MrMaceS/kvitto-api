from app.routers.payments import router as payments_router
from app.routers.tariffs import router as tariffs_router
from app.routers.webhooks import router as webhooks_router

__all__ = ["payments_router", "tariffs_router", "webhooks_router"]
