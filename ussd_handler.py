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


def _normalize_phone(phone_number: str) -> str:
    """Normalize phone number: strip + prefix for consistent DB lookups."""
    return phone_number.lstrip("+")


def _is_registered(phone_number: str) -> bool:
    """Quick check if a phone number is registered."""
    from models import get_session, User
    phone = _normalize_phone(phone_number)
    sess = get_session()
    try:
        return sess.query(User).filter(
            User.phone_number == phone,
            User.is_active == True,
        ).first() is not None
    finally:
        sess.close()


def _get_user(phone_number: str):
    """Get full user record."""
    from models import get_session, User
    phone = _normalize_phone(phone_number)
    sess = get_session()
    try:
        return sess.query(User).filter(
            User.phone_number == phone,
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
    # Normalize phone number: strip + prefix (AT sends +254..., DB stores 254...)
    phone_number = _normalize_phone(phone_number)
    logger.info(f"USSD: {phone_number} | session={session_id[:8]}... | text='{text}'")

    if not text:
        return _main_menu()

    parts = text.split("*")

    # ==================== UNIVERSAL BACK (0) ====================
    # In USSD, text accumulates: "1*0" means user pressed 1 then 0.
    # Handle "0" = Back at every level so users never get stuck.
    if len(parts) > 1 and parts[-1] == "0":
        depth = len(parts)
        if depth == 2:
            # "X*0" → back to main menu
            return _main_menu()
        if depth == 3:
            if parts[0] == "1":
                return _crypto_menu()
            if parts[0] == "2":
                return _handle_wallet_main(phone_number)
        # depth >= 4: individual flows handle their own "0"

    # ==================== MAIN MENU ====================
    if len(parts) == 1:
        return _handle_main_menu(parts[0], phone_number)

    # ==================== SEND FLOW ====================
    # parts[0] == "1"
    if parts[0] == "1":
        if not _is_registered(phone_number):
            return _build_menu(
                "✨ You need a wallet first!\n"
                "0. Back to main menu\n"
                "(then choose 4. Register)"
            )
        return _handle_send_flow(parts, phone_number)

    # ==================== MY WALLET ====================
    if parts[0] == "2":
        return _handle_wallet_flow(parts, phone_number)

    # ==================== MY TRANSACTIONS ====================
    if parts[0] == "3":
        return _handle_transactions_flow(parts, phone_number)

    # ==================== REGISTER FLOW ====================
    # parts[0] == "4" — simplified: just PIN, no Cardano address needed
    if parts[0] == "4":
        return _handle_register_flow(parts, phone_number)

    # ==================== HELP FLOW ====================
    if parts[0] == "5":
        return _handle_help_flow(parts)

    return _build_menu("❌ Invalid option. Try again.\n0. Back")


# ============================================================
# MAIN MENU
# ============================================================

def _main_menu() -> str:
    """Friendly main menu with all options."""
    menu = (
        "🌧️ RainMaker\n"
        "1. Send Crypto 💱\n"
        "2. My Wallet\n"
        "3. My Transactions 📋\n"
        "4. Register 🔐\n"
        "5. Help ❓\n"
        "0. Exit"
    )
    return _build_menu(menu)


def _crypto_menu() -> str:
    """Sub-menu: choose which crypto to send."""
    return _build_menu(
        "💱 Send Crypto\n"
        "1. Send ADA\n"
        "2. Send DJED\n"
        "0. Back"
    )


def _handle_main_menu(option: str, phone_number: str) -> str:
    if option == "1":
        if not _is_registered(phone_number):
            return _build_menu(
                "✨ You need a wallet first!\n"
                "0. Back to main menu\n"
                "(then choose 4. Register)"
            )
        # Show crypto sub-menu
        return _crypto_menu()

    if option == "2":
        return _handle_wallet_main(phone_number)

    if option == "3":
        return _handle_transactions_flow(["3"], phone_number)

    if option == "4":
        # Check if already registered
        if _is_registered(phone_number):
            return _build_menu(
                "⚠️ You already have a wallet!\n"
                "1. View Address\n"
                "2. Create New Wallet\n"
                "3. Delete Wallet\n"
                "0. Back"
            )
        # New registration — ask for PIN
        return _build_menu(
            "🔐 Create Your Wallet\n"
            "Enter a 4-digit PIN\n"
            "(keep it safe!):\n"
            "0. Back"
        )

    if option == "5":
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
            f"1. Send Crypto 💱\n"
            f"2. Full Address\n"
            f"0. Back"
        )
        return _build_menu(menu)

    # Balance fetch failed — show basic info
    addr_short = user.cardano_address[:10] + "..." + user.cardano_address[-6:]
    menu = (
        f"💰 My Wallet\n"
        f"📱 {phone_number}\n"
        f"🔗 {addr_short}\n"
        f"1. Send Crypto 💱\n"
        f"2. Full Address\n"
        f"0. Back"
    )
    return _build_menu(menu)


