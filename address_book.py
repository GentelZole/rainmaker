"""Address Book — Phone Number ↔ Cardano Address Resolution"""
from typing import Optional
from models import AddressBook, get_session


def _normalize_phone(phone_number: str) -> str:
    """Normalize phone number: strip + prefix for consistent DB lookups."""
    return phone_number.lstrip("+")


def lookup_by_phone(phone_number: str) -> Optional[dict]:
    """Resolve phone number to Cardano address (Tier 1 — MVP)"""
    session = get_session()
    try:
        entry = session.query(AddressBook).filter(
            AddressBook.phone_number == _normalize_phone(phone_number)
        ).first()
        if entry:
            return {
                "type": "phone",
                "address": entry.cardano_address,
                "stake_address": entry.stake_address,
                "display_name": entry.handle_name or phone_number,
                "kyc_level": entry.kyc_level,
                "is_verified": entry.is_verified,
            }
        return None
    finally:
        session.close()


def register_phone(
    phone_number: str,
    cardano_address: str,
    stake_address: Optional[str] = None,
    handle_name: Optional[str] = None,
    owner_user_id: Optional[str] = None,
) -> dict:
    """Register a phone number ↔ Cardano address mapping"""
    session = get_session()
    try:
        existing = session.query(AddressBook).filter(
            AddressBook.phone_number == _normalize_phone(phone_number)
        ).first()
        if existing:
            existing.cardano_address = cardano_address
            existing.stake_address = stake_address or existing.stake_address
            existing.handle_name = handle_name or existing.handle_name
            existing.updated_at = __import__("datetime").datetime.utcnow()
            session.commit()
            return {"status": "updated", "phone": phone_number}
        
        entry = AddressBook(
            phone_number=phone_number,
            cardano_address=cardano_address,
            stake_address=stake_address,
            handle_name=handle_name,
            owner_user_id=owner_user_id,
        )
        session.add(entry)
        session.commit()
        return {"status": "created", "phone": phone_number}
    finally:
        session.close()


def unregister_phone(phone_number: str) -> dict:
    """Remove a phone number from the address book."""
    session = get_session()
    try:
        entry = session.query(AddressBook).filter(
            AddressBook.phone_number == _normalize_phone(phone_number)
        ).first()
        if entry:
            session.delete(entry)
            session.commit()
            return {"status": "deleted", "phone": phone_number}
        return {"status": "not_found", "phone": phone_number}
    finally:
        session.close()


def resolve_destination(input_str: str) -> dict:
    """
    3-tier address resolution:
    1. Phone number (digit string, >= 10 chars, optional + prefix)
    2. ADA Handle (starts with $) — post-MVP stub
    3. Full Cardano address (starts with addr)
    """
    # Strip whitespace
    input_str = input_str.strip()

    # Tier 1: Phone number (allow + prefix)
    phone = input_str.lstrip("+")
    if phone.isdigit() and len(phone) >= 10:
        result = lookup_by_phone(phone)
        if result:
            return result
        # Also try with + prefix in case stored that way
        result = lookup_by_phone(input_str)
        if result:
            return result
        return {
            "type": "unregistered",
            "error": "Phone number not registered",
            "prompt": "Ask recipient to register first, or use their Cardano address",
        }

    # Tier 2: ADA Handle ($handle) — stub for post-MVP
    if input_str.startswith("$"):
        return {
            "type": "handle_stub",
            "error": "ADA Handle support coming soon",
            "prompt": "Use phone number or full Cardano address instead",
        }

    # Tier 3: Full Cardano address
    if input_str.startswith("addr") or input_str.startswith("addr_test"):
        return {
            "type": "full_address",
            "address": input_str,
            "display_name": input_str[:12] + "..." + input_str[-8:],
        }

    # Unknown format
    return {
        "type": "unknown",
        "error": "Invalid input. Enter phone number, $handle, or Cardano address",
    }
