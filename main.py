from __future__ import annotations

import logging
from logging.config import dictConfig
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os

from api.v1.router import api_router
import warnings

from core.config import settings
from services.gmail.client import start_watch, build_gmail_service
from email_reply_agent.reply_handler.repository import set_last_history_id, get_last_history_id

try:
    from urllib3.exceptions import NotOpenSSLWarning
    warnings.filterwarnings("ignore", category=NotOpenSSLWarning)
except Exception:
    pass


def configure_logging() -> None:
    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "json": {
                    "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
                    "fmt": "%(asctime)s %(levelname)s %(name)s %(message)s",
                }
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "json",
                    "level": "INFO",
                }
            },
            "root": {"handlers": ["console"], "level": "INFO"},
            "loggers": {
                "backend": {"handlers": ["console"], "level": "INFO", "propagate": True},
                "email_reply_agent": {"handlers": ["console"], "level": "INFO", "propagate": True},
                "services.gmail": {"handlers": ["console"], "level": "INFO", "propagate": True},
            },
        }
    )


configure_logging()
logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(title="Mundos AI Backend", version="0.1.0")

    origins_env = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").strip()
    allow_all_origins = origins_env in {"*", '"*"'}
    if allow_all_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=False,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    else:
        allowed_origins = [o.strip() for o in origins_env.split(",") if o.strip()]
        app.add_middleware(
            CORSMiddleware,
            allow_origins=allowed_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    app.include_router(api_router, prefix="/api/v1")

    @app.on_event("startup")
    async def _auto_watch_start():
        import asyncio, time

        async def start_or_refresh_watch():
            if not settings.gmail_topic_name:
                return None
            try:
                label_ids = [lbl.strip() for lbl in settings.gmail_label_ids_default.split(",") if lbl.strip()]
                resp = start_watch(
                    topic_name=settings.gmail_topic_name,
                    label_ids=label_ids or ["INBOX"],
                    label_filter_action=settings.gmail_label_filter_action_default or "include",
                    user_id="me",
                )
                baseline_history = resp.get("historyId")
                try:
                    svc = build_gmail_service()
                    profile = svc.users().getProfile(userId="me").execute()
                    email_addr = profile.get("emailAddress")
                except Exception:
                    email_addr = settings.gmail_user_email
                if baseline_history and email_addr and not get_last_history_id(email_addr):
                    set_last_history_id(email_addr, str(baseline_history))
                    logger.info("gmail.watch_baseline_saved", extra={"email": email_addr, "historyId": str(baseline_history)})
                exp = resp.get("expiration")
                return float(exp) / 1000.0 if exp else None
            except Exception:
                return None

        async def watch_maintainer():
            while True:
                exp_sec = await start_or_refresh_watch()
                now = __import__("time").time()
                if exp_sec:
                    delay = max(300.0, (exp_sec - now) - 600.0)
                else:
                    delay = 12 * 60 * 60
                try:
                    await __import__("asyncio").sleep(delay)
                except __import__("asyncio").CancelledError:
                    break

        app.state._watch_task = __import__("asyncio").create_task(watch_maintainer())

    @app.on_event("shutdown")
    async def _auto_watch_stop():
        task = getattr(app.state, "_watch_task", None)
        if task:
            task.cancel()

    @app.get("/")
    async def root_health() -> dict[str, str]:
        return {"status": "ok"}

    logger.info("Application initialized")
    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn
    app = create_app()
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)


