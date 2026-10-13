from fastapi import APIRouter

from app.api import auth, misc, orders, plans, tasks, users

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(orders.router)
api_router.include_router(tasks.router)
api_router.include_router(plans.router)
api_router.include_router(misc.notifications_router)
api_router.include_router(misc.audit_router)
api_router.include_router(misc.dashboard_router)
api_router.include_router(misc.meta_router)
api_router.include_router(misc.health_router)

__all__ = ["api_router"]
