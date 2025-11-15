from datetime import datetime, timedelta
import logging
from typing import List

from fastapi import APIRouter

from app.models import Alert, AlertLevel

router = APIRouter(prefix="/alerts", tags=["alerts"])
logger = logging.getLogger(__name__)


@router.get("/", response_model=List[Alert])
async def list_alerts() -> List[Alert]:
    now = datetime.utcnow()
    logger.info("Listing alert feed since_minutes=%s", 5)
    return [
        Alert(
            id="alert-1",
            level=AlertLevel.warning,
            message="High risk of L1 max breach in 2 hours",
            detected_at=now - timedelta(minutes=5),
        )
    ]
