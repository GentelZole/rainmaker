"""
🌧️ RainMaker — USSD Handler
User-journey: guided, friendly, phone-as-wallet, back-options everywhere.
"""
from typing import Tuple
import logging

logger = logging.getLogger(__name__)

# USSD character limit
MAX_CHARS = 160


def _build_menu(text: str, is_end: bool = False) -> str:
    """Build a USSD response with proper prefix (CON or END)."""
    prefix = "END" if is_end else "CON"
    if len(text) > 155:
        text = text[:152] + "..."
    return f"{prefix} {text}"


def _is_registered(phone_number: str) -> bool:
    """Quick check if a phone number is registered."""
    from models import get_session, User
    sess = get_session()
    try:
        return sess.query(User).filter(
            User.phone_number == phone_number,
            User.is_active == True,
        ).first() is not None
    finally:
        sess.close()


def _get_user(phone_number: str):
    """Get full user record."""
    from models import get_session, User
    sess = get_session()
    try:
        return sess.query(User).filter(
            User.phone_number == phone_number,
            User.is_active == True,
        ).first()
    finally:
        sess.close()


# ============================================================
# MAIN ENTRY
# ============================================================

def handle_ussd(session_id: str, phone_number: str, text: str) -> str:
    """
    Main USSD handler — called by Africa's Talking on each user input.
    text is empty on first call, then concatenates user inputs with *.
    """
    logger.info(f"USSD: {phone_number} | session={session_id[:8]}... | text='{text}'")

    if not text:
        return _main_menu()

    parts = text.split("*")

    # ==================== MAIN MENU ====================
    if len(parts) == 1:
        return _handle_main_menu(parts[0], phone_number)

    # ==================== SEND FLOW ====================
    # parts[0] == "1"
    if parts[0] == "1":
        if not _is_registered(phone_number):
            return _build_menu(
                "✨ You're not registered yet!\n"
                "It's free and takes 10 seconds.\n"
                "3. Register now\n"
                "0. Back"
            )
        return _handle_send_flow(parts, phone_number)

    # ==================== MY WALLET ====================
    if parts[0] == "2":
        return _handle_wallet_flow(parts, phone_number)

    # ==================== REGISTER FLOW ====================
    # parts[0] == "3" — simplified: just PIN, no Cardano address needed
    if parts[0] == "3":
        return _handle_register_flow(parts, phone_number)

    # ==================== HELP FLOW ====================
    if parts[0] == "4":
        return _handle_help_flow(parts)

    return _build_menu("❌ Invalid option. Try again.\n0. Back")


# ============================================================
# MAIN MENU
# ============================================================

def _main_menu() -> str:
    """Friendly main menu with all options."""
    menu = (
        "🌧️ RainMaker\n"
        "1. Send DJED\n"
        "2. My Wallet\n"
        "3. Register 🔐\n"
        "4. Help ❓\n"
        "0. Exit"
    )
    return _build_menu(menu)


def _handle_main_menu(option: str, phone_number: str) -> str:
    if option == "1":
        if not _is_registered(phone_number):
            return _build_menu(
                "✨ You're not registered yet!\n"
                "It's free — just create a PIN.\n"
                "3. Register now\n"
                "0. Back"
            )
        # Start send flow: ask for recipient's phone number
        return _build_menu(
            "📤 Send DJED\n"
            "Enter receiver's phone number\n"
            "(e.g. 254712345678):\n"
            "0. Back"
        )

    if option == "2":
        return _handle_wallet_main(phone_number)

    if option == "3":
        # Simplified registration — no Cardano address needed
        return _build_menu(
            "🔐 Create Your Wallet\n"
            "Enter a 4-digit PIN\n"
            "(keep it safe!):\n"
            "0. Back"
        )

    if option == "4":
        return _help_main()

    if option == "0":
        return _build_menu(
            "👋 Thank you for using RainMaker!\n"
            "Send money anywhere, anytime.\n"
            "🌧️ rainmaker.dj",
            is_end=True,
        )

    return _build_menu("❌ Invalid option.\n0. Back")


# ============================================================
# MY WALLET
# ============================================================

def _handle_wallet_main(phone_number: str) -> str:
    """Show wallet or guide to register."""
    user = _get_user(phone_number)
    if not user:
        return _build_menu(
            "⚠️ No wallet yet!\n"
            "RainMaker is free to join.\n"
            "1. Register now\n"
            "0. Back"
        )

    from cardano_tx import get_balance
    bal = get_balance(user.cardano_address)

    if bal.get("status") == "ok":
        addr_short = user.cardano_address[:10] + "..." + user.cardano_address[-6:]
        menu = (
            f"💰 My Wallet\n"
            f"ADA: {bal['ada']:.2f}\n"
            f"DJED: {bal['djed']:.2f}\n"
            f"📱 {phone_number}\n"
            f"🔗 {addr_short}\n"
            f"1. Send DJED\n"
            f"0. Back"
        )
        return _build_menu(menu)

    # Balance fetch failed — show basic info
    addr_short = user.cardano_address[:10] + "..." + user.cardano_address[-6:]
    menu = (
        f"💰 My Wallet\n"
        f"📱 {phone_number}\n"
        f"🔗 {addr_short}\n"
        f"1. Send DJED\n"
        f"0. Back"
    )
    return _build_menu(menu)


