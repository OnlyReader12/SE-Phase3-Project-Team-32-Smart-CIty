"""
Twilio SMS service.
Disabled gracefully if TWILIO_ACCOUNT_SID is not configured.
"""
from core.config import settings


def send_sms(to_number: str, message: str):
    if not settings.twilio_enabled:
        print(f"[Twilio] SMS disabled. Would send to {to_number}: {message[:60]}")
        return
    try:
        from twilio.rest import Client
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        client.messages.create(
            body=f"[SmartCity Alert] {message}",
            from_=settings.TWILIO_FROM_NUMBER,
            to=to_number,
        )
        print(f"[Twilio] SMS sent to {to_number}")
    except Exception as e:
        print(f"[Twilio] SMS failed: {e}")
