"""Wallet Manager — HD wallet generation, PIN encryption, seed phrase handling"""
import os
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Tuple

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from models import User, get_session


def _normalize_phone(phone_number: str) -> str:
    """Normalize phone number: strip + prefix for consistent DB lookups."""
    return phone_number.lstrip("+")


def _derive_key(pin: str, salt: bytes) -> bytes:
    """Derive AES-256 key from PIN using PBKDF2"""
    return hashlib.pbkdf2_hmac(
        "sha256",
        pin.encode(),
        salt,
        iterations=600_000,
        dklen=32,
    )


def encrypt_seed(seed_phrase: str, pin: str) -> str:
    """Encrypt seed phrase with PIN-derived key. Returns hex: salt + nonce + ciphertext"""
    salt = os.urandom(16)
    nonce = os.urandom(12)
    key = _derive_key(pin, salt)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, seed_phrase.encode(), None)
    return salt.hex() + ":" + nonce.hex() + ":" + ciphertext.hex()


def decrypt_seed(encrypted: str, pin: str) -> Optional[str]:
    """Decrypt seed phrase using PIN. Returns None if PIN is wrong"""
    try:
        parts = encrypted.split(":")
        if len(parts) != 3:
            return None
        salt = bytes.fromhex(parts[0])
        nonce = bytes.fromhex(parts[1])
        ciphertext = bytes.fromhex(parts[2])
        key = _derive_key(pin, salt)
        aesgcm = AESGCM(key)
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
        return plaintext.decode()
    except Exception:
        return None


def hash_pin(pin: str) -> str:
    """Hash PIN using bcrypt (slow, GPU-resistant)"""
    import bcrypt
    return bcrypt.hashpw(pin.encode(), bcrypt.gensalt(rounds=12)).decode()


def verify_pin(pin: str, stored_hash: str) -> bool:
    """Verify PIN against bcrypt hash"""
    import bcrypt
    try:
        return bcrypt.checkpw(pin.encode(), stored_hash.encode())
    except Exception:
        return False


def create_wallet(phone_number: str, pin: str) -> dict:
    """Create a new wallet for a phone number with PIN"""
    # ponytail: inline import avoids cbor2 module-level crash
    from pycardano import (
        HDWallet, Network, Address,
        PaymentExtendedSigningKey, StakeExtendedSigningKey,
    )

    session = get_session()
    try:
        # Check if user exists
        existing = session.query(User).filter(
            User.phone_number == _normalize_phone(phone_number)
        ).first()
        if existing:
            return {"status": "error", "error": "Phone number already registered"}

        # Generate HD wallet (12-word seed)
        # ponytail: HDWallet.generate() removed in 0.19.x
        mnemonic_str = HDWallet.generate_mnemonic(strength=128)
        wallet = HDWallet.from_mnemonic(mnemonic_str)
        seed_phrase = mnemonic_str

        # Derive payment keys (CIP-1852, m/1852'/1815'/0'/0/0)
        network = Network.TESTNET  # preprod
        payment_hdw = wallet.derive_from_path("m/1852'/1815'/0'/0/0")
        stake_hdw = wallet.derive_from_path("m/1852'/1815'/0'/2/0")

        # ponytail: derive_from_path returns HDWallet in 0.19.x; use from_hdwallet()
        payment_sk = PaymentExtendedSigningKey.from_hdwallet(payment_hdw)
        stake_sk = StakeExtendedSigningKey.from_hdwallet(stake_hdw)
        payment_vk_hash = payment_sk.to_verification_key().hash()
        stake_vk_hash = stake_sk.to_verification_key().hash()

        cardano_address = Address(
            payment_part=payment_vk_hash,
            staking_part=stake_vk_hash,
            network=network,
        )

        # Encrypt seed with PIN
        encrypted = encrypt_seed(seed_phrase, pin)
        pin_hashed = hash_pin(pin)

        # Save user
        user = User(
            phone_number=phone_number,
            cardano_address=str(cardano_address),
            stake_address=str(stake_vk_hash),
            encrypted_seed=encrypted,
            pin_hash=pin_hashed,
            handle_name=phone_number,
        )
        session.add(user)
        session.commit()

        # Also register in address book
        from address_book import register_phone
        register_phone(phone_number, str(cardano_address),
                      str(stake_vk_hash),
                      phone_number, user.id)

        return {
            "status": "created",
            "phone_number": phone_number,
            "cardano_address": str(cardano_address),
            "seed_phrase": seed_phrase,  # Show ONCE during registration
        }
    finally:
        session.close()


def get_wallet_for_send(phone_number: str, pin: str) -> Optional[dict]:
    """Decrypt wallet for sending a transaction. Returns None if PIN wrong."""
    session = get_session()
    try:
        user = session.query(User).filter(
            User.phone_number == _normalize_phone(phone_number),
            User.is_active == True,
        ).first()

        if not user:
            return None

        # Check lockout
        if user.locked_until and user.locked_until > datetime.utcnow():
            return {"status": "locked", "locked_until": user.locked_until.isoformat()}

        # Verify PIN
        if not verify_pin(pin, user.pin_hash):
            user.pin_attempts = (user.pin_attempts or 0) + 1
            if user.pin_attempts >= 5:
                user.locked_until = datetime.utcnow() + timedelta(hours=24)
            session.commit()
            return {"status": "wrong_pin", "attempts": user.pin_attempts}

        # Reset attempts on success
        user.pin_attempts = 0
        user.locked_until = None
        session.commit()

        # Decrypt seed
        seed = decrypt_seed(user.encrypted_seed, pin)
        if not seed:
            return {"status": "error", "error": "Failed to decrypt wallet"}

        return {
            "status": "ok",
            "user_id": user.id,
            "phone_number": user.phone_number,
            "cardano_address": user.cardano_address,
            "seed_phrase": seed,
            "kyc_level": user.kyc_level,
        }
    finally:
        session.close()


def delete_wallet(phone_number: str) -> dict:
    """Delete a wallet (soft delete — mark inactive). Used when creating a new wallet."""
    session = get_session()
    try:
        user = session.query(User).filter(
            User.phone_number == _normalize_phone(phone_number),
        ).first()
        if not user:
            return {"status": "error", "error": "No wallet found"}

        user.is_active = False
        session.commit()

        # Also remove from address book
        try:
            from address_book import unregister_phone
            unregister_phone(phone_number)
        except Exception:
            pass

        return {"status": "deleted", "phone_number": phone_number}
    finally:
        session.close()


def delete_wallet_with_pin(phone_number: str, pin: str) -> dict:
    """Delete wallet after verifying PIN. Safer than delete_wallet."""
    session = get_session()
    try:
        user = session.query(User).filter(
            User.phone_number == _normalize_phone(phone_number),
            User.is_active == True,
        ).first()
        if not user:
            return {"status": "error", "error": "No active wallet found"}

        # Verify PIN before deletion
        if not verify_pin(pin, user.pin_hash):
            return {"status": "wrong_pin"}

        user.is_active = False
        session.commit()

        # Remove from address book
        try:
            from address_book import unregister_phone
            unregister_phone(phone_number)
        except Exception:
            pass

        return {"status": "deleted", "phone_number": phone_number}
    finally:
        session.close()