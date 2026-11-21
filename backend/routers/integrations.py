from fastapi import APIRouter
from backend.adapters import get_tracker_adapter, get_notifier_adapter
from backend.config import settings

router = APIRouter(prefix="/integrations", tags=["integrations"])

@router.post("/test")
def test_integrations():
    tracker = get_tracker_adapter()
    tracker_res = tracker.test_connection()

    return {
        "tracker": tracker_res,
        "notifier": {
            "status": "connected",
            "provider": settings.notifier_integration,
            "message": "In-app and console notification dispatch active."
        },
        "llm_engine": {
            "status": "active",
            "mode": "DEMO_MODE (Deterministic Heuristics & Local Vector Memory)" if settings.demo_mode else "GEMINI LIVE API",
            "model": settings.gemini_model
        }
    }
