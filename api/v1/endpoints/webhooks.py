from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, BackgroundTasks

from services.email_processor import process_gmail_webhook


router = APIRouter(tags=["webhooks"])


@router.post("/webhooks/gmail")
async def gmail_webhook(payload: Dict[str, Any], background_tasks: BackgroundTasks) -> dict[str, str]:
    # Immediately return 200 and run processing in background
    background_tasks.add_task(process_gmail_webhook, payload)
    return {"status": "accepted"}


