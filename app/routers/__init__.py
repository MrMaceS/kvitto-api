from app.routers.tariffs import router as tariffs_router
from app.routers.payments import router as payments_router
from app.routers.webhooks import router as webhooks_router

__all__ = ["tariffs_router", "payments_router", "webhooks_router"]
