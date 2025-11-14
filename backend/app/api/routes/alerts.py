from datetime import datetime, timedelta
from typing import List

from fastapi import APIRouter

from app.models import Alert, AlertLevel

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("/", response_model=List[Alert])
async def list_alerts() -> List[Alert]:
    now = datetime.utcnow()
    return [
        Alert(
            id="alert-1",
            level=AlertLevel.warning,
            message="High risk of L1 max breach in 2 hours",
            detected_at=now - timedelta(minutes=5),
        )
    ]