def _handle_wallet_flow(parts: list, phone_number: str) -> str:
    """Handle sub-options from My Wallet screen."""
    # parts = ["2"] or ["2", "1"] etc.
    if len(parts) >= 2 and parts[1] == "1":
        # "Send Crypto" from wallet screen
        if not _is_registered(phone_number):
            return _build_menu(
                "✨ You need a wallet first!\n"
                "0. Back to main menu\n"
                "(then choose 4. Register)"
            )
        # If deeper parts exist, route to send flow
        # parts = ["2", "1", token, phone, amount, pin]
        # send flow expects ["1", token, phone, amount, pin]
        if len(parts) >= 3:
            return _handle_send_flow(["1"] + parts[2:], phone_number)
        return _crypto_menu()

    if len(parts) >= 2 and parts[1] == "2":
        # "Full Address" — show complete Cardano address in chunks
        user = _get_user(phone_number)
        if not user:
            return _build_menu("⚠️ No wallet.\n4. Register\n0. Back")
        # Split address into lines of ~35 chars for USSD display
        addr = user.cardano_address
        chunks = [addr[i:i+35] for i in range(0, len(addr), 35)]
        addr_display = "\n".join(chunks)
        return _build_menu(
            f"🔗 Address:\n"
            f"{addr_display}\n"
            f"0. Back",
            is_end=True,
        )

    if len(parts) >= 2 and parts[1] == "0":
        return _main_menu()

    return _build_menu("❌ Invalid option.\n0. Back", is_end=False)


# ============================================================
# SEND FLOW (phone-number-first)
# ============================================================

