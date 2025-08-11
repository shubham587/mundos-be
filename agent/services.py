from __future__ import annotations

import json
import os
from typing import List, Dict, Any, Optional
from datetime import datetime
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
import smtplib
from email.message import EmailMessage
from email.utils import make_msgid
from openai import OpenAI


load_dotenv()


class EmailService:
    def __init__(self) -> None:
        # SMTP configuration (supports Gmail app password)
        self.smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user = os.getenv("SMTP_USERNAME")
        self.smtp_pass = os.getenv("SMTP_PASSWORD")
        self.from_email = os.getenv("SMTP_FROM_EMAIL", self.smtp_user)
        self.from_name = os.getenv("SMTP_FROM_NAME", "Clinic")

    def send(
        self,
        to_email: str,
        subject: str,
        body: str,
        html: str | None = None,
        in_reply_to: str | None = None,
        references: str | None = None,
        reply_to: str | None = None,
    ) -> tuple[bool, str | None]:
        """Send an email via SMTP.

        Returns (ok, message_id_or_error).
        """
        try:
            if not self.smtp_user or not self.smtp_pass:
                print("email_send (DRY-RUN: missing SMTP creds)")
                return True, None

            msg = EmailMessage()
            msg["From"] = f"{self.from_name} <{self.from_email}>" if self.from_email else self.from_name
            msg["To"] = to_email
            msg["Subject"] = subject

            # Optional threading headers
            if in_reply_to:
                msg["In-Reply-To"] = in_reply_to
            if references:
                msg["References"] = references

            message_id = make_msgid()
            msg["Message-ID"] = message_id

            if html:
                msg.set_content(body)
                msg.add_alternative(html, subtype="html")
            else:
                msg.set_content(body)

            if reply_to:
                msg["Reply-To"] = reply_to

            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=30) as s:
                s.ehlo()
                s.starttls()
                s.ehlo()
                s.login(self.smtp_user, self.smtp_pass)
                s.send_message(msg)

            print("email_send")
            return True, message_id
        except Exception as exc:  # pragma: no cover
            return False, str(exc)


class LLMService:
    def __init__(self) -> None:
        api_key = os.getenv("OPENAI_API_KEY")
        self.client = OpenAI(api_key=api_key)
        self.model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    def generate_followup_email(self, patient_name: str, service_name: str) -> str:
        system = "You are a helpful healthcare assistant drafting brief, friendly follow-up emails."
        user = (
            f"Draft a short, friendly follow-up email to {patient_name} about the service '{service_name}'. "
            f"Keep it under 120 words, with a clear next step to reply or book."
        )
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.4,
            max_tokens=220,
        )
        return resp.choices[0].message.content.strip()

    def summarize(self, chat_lines: List[str]) -> str:
        history = "\n".join(chat_lines)
        prompt = (
            "Analyze the following conversation history with a potential patient for a healthcare service. "
            "Your task is to produce a concise JSON summary. The JSON object should include three keys: "
            "sentiment (can be 'Positive', 'Neutral', 'Negative', or 'Interested'), key_questions (a list of specific questions the patient asked), "
            "and summary (a one-paragraph overview of the interaction, focusing on the patient's needs and objections). "
            f"Conversation: {history}"
        )
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "Return only valid JSON."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=300,
        )
        text = resp.choices[0].message.content.strip()
        try:
            json.loads(text)
            return text
        except Exception:
            return json.dumps({"sentiment": "Neutral", "key_questions": [], "summary": text})

    def summarize_formatted(self, chat_items: List[Dict[str, Any]]) -> str:
        # chat_items: [{timestamp_iso, direction, content}]
        history_lines = [f"{i['timestamp_iso']} | {i['direction']}: {i['content']}" for i in chat_items]
        history = "\n".join(history_lines)
        format_spec = (
            "Overall Summary-\n"
            "<one-paragraph overall summary>\n\n"
            "Chatwise Summary-\n\n"
            "<timestamp iso>: <short summary of message 1>\n\n"
            "<timestamp iso>: <short summary of message 2>\n\n"
            "..."
        )
        prompt = (
            "You are an analyst. Read the conversation history below (each line is 'ISO_TIMESTAMP | direction: content').\n"
            "Produce a concise analytical summary in EXACTLY this format (no extra text):\n\n"
            f"{format_spec}\n\n"
            f"Conversation History:\n{history}"
        )
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "Return only the formatted summary text."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=500,
        )
        return resp.choices[0].message.content.strip()

    def generate_campaign_message(
        self,
        *,
        patient_name: str,
        campaign_type: str,
        attempts_made: int,
        service_name: Optional[str] = None,
        ai_summary: Optional[str] = None,
    ) -> str:
        context_lines: List[str] = []
        if ai_summary:
            context_lines.append("Previous engagement summary (with dated history):\n" + ai_summary)
        if service_name:
            context_lines.append(f"Service: {service_name}")
        context = "\n\n".join(context_lines)

        system = (
            "You are a helpful, concise healthcare assistant. Write short, friendly outreach emails "
            "with a clear CTA to reply. Avoid being pushy; respect previous context. "
            "Always sign off with 'Best regards,\\nMedCampaign' only. Do not include any contact information."
        )
        user = (
            f"Patient name: {patient_name}\n"
            f"Campaign type: {campaign_type}\n"
            f"Attempts made so far: {attempts_made}\n"
            f"{context}\n\n"
            "Task: Draft an email to re-engage this patient. Keep under 130 words."
        )
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.4,
            max_tokens=240,
        )
        return resp.choices[0].message.content.strip()

    def generate_appointment_reminder_message(
        self,
        *,
        patient_name: str,
        appointment_dt_local_str: str,
    ) -> str:
        system = (
            "You write polite, clear appointment reminder emails for healthcare clinics. "
            "Use the EXACT date/time string provided below verbatim in the email body. "
            "Do NOT use placeholders like [insert date] or [insert time]. Keep it under 120 words. "
            "Always sign off with 'Best regards,\\nMedCampaign' only. Do not include any contact information."
        )
        user = (
            f"Patient name: {patient_name}\n"
            f"Appointment date/time (string): {appointment_dt_local_str}\n\n"
            "Task: Draft a friendly reminder including that exact date/time string, and invite them to reply if they need to reschedule."
        )
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.1,
            max_tokens=200,
        )
        return resp.choices[0].message.content.strip()


