import resend
import os
import asyncio
import logging

logger = logging.getLogger(__name__)

# Initialise Resend with the API key from env
resend.api_key = os.environ.get("RESEND_API_KEY", "")

SENDER    = os.environ.get("EMAIL_FROM", "Øditr <onboarding@resend.dev>")
SITE_URL  = os.environ.get("SITE_URL", "http://localhost:3000")


def _build_confirmation_html(position: int, referral_code: str) -> str:
    referral_url = f"{SITE_URL}?ref={referral_code}"
    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#ffffff;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;color:#0A0A0A;">
  <table width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;margin:0 auto;padding:48px 24px;">
    <tr><td>
      <!-- Logo -->
      <p style="font-size:52px;font-weight:500;line-height:1;margin:0 0 4px;">Ø</p>
      <p style="font-size:10px;letter-spacing:0.22em;text-transform:uppercase;color:#666;margin:0 0 48px;">Øditr — Pre-launch</p>

      <!-- Headline -->
      <h1 style="font-size:30px;font-weight:500;letter-spacing:-0.02em;margin:0 0 16px;">You're on the list.</h1>
      <p style="font-size:16px;color:#444;line-height:1.65;margin:0 0 36px;">
        You're <strong style="color:#0A0A0A;">#{position}</strong> in line for early access to Øditr —
        performance intelligence for modern websites.
      </p>

      <!-- Referral card -->
      <table width="100%" cellpadding="0" cellspacing="0"
             style="border:1px solid #EAEAEA;border-radius:12px;padding:28px;margin-bottom:36px;">
        <tr><td>
          <p style="font-size:10px;letter-spacing:0.22em;text-transform:uppercase;color:#888;margin:0 0 8px;">Move up the list</p>
          <p style="font-size:15px;color:#444;line-height:1.6;margin:0 0 20px;">
            Share your referral link. Every friend who joins moves you one spot closer to the front.
          </p>
          <a href="{referral_url}"
             style="display:inline-block;background:#0A0A0A;color:#ffffff;text-decoration:none;
                    padding:12px 28px;border-radius:999px;font-size:14px;font-weight:500;">
            Share my link →
          </a>
        </td></tr>
      </table>

      <!-- Referral link plain text -->
      <p style="font-size:12px;color:#999;word-break:break-all;margin:0 0 36px;">
        {referral_url}
      </p>

      <!-- Footer -->
      <hr style="border:none;border-top:1px solid #EAEAEA;margin:0 0 24px;">
      <p style="font-size:12px;color:#aaa;line-height:1.6;margin:0;">
        You're receiving this because you joined the Øditr waitlist.<br>
        We'll send one email when early access opens — nothing else.
      </p>
    </td></tr>
  </table>
</body>
</html>"""


def _send_sync(email: str, position: int, referral_code: str) -> None:
    """Synchronous send — run via asyncio.to_thread to stay non-blocking."""
    params: resend.Emails.SendParams = {
        "from": SENDER,
        "to": [email],
        "subject": f"You're #{position} on the Øditr waitlist",
        "html": _build_confirmation_html(position, referral_code),
    }
    resend.Emails.send(params)


async def send_waitlist_confirmation(email: str, position: int, referral_code: str) -> None:
    """
    Fire-and-forget confirmation email.
    Failures are logged but never bubble up to the caller.
    """
    if not resend.api_key:
        logger.warning("RESEND_API_KEY not set — skipping confirmation email")
        return
    try:
        await asyncio.to_thread(_send_sync, email, position, referral_code)
        logger.info(f"Confirmation email sent to {email} (position #{position})")
    except Exception as exc:
        logger.error(f"Email send failed (non-fatal): {exc}")
