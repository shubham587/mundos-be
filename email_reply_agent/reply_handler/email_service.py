from __future__ import annotations

from typing import Optional, Dict, Any


def send_email(to_address: str, subject: str, body: str, from_address: Optional[str] = None) -> Dict[str, Any]:
    # Stub implementation: integrate with your provider (e.g., SES, SendGrid) later
    # For now, return a simulated result
    result = {
        "status": "sent",
        "to": to_address,
        "from": from_address or "noreply@clinic.example.com",
        "subject": subject,
        "body_preview": (body[:200] + "...") if len(body) > 200 else body,
    }
    return result