def _handle_wallet_flow(parts: list, phone_number: str) -> str:
    """Handle sub-options from My Wallet screen."""
    # parts = ["2"] or ["2", "1"] etc.
    if len(parts) >= 2 and parts[1] == "1":
        # "Send DJED" from wallet screen
        if not _is_registered(phone_number):
            return _build_menu("⚠️ Register first!\n3. Register\n0. Back")
        return _build_menu(
            "📤 Send DJED\n"
            "Enter receiver's phone number:\n"
            "0. Back"
        )

    if len(parts) >= 2 and parts[1] == "0":
        return _main_menu()

    return _build_menu("❌ Invalid option.\n0. Back", is_end=False)


# ============================================================
# SEND FLOW (phone-number-first)
# ============================================================

def _handle_send_flow(parts: list, phone_number: str) -> str:
    """
    Send DJED flow — phone number as recipient.
    parts[0] = "1"
    parts[1] = recipient phone number
    parts[2] = amount
    parts[3] = PIN
    """
    step = len(parts) - 1

    # Step 1: Enter recipient phone number
    if step < 2:
        if len(parts) >= 2 and parts[1] == "0":
            return _main_menu()

        if len(parts) < 2:
            return _build_menu(
                "📤 Enter receiver's phone number:\n"
                "0. Back"
            )

        recipient_input = parts[1]

        # If user entered "0", go back
        if recipient_input == "0":
            return _main_menu()

        # Clean the phone number
        if not recipient_input.isdigit():
            return _build_menu(
                "❌ Phone numbers only!\n"
                "Enter digits (e.g. 254712345678):\n"
                "0. Back"
            )

        # Check if recipient is registered in our system
        from address_book import resolve_destination
        result = resolve_destination(recipient_input)

        if result.get("error"):
            return _build_menu(
                f"⚠️ {recipient_input} not registered\n"
                "Ask them to dial *384*225533#\n"
                "and register first.\n"
                "0. Back"
            )

        # Recipient found! Ask for amount
        display = result.get("display_name", recipient_input)
        return _build_menu(
            f"📤 To: {display}\n"
            "Amount (DJED):\n"
            "0. Back"
        )

    # Step 2: Enter amount
    if step < 3:
        amount = parts[2]
        if amount == "0":
            # Go back to recipient entry
            return _build_menu(
                "📤 Enter receiver's phone number:\n"
                "0. Back"
            )

        if not amount.replace(".", "").isdigit() or float(amount) <= 0:
            return _build_menu(
                "❌ Enter a valid amount\n"
                "(e.g. 10.5):\n"
                "0. Back"
            )

        return _build_menu(
            "🔐 Enter your 4-digit PIN\nto confirm:\n"
            "0. Back"
        )

    # Step 3: Enter PIN + Confirm & Send
    if step >= 3:
        recipient_input = parts[1]
        amount_str = parts[2]
        pin = parts[3]

        if pin == "0":
            # Go back to amount
            return _build_menu(
                f"📤 To: {recipient_input}\n"
                "Amount (DJED):\n"
                "0. Back"
            )

        try:
            amount = float(amount_str)
            if amount <= 0:
                return _build_menu("❌ Invalid amount.\n0. Back")
        except ValueError:
            return _build_menu("❌ Enter numbers only:\n0. Back")

        # Resolve destination again
        from address_book import resolve_destination
        dest = resolve_destination(recipient_input)
        if dest.get("error"):
            return _build_menu(
                "⚠️ Recipient not found.\n"
                "They need to register first.\n"
                "0. Back"
            )

        # Get sender wallet
        from wallet_manager import get_wallet_for_send
        wallet = get_wallet_for_send(phone_number, pin)
        if wallet is None:
            return _build_menu(
                "❌ Not registered.\n"
                "3. Register now\n"
                "0. Back"
            )

        if wallet.get("status") == "wrong_pin":
            remaining = 5 - wallet.get("attempts", 1)
            if remaining <= 0:
                return _build_menu(
                    "🔒 Account locked for 24h.\n"
                    "Too many wrong PIN attempts.\n"
                    "Contact support.",
                    is_end=True,
                )
            return _build_menu(
                f"❌ Wrong PIN. {remaining} tries left:\n"
                "0. Back"
            )

        if wallet.get("status") == "locked":
            return _build_menu(
                "🔒 Account locked.\n"
                "Try again later.",
                is_end=True,
            )

        if wallet.get("status") != "ok":
            return _build_menu(
                "❌ Error. Try again.\n"
                "0. Back"
            )

        # Check KYC limits
        kyc_level = wallet.get("kyc_level", 0)
        limits = {0: 10, 1: 100, 2: 500}
        daily_limit = limits.get(kyc_level, 10)

        if amount > daily_limit:
            return _build_menu(
                f"⚠️ Daily limit: ${daily_limit}\n"
                f"Contact support to upgrade.\n"
                f"0. Back"
            )

        # Build and submit transaction
        from cardano_tx import build_and_submit_tx
        result = build_and_submit_tx(
            sender_seed=wallet["seed_phrase"],
            sender_address=wallet["cardano_address"],
            recipient_address=dest["address"],
            amount_djed=amount,
        )

        if result["status"] == "submitted":
            tx_short = result["tx_hash"][:10] + "..."
            recipient_display = dest.get("display_name", recipient_input[:10])
            return _build_menu(
                f"✅ Sent {amount} DJED\n"
                f"To: {recipient_display}\n"
                f"💰 Fee: $0.10\n"
                f"⛓️ {tx_short}",
                is_end=True,
            )
        else:
            logger.error(f"TX failed: {result.get('error')}")
            return _build_menu(
                "❌ Transaction failed.\n"
                "Try again later.",
                is_end=True,
            )

    return _build_menu("❌ Session error. Start over.", is_end=True)


