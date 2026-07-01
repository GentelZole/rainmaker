"""
🌧️ RainMaker — SMS Notification Service
Sends wallet credentials and alerts via Africa's Talking SMS API.
"""
import logging
import httpx
from config import get_settings

logger = logging.getLogger("rainmaker.sms")


def send_sms(to: str, message: str) -> dict:
    """
    Send an SMS via Africa's Talking API.
    
    Args:
        to: Phone number (e.g. '254712345678')
        message: SMS text content
    Returns:
        dict with status and details
    """
    settings = get_settings()

    if not settings.at_api_key or settings.at_username == "sandbox":
        # In sandbox, log instead of sending
        logger.info(f"📨 [SANDBOX SMS] To: {to} | Msg: {message[:60]}...")
        return {
            "status": "sandbox",
            "message": "SMS logged (sandbox mode - no actual SMS sent)",
        }

    try:
        url = "https://api.africastalking.com/version1/messaging"
        headers = {
            "apiKey": settings.at_api_key,
            "Accept": "application/json",
        }
        data = {
            "username": settings.at_username,
            "to": to,
            "message": message,
            "from": "RainMaker",  # Alphanumeric sender ID
        }

        with httpx.Client(timeout=15) as client:
            resp = client.post(url, headers=headers, data=data)
            resp.raise_for_status()
            result = resp.json()

        logger.info(f"📨 SMS sent to {to}: {result.get('SMSMessageData', {}).get('Message', 'OK')}")
        return {"status": "sent", "response": result}

    except Exception as e:
        logger.error(f"❌ SMS failed for {to}: {e}")
        return {"status": "failed", "error": str(e)}


def send_wallet_sms(phone_number: str, cardano_address: str, seed_phrase: str) -> dict:
    """
    Send wallet credentials via SMS after registration.
    
    The SMS contains:
    - Cardano wallet address (for receiving from outside RainMaker)
    - Seed phrase (for wallet recovery)
    
    WARNING: Seed phrase in SMS is a security trade-off.
    For MVP it's essential since users have feature phones.
    Future: encrypted storage + recovery via USSD.
    """
    # Truncate seed to first 6 words for SMS (full phrase shown on USSD)
    seed_words = seed_phrase.split()
    seed_compact = " ".join(seed_words[:6]) + ("..." if len(seed_words) > 6 else "")

    message = (
        f"🌧️ RainMaker Wallet\n"
        f"Phone: {phone_number}\n"
        f"Address: {cardano_address}\n"
        f"\n"
        f"⚠️ Recovery phrase:\n"
        f"{seed_phrase}\n"
        f"\n"
        f"Keep this secret! Never share it.\n"
        f"Dial *384*225533# to send DJED."
    )

    return send_sms(phone_number, message)