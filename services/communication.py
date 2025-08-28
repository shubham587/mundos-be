from __future__ import annotations

import os
from typing import List, Dict, Any, Optional, Tuple
from email.message import EmailMessage
from email.utils import make_msgid
import smtplib
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

class EmailService:
    """SMTP email sender (supports Gmail / generic SMTP)."""
    def __init__(self) -> None:
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
    ) -> Tuple[bool, str | None]:
        try:
            if not self.smtp_user or not self.smtp_pass:
                print("email_send skipped (missing SMTP credentials)")
                return True, None
            msg = EmailMessage()
            msg["From"] = f"{self.from_name} <{self.from_email}>" if self.from_email else self.from_name
            msg["To"] = to_email
            msg["Subject"] = subject
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
                s.ehlo(); s.starttls(); s.ehlo(); s.login(self.smtp_user, self.smtp_pass); s.send_message(msg)
            print("email_send ok")
            return True, message_id
        except Exception as exc:  # pragma: no cover
            return False, str(exc)


class LLMService:
    """Wrapper around OpenAI chat completions for summaries & outreach copy."""
    def __init__(self) -> None:
        api_key = os.getenv("OPENAI_API_KEY")
        self.client = OpenAI(api_key=api_key)
        self.model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    def summarize_formatted(self, chat_items: List[Dict[str, Any]]) -> str:
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
            f"{format_spec}\n\nConversation History:\n{history}"
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
        context_parts: List[str] = []
        if ai_summary:
            context_parts.append("Previous engagement summary (with dated history):\n" + ai_summary)
        if service_name:
            context_parts.append(f"Service: {service_name}")
        context = "\n\n".join(context_parts)
        system = (
            "You are a helpful, concise healthcare assistant. Write short, friendly outreach emails "
            "with a clear CTA to reply. Avoid being pushy; respect previous context. "
            "Always sign off with 'Best regards,\nMedCampaign' only. Do not include any contact information."
        )
        user = (
            f"Patient name: {patient_name}\n"
            f"Campaign type: {campaign_type}\n"
            f"Attempts made so far: {attempts_made}\n"
            f"{context}\n\nTask: Draft an email to re-engage this patient. Keep under 130 words."
        )
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.4,
            max_tokens=240,
        )
        return resp.choices[0].message.content.strip()