# ============================================================
# REGISTER FLOW (simplified — just PIN + auto-wallet)
# ============================================================

def _handle_register_flow(parts: list, phone_number: str) -> str:
    """
    Register: just ask for PIN, auto-generate wallet.
    No Cardano address needed — phone IS the wallet.

    parts[0] = "3"
    parts[1] = PIN
    parts[2] = PIN confirm (optional, we keep it simple)
    """
    step = len(parts) - 1

    # Step 1: Enter PIN
    if step < 2:
        if len(parts) >= 2 and parts[1] == "0":
            return _main_menu()

        if len(parts) < 2:
            return _build_menu(
                "🔐 Create Your Wallet\n"
                "Enter a 4-digit PIN:\n"
                "0. Back"
            )

        pin = parts[1]
        if not (pin.isdigit() and len(pin) >= 4):
            return _build_menu(
                "❌ PIN must be 4+ digits.\n"
                "Try again:\n"
                "0. Back"
            )

        # Ask to confirm PIN
        return _build_menu(
            "🔐 Confirm your PIN:\n"
            "0. Back"
        )

    # Step 2: Confirm PIN and create wallet
    if step >= 2:
        pin = parts[1]
        confirm_pin = parts[2]

        if confirm_pin == "0":
            return _build_menu(
                "🔐 Enter a 4-digit PIN:\n"
                "0. Back"
            )

        if pin != confirm_pin:
            return _build_menu(
                "❌ PINs don't match!\n"
                "Enter your PIN again:\n"
                "0. Back"
            )

        # Create wallet — auto-generates HD wallet + Cardano address
        from wallet_manager import create_wallet
        result = create_wallet(phone_number, pin)

        if result.get("status") == "error":
            if "already registered" in result.get("error", ""):
                return _build_menu(
                    "✅ Already registered!\n"
                    "Use 'My Wallet' to manage.\n"
                    "0. Back",
                )
            return _build_menu(
                f"❌ {result.get('error')}\n"
                "Try again.",
                is_end=True,
            )

        # Success!
        seed_short = result.get("seed_phrase", "")
        addr = result.get("cardano_address", "")
        addr_short = addr[:10] + "..." + addr[-6:]

        # Send SMS with wallet credentials (fire-and-forget)
        try:
            from sms_service import send_wallet_sms
            send_wallet_sms(phone_number, addr, seed_short)
            logger.info(f"📨 Wallet SMS sent to {phone_number}")
        except Exception as e:
            logger.warning(f"⚠️ Wallet SMS failed: {e}")
            # Don't block registration — SMS is best-effort

        # Show seed phrase compactly — first 8 words
        seed_words = seed_short.split()
        seed_compact = " ".join(seed_words[:6]) + ("..." if len(seed_words) > 6 else "")

        return _build_menu(
            f"🎉 Welcome!\n"
            f"☂️ {phone_number}\n"
            f"🔗 {addr_short}\n"
            f"⚠️ SAVE: {seed_compact}\n"
            f"1. Send DJED | 0. Exit",
            is_end=True,
        )

    return _build_menu("❌ Registration error. Try again.", is_end=True)


# ============================================================
# HELP
# ============================================================

def _help_main() -> str:
    """Show help menu."""
    return _build_menu(
        "📖 RainMaker Help\n"
        "1. Send: 1 + phone# + amount\n"
        "2. Fees: $0.10/transfer\n"
        "3. Limit: $10/day (upgradeable)\n"
        "4. Register: 3 + PIN\n"
        "0. Back"
    )


def _handle_help_flow(parts: list) -> str:
    """Handle help sub-menus."""
    if len(parts) >= 2 and parts[1] == "0":
        return _main_menu()

    # Just show main help again
    return _help_main()
