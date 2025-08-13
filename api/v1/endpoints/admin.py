from __future__ import annotations

from datetime import datetime, timezone, timedelta
from math import ceil
from typing import Any, Dict, List

from bson import ObjectId
import logging
from fastapi import APIRouter, Depends, HTTPException, Query

from db.database import get_database
from repositories.base import BaseRepository
from models.campaign import (
    CampaignType,
    CampaignStatus,
    Campaign,
    Channel,
    FollowUpDetails,
    BookingFunnel,
)
from models.patient import PatientType, ChannelType, Patient
from models.patient import TreatmentHistoryItem
from models.appointment import AppointmentStatus, CreatedFrom, Appointment
from models.interaction import Interaction, Direction
from schemas.admin import (
    RecoveryCampaignCreate,
    CampaignRespondRequest,
    AdminAppointmentCreate,
    CompleteAppointmentRequest,
    AppointmentReminderCampaignCreate,
)
from services.security import get_current_user


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(get_current_user)])


@router.get("/dashboard-stats")
async def dashboard_stats() -> Dict[str, Any]:
    db = await get_database()
    repo = BaseRepository(db)

    # KPIs
    now = datetime.now(timezone.utc)
    start_month = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    next_month = datetime(now.year + (now.month // 12), ((now.month % 12) + 1), 1, tzinfo=timezone.utc)

    # Helpers to normalize datetimes possibly stored as strings or naive
    def _as_utc(dt_like: Any) -> datetime | None:
        if isinstance(dt_like, datetime):
            if dt_like.tzinfo is None:
                return dt_like.replace(tzinfo=timezone.utc)
            return dt_like.astimezone(timezone.utc)
        if isinstance(dt_like, str):
            try:
                parsed = datetime.fromisoformat(dt_like.replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                else:
                    parsed = parsed.astimezone(timezone.utc)
                return parsed
            except Exception:
                return None
        return None

    # Appointments booked this month
    booked_month = 0
    for appt in await repo.find_many("appointments", {}):
        ts = _as_utc(appt.get("appointment_date"))
        if ts and start_month <= ts < next_month and appt.get("status") == "booked":
            booked_month += 1

    # Active campaign counts (current snapshot)
    handoffs = await repo.count_many("campaigns", {"status": CampaignStatus.HANDOFF_REQUIRED.value})
    active_recovery = await repo.count_many(
        "campaigns",
        {
            "campaign_type": CampaignType.RECOVERY.value,
            "status": {"$in": [CampaignStatus.ATTEMPTING_RECOVERY.value, CampaignStatus.RE_ENGAGED.value]},
        },
    )
    active_recall = await repo.count_many(
        "campaigns",
        {
            "campaign_type": CampaignType.RECALL.value,
            "status": {"$in": [CampaignStatus.ATTEMPTING_RECOVERY.value, CampaignStatus.RE_ENGAGED.value]},
        },
    )

    # Monthly campaign stats (filter in Python to be robust against mixed datetime storage)
    campaigns = await repo.find_many("campaigns", {})
    monthly: list[Dict[str, Any]] = []
    for c in campaigns:
        upd = _as_utc(c.get("updated_at")) or _as_utc(c.get("created_at"))
        if upd and start_month <= upd < next_month:
            monthly.append(c)

    recoveries_month = sum(1 for c in monthly if c.get("status") == CampaignStatus.RECOVERED.value)
    engaged_month = sum(1 for c in monthly if c.get("status") == CampaignStatus.RE_ENGAGED.value)

    # Rates scoped to this month
    recov_month_den = sum(1 for c in monthly if c.get("campaign_type") == CampaignType.RECOVERY.value)
    recov_month_num = sum(
        1
        for c in monthly
        if c.get("campaign_type") == CampaignType.RECOVERY.value and c.get("status") == CampaignStatus.RECOVERED.value
    )
    recovery_rate = (recov_month_num / recov_month_den * 100.0) if recov_month_den else 0.0

    recall_month_den = sum(1 for c in monthly if c.get("campaign_type") == CampaignType.RECALL.value)
    recall_month_num = sum(
        1
        for c in monthly
        if c.get("campaign_type") == CampaignType.RECALL.value and c.get("status") == CampaignStatus.RECOVERED.value
    )
    recall_rate = (recall_month_num / recall_month_den * 100.0) if recall_month_den else 0.0

    # Lifetime rates (across all history)
    total_recovery = sum(1 for c in campaigns if c.get("campaign_type") == CampaignType.RECOVERY.value)
    total_recovery_recovered = sum(
        1 for c in campaigns if c.get("campaign_type") == CampaignType.RECOVERY.value and c.get("status") == CampaignStatus.RECOVERED.value
    )
    lifetime_recovery_rate = (total_recovery_recovered / total_recovery * 100.0) if total_recovery else 0.0

    total_recall = sum(1 for c in campaigns if c.get("campaign_type") == CampaignType.RECALL.value)
    total_recall_recovered = sum(
        1 for c in campaigns if c.get("campaign_type") == CampaignType.RECALL.value and c.get("status") == CampaignStatus.RECOVERED.value
    )
    lifetime_recall_rate = (total_recall_recovered / total_recall * 100.0) if total_recall else 0.0

    # Time-series (last 12 months ending with current month)
    def _month_key(dt: datetime) -> str:
        return f"{dt.year:04d}-{dt.month:02d}"

    def _add_months(dt: datetime, n: int) -> datetime:
        y = dt.year + (dt.month - 1 + n) // 12
        m = (dt.month - 1 + n) % 12 + 1
        return datetime(y, m, 1, tzinfo=timezone.utc)

    months: list[str] = []
    start_window = _add_months(start_month, -11)
    cursor = start_window
    for _ in range(12):
        months.append(_month_key(cursor))
        cursor = _add_months(cursor, 1)

    perf_series: list[Dict[str, Any]] = []
    for mk in months:
        yr, mo = mk.split("-")
        s = datetime(int(yr), int(mo), 1, tzinfo=timezone.utc)
        e = datetime(s.year + (s.month // 12), (s.month % 12) + 1, 1, tzinfo=timezone.utc)
        slice_items = [c for c in campaigns if (dt := (_as_utc(c.get("updated_at")) or _as_utc(c.get("created_at")))) and s <= dt < e]
        rec_den = sum(1 for c in slice_items if c.get("campaign_type") == CampaignType.RECOVERY.value)
        rec_num = sum(1 for c in slice_items if c.get("campaign_type") == CampaignType.RECOVERY.value and c.get("status") == CampaignStatus.RECOVERED.value)
        rcl_den = sum(1 for c in slice_items if c.get("campaign_type") == CampaignType.RECALL.value)
        rcl_num = sum(1 for c in slice_items if c.get("campaign_type") == CampaignType.RECALL.value and c.get("status") == CampaignStatus.RECOVERED.value)
        perf_series.append(
            {
                "month": mk,
                "recovery_rate_percent": round((rec_num / rec_den * 100.0) if rec_den else 0.0, 1),
                "recall_rate_percent": round((rcl_num / rcl_den * 100.0) if rcl_den else 0.0, 1),
                "recoveries": rec_num,
                "recall_recoveries": rcl_num,
            }
        )

    # Campaign breakdown (lifetime and month) for pie charts
    ACTIVE_STATUSES = {CampaignStatus.ATTEMPTING_RECOVERY.value, CampaignStatus.RE_ENGAGED.value}
    FAILED = CampaignStatus.RECOVERY_FAILED.value
    DECLINED = CampaignStatus.RECOVERY_DECLINED.value

    def _breakdown(items: list[Dict[str, Any]]) -> Dict[str, int]:
        return {
            "handoffs": sum(1 for c in items if c.get("status") == CampaignStatus.HANDOFF_REQUIRED.value),
            "active_recovery": sum(1 for c in items if c.get("campaign_type") == CampaignType.RECOVERY.value and c.get("status") in ACTIVE_STATUSES),
            "active_recall": sum(1 for c in items if c.get("campaign_type") == CampaignType.RECALL.value and c.get("status") in ACTIVE_STATUSES),
            "recovered": sum(1 for c in items if c.get("status") == CampaignStatus.RECOVERED.value),
            "failed": sum(1 for c in items if c.get("status") == FAILED),
            "declined": sum(1 for c in items if c.get("status") == DECLINED),
        }

    breakdown_lifetime = _breakdown(campaigns)
    breakdown_month = _breakdown(monthly)

    # Appointments trend per month (booked/completed/cancelled)
    appts = await repo.find_many("appointments", {})
    appt_series: list[Dict[str, Any]] = []
    for mk in months:
        yr, mo = mk.split("-")
        s = datetime(int(yr), int(mo), 1, tzinfo=timezone.utc)
        e = datetime(s.year + (s.month // 12), (s.month % 12) + 1, 1, tzinfo=timezone.utc)
        slice_appts = [a for a in appts if (dt := _as_utc(a.get("appointment_date"))) and s <= dt < e]
        appt_series.append(
            {
                "month": mk,
                "booked": sum(1 for a in slice_appts if a.get("status") == "booked"),
                "completed": sum(1 for a in slice_appts if a.get("status") == "completed"),
                "cancelled": sum(1 for a in slice_appts if a.get("status") == "cancelled"),
            }
        )

    # Trailing 90 days rates to reflect near-term performance even when current month has no data yet
    window_90_start = now - timedelta(days=90)
    recent = [
        c
        for c in campaigns
        if (dt := (_as_utc(c.get("updated_at")) or _as_utc(c.get("created_at")))) and window_90_start <= dt <= now
    ]
    rec_recent_den = sum(1 for c in recent if c.get("campaign_type") == CampaignType.RECOVERY.value)
    rec_recent_num = sum(1 for c in recent if c.get("campaign_type") == CampaignType.RECOVERY.value and c.get("status") == CampaignStatus.RECOVERED.value)
    rcl_recent_den = sum(1 for c in recent if c.get("campaign_type") == CampaignType.RECALL.value)
    rcl_recent_num = sum(1 for c in recent if c.get("campaign_type") == CampaignType.RECALL.value and c.get("status") == CampaignStatus.RECOVERED.value)
    recovery_rate_90d = (rec_recent_num / rec_recent_den * 100.0) if rec_recent_den else 0.0
    recall_rate_90d = (rcl_recent_num / rcl_recent_den * 100.0) if rcl_recent_den else 0.0

    return {
        "kpis": {
            "appointments_booked_month": booked_month,
            "handoffs_requiring_action": handoffs,
            "active_recovery_campaigns": active_recovery,
            "active_recall_campaigns": active_recall,
            "engaged_leads_month": engaged_month,
            "recoveries_month": recoveries_month,
            "lifetime_recoveries": total_recovery_recovered,
            "lifetime_recall_recoveries": total_recall_recovered,
        },
        "conversion_rates": {
            "recovery_rate_percent": round(recovery_rate, 1),
            "recall_rate_percent": round(recall_rate, 1),
            "lifetime_recovery_rate_percent": round(lifetime_recovery_rate, 1),
            "lifetime_recall_rate_percent": round(lifetime_recall_rate, 1),
            "recovery_rate_90d_percent": round(recovery_rate_90d, 1),
            "recall_rate_90d_percent": round(recall_rate_90d, 1),
        },
        "time_window": {
            "start": start_month.isoformat(),
            "end": next_month.isoformat(),
        },
        "charts": {
            "performance_timeseries": perf_series,
            "campaign_breakdown": {
                "lifetime": breakdown_lifetime,
                "this_month": breakdown_month,
            },
            "appointments_trend": appt_series,
        },
    }


@router.get("/campaigns")
async def list_campaigns(
    status: str | None = None,
    page: int = Query(1, ge=1),
    limit: int = Query(25, ge=1, le=100),
) -> Dict[str, Any]:
    db = await get_database()
    repo = BaseRepository(db)
    query: Dict[str, Any] = {}
    if status:
        query["status"] = status

    items: List[Dict[str, Any]] = await repo.find_many("campaigns", query, sort=[("updated_at", -1)])
    total = len(items)
    start = (page - 1) * limit
    end = start + limit
    page_items = items[start:end]

    results: List[Dict[str, Any]] = []
    for c in page_items:
        pid = c.get("patient_id")
        # Support both ObjectId and string stored ids (from seed or legacy)
        query_id = pid
        if isinstance(pid, str):
            try:
                query_id = ObjectId(pid)
            except Exception:
                query_id = pid
        patient = await repo.find_one("patients", {"_id": query_id})
        results.append(
            {
                "campaign_id": str(c.get("_id")),
                "patient_name": (patient or {}).get("name", "Unknown"),
                "campaign_type": c.get("campaign_type"),
                "status": c.get("status"),
                "last_updated": c.get("updated_at"),
            }
        )

    return {
        "pagination": {
            "total_items": total,
            "total_pages": ceil(total / limit) if limit else 1,
            "current_page": page,
        },
        "campaigns": results,
    }


@router.get("/campaigns/{campaign_id}")
async def campaign_details(campaign_id: str) -> Dict[str, Any]:
    db = await get_database()
    repo = BaseRepository(db)
    try:
        oid = ObjectId(campaign_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid campaign_id")

    campaign = await repo.find_one("campaigns", {"_id": oid})
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    messages = await repo.find_many("interactions", {"campaign_id": oid})
    history = [
        {
            "direction": m.get("direction"),
            "content": m.get("content"),
            "timestamp": m.get("timestamp"),
        }
        for m in messages
    ]

    # Fetch patient details from patients collection (support str/ObjectId)
    pid = campaign.get("patient_id")
    pid_query = pid
    if isinstance(pid, str):
        try:
            pid_query = ObjectId(pid)
        except Exception:
            pid_query = pid
    patient = await repo.find_one("patients", {"_id": pid_query})

    details = {
        "campaign_id": str(campaign.get("_id")),
        "patient_name": (patient or {}).get("name", "Unknown"),
        "patient_phone": (patient or {}).get("phone", ""),
        "patient_email": (patient or {}).get("email", ""),
        "status": campaign.get("status"),
        "source": (campaign.get("channel") or {}).get("type") if isinstance(campaign.get("channel"), dict) else None,
        "engagement_summary": campaign.get("engagement_summary"),
    }
    return {"campaign_details": details, "conversation_history": history}


@router.get("/appointments")
async def list_appointments(
    start_date: str | None = None,
    end_date: str | None = None,
    provider_id: str | None = None,  # Placeholder: provider not modeled yet
) -> Dict[str, Any]:
    db = await get_database()
    repo = BaseRepository(db)
    def _parse_iso(dt_str: str | None) -> datetime | None:
        if not dt_str:
            return None
        # Normalize trailing Z to +00:00 for fromisoformat compatibility
        normalized = dt_str.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(normalized)
        except Exception:
            logger.exception("appointments.list.invalid_datetime", extra={"value": dt_str})
            return None

    start_dt = _parse_iso(start_date)
    end_dt = _parse_iso(end_date)

    # Try to narrow the DB scan if date filters are provided, supporting both
    # datetime and ISO string storage for appointment_date.
    appt_query: Dict[str, Any] = {}
    if start_dt and end_dt:
        start_iso = start_dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        end_iso = end_dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        appt_query = {
            "$or": [
                {"appointment_date": {"$gte": start_dt, "$lte": end_dt}},
                {"appointment_date": {"$gte": start_iso, "$lte": end_iso}},
            ]
        }

    results: List[Dict[str, Any]] = []
    for appt in await repo.find_many("appointments", appt_query):
        ts = appt.get("appointment_date")
        if isinstance(ts, str):
            try:
                ts = datetime.fromisoformat(ts)
            except Exception:
                ts = None
        # Normalize to UTC-aware for safe comparisons
        if isinstance(ts, datetime) and ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if start_dt and (not ts or ts < start_dt):
            continue
        if end_dt and (not ts or ts > end_dt):
            continue

        patient = await repo.find_one("patients", {"_id": appt.get("patient_id")})
        results.append(
            {
                "appointment_id": str(appt.get("_id", "")),
                "patient_name": (patient or {}).get("name", "Unknown"),
                "appointment_date": appt.get("appointment_date"),
                "service_name": appt.get("service_name"),
                "status": appt.get("status"),
                "patient_email": (patient or {}).get("email", ""),
                "patient_phone": (patient or {}).get("phone", ""),
                "doctor": appt.get("consulting_doctor", "")
            }
        )

    return {"appointments": results}


# Milestone 6: Write operations


@router.post("/campaigns/recovery")
async def create_recovery_campaign(payload: RecoveryCampaignCreate) -> Dict[str, str]:
    db = await get_database()
    repo = BaseRepository(db)
    # Create patient using model to ensure full document shape
    patient_model = Patient(
        name=payload.patient_name,
        email=str(payload.patient_email),
        phone="",
        patient_type=PatientType.COLD_LEAD,
        preferred_channel=[ChannelType.email],
    )
    presult_id = await repo.insert_one("patients", patient_model.model_dump(by_alias=True, exclude_none=False))

    # Create campaign via model
    campaign_model = Campaign(
        patient_id=presult_id,  # type: ignore[arg-type]
        campaign_type=CampaignType.RECOVERY,
        status=CampaignStatus.ATTEMPTING_RECOVERY,
        engagement_summary=payload.initial_inquiry,
    )
    cresult_id = await repo.insert_one("campaigns", campaign_model.model_dump(by_alias=True, exclude_none=False))
    return {"message": "Recovery campaign created successfully.", "campaign_id": str(cresult_id)}


@router.post("/campaigns/{campaign_id}/respond")
async def respond_to_campaign(campaign_id: str, payload: CampaignRespondRequest) -> Dict[str, str]:
    db = await get_database()
    repo = BaseRepository(db)
    try:
        oid = ObjectId(campaign_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid campaign_id")

    # Create outgoing interaction via model
    interaction = Interaction(campaign_id=oid, direction=Direction.outgoing, content=payload.message)
    await repo.insert_one("interactions", interaction.model_dump(by_alias=True, exclude_none=False))

    # Update campaign status
    await repo.update_one("campaigns", {"_id": oid}, {"$set": {"status": payload.new_status}})
    return {"message": "Response sent successfully."}


@router.post("/appointments")
async def create_admin_appointment(payload: AdminAppointmentCreate) -> Dict[str, Any]:
    db = await get_database()
    repo = BaseRepository(db)
    logger.info("appointments.create.request", extra={"email": str(payload.email), "date": str(payload.appointment_date)})
    try:
        patient = await repo.find_one("patients", {"email": str(payload.email)})
        new_patient_created = False
        if not patient:
            # create patient with full model
            preferred = [ChannelType.email]
            if payload.preferred_channel and payload.preferred_channel in {c.value for c in ChannelType}:  # type: ignore[attr-defined]
                try:
                    preferred = [ChannelType(payload.preferred_channel)]
                except Exception:
                    preferred = [ChannelType.email]
            patient_model = Patient(
                name=payload.name,
                email=str(payload.email),
                phone=payload.phone or "",
                patient_type=PatientType.EXISTING,
                preferred_channel=preferred,
            )
            patient_id = await repo.insert_one("patients", patient_model.model_dump(by_alias=True, exclude_none=False))
            new_patient_created = True
        else:
            patient_id = patient["_id"]
            # Upsert phone if missing and payload provides one
            if (not patient.get("phone")) and (payload.phone is not None and payload.phone.strip() != ""):
                await repo.update_one("patients", {"_id": patient_id}, {"$set": {"phone": payload.phone.strip()}})

        # Normalize/validate patient_id for downstream Pydantic models
        patient_oid: ObjectId | None
        try:
            patient_oid = patient_id if isinstance(patient_id, ObjectId) else ObjectId(str(patient_id))
        except Exception:
            patient_oid = None

        # Determine campaign linkage per business rules
        selected_campaign_id = None
        # Find most recent campaign for patient
        patient_match: Dict[str, Any]
        if patient_oid is not None:
            patient_match = {"$or": [{"patient_id": patient_oid}, {"patient_id": patient_id}]}
        else:
            patient_match = {"patient_id": patient_id}
        existing_list = await repo.find_many("campaigns", patient_match, sort=[("updated_at", -1)], limit=1)
        existing_campaign = existing_list[0] if existing_list else None

        one_day_before = None
        try:
            appt_dt = payload.appointment_date
            if isinstance(appt_dt, str):
                appt_dt = datetime.fromisoformat(appt_dt.replace("Z", "+00:00"))
            one_day_before = appt_dt - timedelta(days=1)
        except Exception:
            one_day_before = None

        def build_reminder_campaign() -> dict:
            # Build a full campaign-shaped object using the Campaign model (via schema subclass)
            if patient_oid is not None:
                try:
                    reminder = AppointmentReminderCampaignCreate(
                        patient_id=patient_oid,  # type: ignore[arg-type]
                        campaign_type=CampaignType.APPOINTMENT_REMINDER if hasattr(CampaignType, 'APPOINTMENT_REMINDER') else CampaignType.RECALL,
                        status=None,
                        channel=Channel(type="email", thread_id=None),  # default channel placeholder
                        engagement_summary=None,
                        follow_up_details=FollowUpDetails(
                            attempts_made=0,
                            max_attempts=1,
                            next_attempt_at=one_day_before,
                        ),
                        booking_funnel=BookingFunnel(),
                    )
                    return reminder.model_dump(by_alias=True, exclude_none=False)
                except Exception:
                    pass
            # Fallback to dict if model validation fails or patient_oid not available
            # Include full schema fields (excluding autogenerated ones)
            return {
                "patient_id": patient_id,
                "campaign_type": (CampaignType.APPOINTMENT_REMINDER.value if hasattr(CampaignType, 'APPOINTMENT_REMINDER') else CampaignType.RECALL.value),
                "status": None,
                "channel": {"type": "email", "thread_id": None},
                "engagement_summary": None,
                "follow_up_details": {
                    "attempts_made": 0,
                    "max_attempts": 1,
                    "next_attempt_at": one_day_before,
                },
                "booking_funnel": None,
                "handoff_details": None,
            }

        if new_patient_created or existing_campaign is None:
            # Always create reminder for new patients or when no campaign exists
            selected_campaign_id = await repo.insert_one("campaigns", build_reminder_campaign())
        else:
            status = existing_campaign.get("status")
            if status in (CampaignStatus.RECOVERED.value, None):
                # Create new reminder campaign
                selected_campaign_id = await repo.insert_one("campaigns", build_reminder_campaign())
            else:
                # Mark existing as booking completed and use it
                await repo.update_one(
                    "campaigns",
                    {"_id": existing_campaign["_id"]},
                    {"$set": {"status": CampaignStatus.BOOKING_COMPLETED.value}},
                )
                selected_campaign_id = existing_campaign["_id"]

        # Normalize appointment_date to UTC
        appt_dt_raw = payload.appointment_date
        if isinstance(appt_dt_raw, str):
            try:
                appt_dt = datetime.fromisoformat(appt_dt_raw.replace("Z", "+00:00"))
            except Exception:
                appt_dt = datetime.now(timezone.utc)
        else:
            appt_dt = appt_dt_raw
        if appt_dt.tzinfo is None:
            appt_dt = appt_dt.replace(tzinfo=timezone.utc)
        else:
            appt_dt = appt_dt.astimezone(timezone.utc)

        # Build appointment document (prefer model; fallback to dict if patient_oid unavailable)
        if patient_oid is not None:
            appt_model = Appointment(
                patient_id=patient_oid,  # type: ignore[arg-type]
                campaign_id=selected_campaign_id,  # type: ignore[arg-type]
                appointment_date=appt_dt,
                duration_minutes=payload.duration_minutes,
                status=AppointmentStatus.booked,
                service_name=payload.service_name,
                notes=payload.notes,
                created_from=CreatedFrom.MANUAL_ADMIN,
            )
            appt_dump = appt_model.model_dump(by_alias=True, exclude_none=False)
        else:
            appt_dump = {
                "patient_id": patient_id,
                "campaign_id": selected_campaign_id,
                "appointment_date": appt_dt,
                "duration_minutes": payload.duration_minutes,
                "status": AppointmentStatus.booked.value,
                "service_name": payload.service_name,
                "notes": payload.notes,
                "consulting_doctor": payload.consulting_doctor if payload.consulting_doctor is not None else None,
                "created_from": CreatedFrom.MANUAL_ADMIN.value,
            }
        if payload.consulting_doctor:
            appt_dump["consulting_doctor"] = payload.consulting_doctor
        appt_id = await repo.insert_one("appointments", appt_dump)
        # Build JSON-serializable response
        response: Dict[str, Any] = {
            "appointment_id": str(appt_id),
            "patient_id": str(patient_id),
            "appointment_date": appt_dump["appointment_date"],
            "service_name": appt_dump["service_name"],
            "status": appt_dump["status"],
        }
        logger.info("appointments.create.success", extra={"appointment_id": str(appt_id)})
        return response
    except Exception as e:
        logger.exception("appointments.create.error")
        # Return a client-friendly error instead of a generic 500
        raise HTTPException(status_code=400, detail=f"Failed to create appointment: {type(e).__name__}: {e}")


@router.post("/appointments/{appointment_id}/complete")
async def complete_appointment(appointment_id: str, payload: CompleteAppointmentRequest) -> Dict[str, str]:
    db = await get_database()
    repo = BaseRepository(db)
    # Accept both ObjectId and string ids for tests/fakes
    oid = None
    try:
        oid = ObjectId(appointment_id)
    except Exception:
        oid = None

    appointment = None
    if oid is not None:
        appointment = await repo.find_one("appointments", {"_id": oid})
    if appointment is None:
        appointment = await repo.find_one("appointments", {"_id": appointment_id})
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")

    # Step 1: update appointment status
    if oid is not None:
        await repo.update_one("appointments", {"_id": oid}, {"$set": {"status": AppointmentStatus.completed.value}})
    else:
        await repo.update_one("appointments", {"_id": appointment_id}, {"$set": {"status": AppointmentStatus.completed.value}})

    # Step 2: update campaign if exists
    campaign_id = appointment.get("campaign_id")
    if campaign_id:
        updates: Dict[str, Any] = {"status": CampaignStatus.RECOVERED.value}
        # If follow-up required → convert to Recall and schedule next attempt
        if payload.next_follow_up_date is not None:
            updates.update(
                {
                    "campaign_type": "RECALL",
                    "follow_up_details": {
                        "attempts_made": 0,
                        "max_attempts": 3,
                        "next_attempt_at": payload.next_follow_up_date,
                    },
                }
            )
        await repo.update_one("campaigns", {"_id": campaign_id}, {"$set": updates})

    # Step 3: update patient treatment_history and optional future recall
    patient_id = appointment.get("patient_id")
    if patient_id:
        try:
            history_item = TreatmentHistoryItem(
                appointment_id=appointment.get("_id"),  # type: ignore[arg-type]
                procedure_name=appointment.get("service_name", ""),
                procedure_date=appointment.get("appointment_date"),
                next_recommended_follow_up=payload.next_recommended_follow_up,
                next_follow_up_date=payload.next_follow_up_date,
            )
            await repo.update_one(
                "patients",
                {"_id": patient_id},
                {
                    "$push": {"treatment_history": history_item.model_dump(by_alias=True, exclude_none=False)},
                    "$set": {
                        "next_follow_up_date": payload.next_follow_up_date,
                        "next_recommended_follow_up": payload.next_recommended_follow_up,
                    } if payload.next_follow_up_date is not None or payload.next_recommended_follow_up is not None else {},
                },
            )
        except Exception:
            # Best-effort; do not fail completion if history update fails
            logger.exception("patients.treatment_history.update_failed", extra={"appointment_id": str(appointment_id)})

    return {"message": "Appointment completed."}


@router.delete("/appointments/{appointment_id}")
async def delete_appointment(appointment_id: str) -> Dict[str, str]:
    db = await get_database()
    repo = BaseRepository(db)
    # Accept either ObjectId hex or raw string ids for robustness
    query: Dict[str, Any]
    try:
        query = {"_id": ObjectId(appointment_id)}
    except Exception:
        query = {"_id": appointment_id}

    await repo.delete_one("appointments", query)
    return {"message": "Appointment deleted."}



