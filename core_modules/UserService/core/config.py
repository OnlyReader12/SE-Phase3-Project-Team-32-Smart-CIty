"""
Configuration — reads from .env file.
All settings are accessed via the `settings` singleton.
"""
import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-secret-change-in-production")
    ALGORITHM: str = os.getenv("ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 15))
    REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", 7))

    INTERNAL_API_KEY: str = os.getenv("INTERNAL_API_KEY", "internal-secret-key")

    MIDDLEWARE_URL: str = os.getenv("MIDDLEWARE_URL", "http://127.0.0.1:8001")
    INGESTION_URL: str = os.getenv("INGESTION_URL", "http://127.0.0.1:8000")

    # Twilio — SMS alerts (disabled if blank)
    TWILIO_ACCOUNT_SID: str = os.getenv("TWILIO_ACCOUNT_SID", "")
    TWILIO_AUTH_TOKEN: str = os.getenv("TWILIO_AUTH_TOKEN", "")
    TWILIO_FROM_NUMBER: str = os.getenv("TWILIO_FROM_NUMBER", "")

    # SendGrid — Email alerts (disabled if blank)
    SENDGRID_API_KEY: str = os.getenv("SENDGRID_API_KEY", "")
    SENDGRID_FROM_EMAIL: str = os.getenv("SENDGRID_FROM_EMAIL", "alerts@smartcity.local")

    @property
    def twilio_enabled(self) -> bool:
        return bool(self.TWILIO_ACCOUNT_SID and self.TWILIO_AUTH_TOKEN)

    @property
    def sendgrid_enabled(self) -> bool:
        return bool(self.SENDGRID_API_KEY)


settings = Settings()