def _handle_send_flow(parts: list, phone_number: str) -> str:
    """
    Send Crypto flow — token selection, then phone number as recipient.
    parts[0] = "1"
    parts[1] = token ("1"=ADA, "2"=DJED)
    parts[2] = recipient phone number
    parts[3] = amount
    parts[4] = PIN
    """
    step = len(parts) - 1

    # Step 0: Token selection (ADA or DJED)
    if step < 1:
        return _crypto_menu()

    token_choice = parts[1]

    # "0" = back to main menu
    if token_choice == "0":
        return _main_menu()

    # Validate token choice
    if token_choice == "1":
        token_name = "ADA"
    elif token_choice == "2":
        token_name = "DJED"
    else:
        return _build_menu(
            "❌ Invalid option.\n"
            "1. Send ADA\n"
            "2. Send DJED\n"
            "0. Back"
        )

    # Step 1: Enter recipient phone number
    if step < 2:
        return _build_menu(
            f"📤 Send {token_name}\n"
            "Enter phone or ADA address:\n"
            "(e.g. 254712345678\n"
            "or addr_test1...):\n"
            "0. Back"
        )

    recipient_input = parts[2]

    if recipient_input == "0":
        return _crypto_menu()

    # Resolve destination (phone number, $handle, or Cardano address)
    from address_book import resolve_destination
    result = resolve_destination(recipient_input)

    if result.get("error"):
        return _build_menu(
            f"⚠️ {result.get('error', 'Not found')}\n"
            "Use phone, $handle, or\n"
            "Cardano address (addr...):\n"
            "0. Back"
        )

    display = result.get("display_name", recipient_input)

    # Step 2: Enter amount
    if step < 3:
        return _build_menu(
            f"📤 To: {display}\n"
            f"Amount ({token_name}):\n"
            "0. Back"
        )

    amount_str = parts[3]
    if amount_str == "0":
        return _build_menu(
            f"📤 Send {token_name}\n"
            "Enter phone or ADA address:\n"
            "0. Back"
        )

    if not amount_str.replace(".", "").isdigit() or float(amount_str) <= 0:
        return _build_menu(
            "❌ Enter a valid amount\n"
            "(e.g. 10.5):\n"
            "0. Back"
        )

    # Step 3: Enter PIN + Confirm & Send
    if step < 4:
        return _build_menu(
            "🔐 Enter your 4-digit PIN\n"
            "to confirm:\n"
            "0. Back"
        )

    pin = parts[4]

    if pin == "0":
        return _build_menu(
            f"📤 To: {display}\n"
            f"Amount ({token_name}):\n"
            "0. Back"
        )

    try:
        amount = float(amount_str)
        if amount <= 0:
            return _build_menu("❌ Invalid amount.\n0. Back")
    except ValueError:
        return _build_menu("❌ Enter numbers only:\n0. Back")

    # Resolve destination again
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
            "4. Register now\n"
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
            f"⚠️ Daily limit: {daily_limit} {token_name}\n"
            f"Contact support to upgrade.\n"
            f"0. Back"
        )

    # Pre-check balance to avoid confusing "All UTxO selectors failed" error
    from cardano_tx import get_balance
    bal = get_balance(wallet["cardano_address"])
    if bal.get("status") == "ok":
        # Need amount + ~0.17 ADA for fee + min UTXO
        min_required = amount + 0.2
        if bal["ada"] < min_required:
            return _build_menu(
                f"⚠️ Insufficient balance.\n"
                f"Need: {min_required:.2f} {token_name}\n"
                f"Have: {bal['ada']:.2f} ADA\n"
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

        # Save transaction to DB
        _save_transaction(
            sender_phone=phone_number,
            recipient_input=recipient_input,
            resolved_address=dest["address"],
            resolution_type=dest.get("type", "phone"),
            amount=amount,
            token=token_name,
            tx_hash=result["tx_hash"],
            status="confirmed",
        )

        return _build_menu(
            f"✅ Sent {amount} {token_name}\n"
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


# ============================================================
# TRANSACTION HELPERS
# ============================================================

def _save_transaction(sender_phone, recipient_input, resolved_address, resolution_type, amount, token, tx_hash, status="confirmed", error_message=None):
    """Save a transaction record to the database."""
    from models import get_session, Transaction
    import uuid
    from datetime import datetime
    sess = get_session()
    try:
        tx = Transaction(
            id=str(uuid.uuid4()),
            sender_phone=_normalize_phone(sender_phone),
            recipient_input=recipient_input,
            resolved_address=resolved_address,
            resolution_type=resolution_type,
            amount=amount,
            token=token,
            cardano_tx_hash=tx_hash,
            status=status,
            error_message=error_message,
            created_at=datetime.utcnow(),
            confirmed_at=datetime.utcnow() if status == "confirmed" else None,
        )
        sess.add(tx)
        sess.commit()
    except Exception as e:
        logger.error(f"Failed to save transaction: {e}")
        sess.rollback()
    finally:
        sess.close()


def _handle_transactions_flow(parts: list, phone_number: str) -> str:
    """
    My Transactions flow — show recent sent AND received transactions.
    parts[0] = "3"
    """
    from models import get_session, Transaction
    from sqlalchemy import or_
    phone = _normalize_phone(phone_number)
    sess = get_session()
    try:
        # Show both sent AND received transactions
        txs = sess.query(Transaction).filter(
            or_(
                Transaction.sender_phone == phone,
                Transaction.recipient_input == phone,
            )
        ).order_by(Transaction.created_at.desc()).limit(5).all()

        if not txs:
            return _build_menu(
                "📋 No transactions yet.\n"
                "Send crypto to see history!\n"
                "0. Back"
            )

        lines = ["📋 Recent Transactions\n"]
        for i, tx in enumerate(txs, 1):
            status_icon = "✅" if tx.status == "confirmed" else "❌" if tx.status == "failed" else "⏳"
            tx_short = tx.cardano_tx_hash[:8] + "..." if tx.cardano_tx_hash else "N/A"
            # Format date
            date_str = tx.created_at.strftime("%m/%d %H:%M") if tx.created_at else "?"
            # Show direction: sent (📤) or received (📥)
            if tx.sender_phone == phone:
                direction = "📤"
                counterparty = f"To: {tx.recipient_input[:12]}"
            else:
                direction = "📥"
                counterparty = f"From: {tx.sender_phone[:12]}"
            lines.append(
                f"{i}. {status_icon}{direction} {tx.amount} {tx.token}\n"
                f"   {counterparty}\n"
                f"   {date_str} | {tx_short}"
            )

        lines.append("0. Back")
        return _build_menu("\n".join(lines))
    finally:
        sess.close()


# ============================================================
# REGISTER FLOW (simplified — just PIN + auto-wallet)
# ============================================================

def _handle_register_flow(parts: list, phone_number: str) -> str:
    """
    Register flow — handles both new registration and existing wallet management.
    
    If NOT registered:
      parts[0] = "4", parts[1] = PIN, parts[2] = confirm PIN
    
    If ALREADY registered:
      parts[0] = "4", parts[1] = "1" (view address), "2" (create new), "3" (delete)
      For "2" (create new): parts[2] = PIN, parts[3] = confirm PIN
      For "3" (delete): parts[2] = PIN (confirm deletion)
    """
    step = len(parts) - 1
    already_registered = _is_registered(phone_number)

    # ==================== EXISTING WALLET MENU ====================
    if already_registered:
        # Step 1: Show options menu
        if step < 1:
            return _build_menu(
                "⚠️ You already have a wallet!\n"
                "1. View Address\n"
                "2. Create New Wallet\n"
                "3. Delete Wallet\n"
                "0. Back"
            )

        option = parts[1]

        # Option 1: View full address
        if option == "1":
            user = _get_user(phone_number)
            if not user:
                return _main_menu()
            addr = user.cardano_address
            chunks = [addr[i:i+35] for i in range(0, len(addr), 35)]
            addr_display = "\n".join(chunks)
            return _build_menu(
                f"🔗 Your Address:\n"
                f"{addr_display}\n"
                f"0. Back",
                is_end=True,
            )

        # Option 2: Create new wallet (replace old one)
        if option == "2":
            # Need PIN + confirm
            if step < 3:
                if step == 1:
                    return _build_menu(
                        "🔐 New Wallet PIN\n"
                        "Enter 4-digit PIN:\n"
                        "0. Back"
                    )
                if step == 2:
                    pin = parts[2]
                    if not (pin.isdigit() and len(pin) >= 4):
                        return _build_menu(
                            "❌ PIN must be 4+ digits.\n"
                            "Try again:\n"
                            "0. Back"
                        )
                    return _build_menu(
                        "🔐 Confirm new PIN:\n"
                        "0. Back"
                    )
                return _build_menu("❌ Error. Try again.", is_end=True)

            # step >= 3: confirm PIN and replace wallet
            pin = parts[2]
            confirm_pin = parts[3]

            if pin != confirm_pin:
                return _build_menu(
                    "❌ PINs don't match!\n"
                    "Enter PIN again:\n"
                    "0. Back"
                )

            # Delete old wallet and create new one
            from wallet_manager import delete_wallet, create_wallet
            delete_wallet(phone_number)
            result = create_wallet(phone_number, pin)

            if result.get("status") == "created":
                addr = result.get("cardano_address", "")
                seed = result.get("seed_phrase", "")
                addr_short = addr[:10] + "..." + addr[-6:]
                seed_words = seed.split()
                seed_compact = " ".join(seed_words[:6]) + ("..." if len(seed_words) > 6 else "")

                # Send SMS
                try:
                    from sms_service import send_wallet_sms
                    send_wallet_sms(phone_number, addr, seed)
                except Exception:
                    pass

                return _build_menu(
                    f"🎉 New Wallet Created!\n"
                    f"🔗 {addr_short}\n"
                    f"⚠️ SAVE: {seed_compact}\n"
                    f"0. Exit",
                    is_end=True,
                )
            return _build_menu(f"❌ {result.get('error', 'Error')}", is_end=True)

        # Option 3: Delete wallet
        if option == "3":
            if step < 2:
                return _build_menu(
                    "⚠️ DELETE wallet?\n"
                    "This cannot be undone!\n"
                    "Enter PIN to confirm:\n"
                    "0. Back"
                )

            pin = parts[2]
            from wallet_manager import delete_wallet_with_pin
            result = delete_wallet_with_pin(phone_number, pin)

            if result.get("status") == "deleted":
                return _build_menu(
                    "🗑️ Wallet deleted.\n"
                    "You can register again anytime.\n"
                    "0. Exit",
                    is_end=True,
                )
            elif result.get("status") == "wrong_pin":
                return _build_menu(
                    "❌ Wrong PIN.\n"
                    "Wallet NOT deleted.\n"
                    "0. Back"
                )
            return _build_menu(f"❌ {result.get('error', 'Error')}", is_end=True)

        if option == "0":
            return _main_menu()

        return _build_menu("❌ Invalid option.\n0. Back")

    # ==================== NEW REGISTRATION ====================
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

        # Show seed phrase compactly — first 6 words
        seed_words = seed_short.split()
        seed_compact = " ".join(seed_words[:6]) + ("..." if len(seed_words) > 6 else "")

        return _build_menu(
            f"🎉 Welcome!\n"
            f"☂️ {phone_number}\n"
            f"🔗 {addr_short}\n"
            f"⚠️ SAVE: {seed_compact}\n"
            f"1. Send Crypto | 0. Exit",
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
        "4. Register: 4 + PIN\n"
        "0. Back"
    )


def _handle_help_flow(parts: list) -> str:
    """Handle help sub-menus."""
    if len(parts) >= 2 and parts[1] == "0":
        return _main_menu()

    # Just show main help again
    return _help_main()
