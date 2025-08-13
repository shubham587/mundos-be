from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Tuple

from dotenv import load_dotenv
from pymongo import MongoClient, InsertOne


# Strict campaign doc builder aligned with scripts/seed_full_flow_test.py
def full_campaign(
    patient_id: Any,
    *,
    campaign_type: str,
    status: str,
    service_name: str,
    attempts_made: int,
    max_attempts: int,
    next_at: datetime,
    now: datetime,
    engagement_summary: str | None = None,
) -> Dict[str, Any]:
    return {
        "patient_id": patient_id,
        "campaign_type": campaign_type,
        "service_name": service_name,
        "status": status,
        "channel": {"type": "email", "thread_id": None},
        "engagement_summary": engagement_summary,
        "follow_up_details": {
            "attempts_made": attempts_made,
            "max_attempts": max_attempts,
            "next_attempt_at": next_at,
        },
        "booking_funnel": {
            "status": None,
            "link_url": None,
            "submitted_at": None,
        },
        "created_at": now,
        "updated_at": now,
    }


def connect_db():
    load_dotenv()
    client = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017"))
    return client[os.getenv("MONGO_DB_NAME", "AI-lead-recovery")]


def daterange_2025_to_aug1() -> List[datetime]:
    start = datetime(2025, 1, 1, 10, 0, 0)
    end_exclusive = datetime(2025, 8, 1, 0, 0, 0)
    cur = start
    days: List[datetime] = []
    while cur < end_exclusive:
        days.append(cur)
        cur = cur + timedelta(days=1)
    return days


SERVICES = [
    "Dental Implants",
    "Root Canal",
    "Teeth Whitening",
    "Braces Consultation",
    "Routine Cleaning",
    "Routine Exam",
    "Fluoride Treatment",
    "Deep Cleaning",
]


def pick_status_for_type(campaign_type: str, day_index: int, idx: int) -> Tuple[str, int]:
    # Deterministic distribution across the 4 statuses the user specified
    statuses = [
        "RECOVERED",
        "RECOVERY_FAILED",
        "RECOVERY_DECLINED",
        "HANDOFF_REQUIRED",
    ]
    status = statuses[(day_index + idx) % len(statuses)]
    # Attempts heuristic by status
    if status == "RECOVERED":
        attempts = 1 + ((day_index + idx) % 2)  # 1-2
    elif status == "RECOVERY_FAILED":
        attempts = 3
    elif status == "RECOVERY_DECLINED":
        attempts = 1
    else:  # HANDOFF_REQUIRED
        attempts = 2
    return status, attempts


