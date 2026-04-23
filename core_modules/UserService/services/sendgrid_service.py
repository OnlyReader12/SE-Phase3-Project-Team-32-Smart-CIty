"""
SendGrid email service.
Disabled gracefully if SENDGRID_API_KEY is not configured.
"""
from core.config import settings


def _str(val) -> str:
    """Safely convert enum or plain string to string."""
    return val.value if hasattr(val, "value") else str(val or "")


def send_email(to_email: str, to_name: str, alert):
    if not settings.sendgrid_enabled:
        print(f"[SendGrid] Email disabled. Would send to {to_email}: {alert.message[:60]}")
        return
    try:
        from sendgrid import SendGridAPIClient
        from sendgrid.helpers.mail import Mail

        severity = _str(alert.severity)
        domain   = _str(alert.domain)
        zone     = _str(getattr(alert, "zone_id", "N/A"))
        node     = _str(getattr(alert, "node_id", "N/A"))
        field    = _str(getattr(alert, "field", ""))
        value    = _str(getattr(alert, "value", ""))
        thresh   = _str(getattr(alert, "threshold", ""))

        html = f"""
        <h2>⚠️ Smart City Alert — {severity}</h2>
        <p><strong>Zone:</strong> {zone}</p>
        <p><strong>Domain:</strong> {domain}</p>
        <p><strong>Node:</strong> {node}</p>
        <p><strong>Reading:</strong> {field} = {value} (threshold: {thresh})</p>
        <p><strong>Message:</strong> {alert.message}</p>
        """
        msg = Mail(
            from_email=settings.SENDGRID_FROM_EMAIL,
            to_emails=to_email,
            subject=f"[SmartCity {severity}] {zone} — {domain}",
            html_content=html,
        )
        SendGridAPIClient(settings.SENDGRID_API_KEY).send(msg)
        print(f"[SendGrid] Email sent to {to_email}")
    except Exception as e:
        print(f"[SendGrid] Email failed: {e}")