def main() -> None:
    db = connect_db()

    patients_per_day = int(os.getenv("SEED_PATIENTS_PER_DAY", "40"))
    # Use EXISTING patients per user requirement
    patient_type = "EXISTING"
    # Appointments volume aligned with average patients per day
    appt_rate = float(os.getenv("SEED_APPT_RATE", "0.25"))  # 25% of daily patients by default
    if appt_rate < 0.0:
        appt_rate = 0.0
    if appt_rate > 1.0:
        appt_rate = 1.0

    days = daterange_2025_to_aug1()
    total_days = len(days)

    patient_ops: List[InsertOne] = []
    campaign_ops: List[InsertOne] = []
    appointment_ops: List[InsertOne] = []

    email_domain = os.getenv("SEED_EMAIL_DOMAIN", "clinic-seed.local")

    inserted_patients = 0
    inserted_campaigns = 0

    for d_idx, day in enumerate(days):
        # Patients batch for this day
        daily_patients: List[Dict[str, Any]] = []
        for i in range(patients_per_day):
            email = f"p{d_idx:03d}-{i:03d}@{email_domain}"
            pdoc = {
                "name": f"Seed Patient {d_idx:03d}-{i:03d}",
                "email": email,
                "phone": f"+1-202-555-{d_idx%1000:04d}{i%10}",
                "patient_type": patient_type,
                "preferred_channel": ["email", "sms"],
                "treatment_history": [],
                "created_at": day,
                "updated_at": day,
            }
            daily_patients.append(pdoc)

        # Insert patients for this day
        day_patient_ops = [InsertOne(p) for p in daily_patients]
        if day_patient_ops:
            res = db.patients.bulk_write(day_patient_ops, ordered=False)
            inserted_patients += res.inserted_count if hasattr(res, "inserted_count") else len(day_patient_ops)

        # Fetch the newly inserted patients' _ids by the day's emails
        emails = [p["email"] for p in daily_patients]
        cur = db.patients.find({"email": {"$in": emails}})
        patients = list(cur)
        # Map by email for deterministic ordering
        email_to_id = {p["email"]: p["_id"] for p in patients}

        # Prepare deterministic half-hour slots 09:00–20:30 for appointments
        slots: List[datetime] = []
        start_slot = day.replace(hour=9, minute=0, second=0, microsecond=0)
        for si in range(23):  # 09:00 to 20:30 inclusive → 23 half-hours
            slots.append(start_slot + timedelta(minutes=30 * si))

        # Campaigns for each patient (one per patient) and optional appointments
        appt_threshold = int(appt_rate * 100)
        appt_idx_day = 0
        for i, p in enumerate(daily_patients):
            patient_id = email_to_id[p["email"]]
            # Half Recovery, half Recall
            campaign_type = "RECOVERY" if (i % 2 == 0) else "RECALL"
            status, attempts = pick_status_for_type(campaign_type, d_idx, i)
            next_at = day  # always before Aug 1, 2025 by construction
            service = SERVICES[(d_idx + i) % len(SERVICES)]
            cdoc = full_campaign(
                patient_id,
                campaign_type=campaign_type,
                status=status,
                service_name=service,
                attempts_made=attempts,
                max_attempts=3,
                next_at=next_at,
                now=day,
                engagement_summary=None,
            )
            # Insert campaign now to get campaign_id for appointment linkage
            cres = db.campaigns.insert_one(cdoc)

            # Decide if this patient gets an appointment today (deterministic by modulo over 100)
            if ((d_idx + i) % 100) < appt_threshold:
                slot_dt = slots[appt_idx_day % len(slots)]
                appt_idx_day += 1
                # Status distribution: mostly completed, some booked, few cancelled
                if appt_idx_day % 20 == 0:
                    appt_status = "cancelled"
                elif appt_idx_day % 5 == 0:
                    appt_status = "booked"
                else:
                    appt_status = "completed"
                duration = 45 if ((d_idx + i) % 3 == 0) else 30
                doctor = ["Dr. Smith", "Dr. Johnson", "Dr. Lee"][((d_idx + i) % 3)]
                created_from = "AI_AGENT_FORM" if ((d_idx + i) % 2 == 0) else "MANUAL_ADMIN"
                notes = "Seeded bulk appointment"
                appointment_ops.append(
                    InsertOne(
                        {
                            "patient_id": patient_id,
                            "campaign_id": cres.inserted_id,
                            "appointment_date": slot_dt,
                            "duration_minutes": duration,
                            "status": appt_status,
                            "service_name": service,
                            "notes": notes,
                            "consulting_doctor": doctor,
                            "created_from": created_from,
                            "created_at": day,
                            "updated_at": day,
                        }
                    )
                )

        # Flush in chunks to avoid huge memory usage
        if len(campaign_ops) >= 2000:
            cres = db.campaigns.bulk_write(campaign_ops, ordered=False)
            inserted_campaigns += cres.inserted_count if hasattr(cres, "inserted_count") else len(campaign_ops)
            campaign_ops.clear()
        if len(appointment_ops) >= 2000:
            db.appointments.bulk_write(appointment_ops, ordered=False)
            appointment_ops.clear()

    # Final flush
    if campaign_ops:
        cres = db.campaigns.bulk_write(campaign_ops, ordered=False)
        inserted_campaigns += cres.inserted_count if hasattr(cres, "inserted_count") else len(campaign_ops)
    if appointment_ops:
        db.appointments.bulk_write(appointment_ops, ordered=False)

    total_expected_patients = total_days * patients_per_day
    total_expected_campaigns = total_expected_patients

    print({
        "days": total_days,
        "patients_per_day": patients_per_day,
        "patients_inserted": inserted_patients,
        "campaigns_inserted": inserted_campaigns,
        "expected_patients": total_expected_patients,
        "expected_campaigns": total_expected_campaigns,
        "appt_rate": appt_rate,
    })


if __name__ == "__main__":
    main()


