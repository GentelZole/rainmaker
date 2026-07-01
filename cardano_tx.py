"""Cardano Transaction Builder — pycardano + Blockfrost integration"""
from typing import Optional
from config import get_settings


def build_and_submit_tx(
    sender_seed: str,
    sender_address: str,
    recipient_address: str,
    amount_djed: float,  # ponytail: ADA for testnet, param name kept for backward compat
) -> dict:
    """
    Build and submit an ADA transfer on Cardano (Preprod Testnet).

    Uses pycardano HDWallet from seed, builds transaction,
    signs with sender key, and submits via Blockfrost.
    """
    # ponytail: inline import avoids cbor2 module-level crash
    from pycardano import (
        Address, Network, HDWallet,
        TransactionBuilder, TransactionOutput,
        BlockFrostChainContext, PaymentExtendedSigningKey,
    )
    from pycardano.exception import TransactionFailedException

    settings = get_settings()

    try:
        # ponytail: from_mnemonic takes str (not list) in 0.19.x
        wallet = HDWallet.from_mnemonic(sender_seed)
        payment_hdw = wallet.derive_from_path("m/1852'/1815'/0'/0/0")
        # ponytail: from_hdwallet() instead of old to_signing_key()
        payment_sk = PaymentExtendedSigningKey.from_hdwallet(payment_hdw)

        network = Network.TESTNET if settings.cardano_network == "preprod" else Network.MAINNET

        # Parse addresses
        sender_addr = Address.from_primitive(sender_address)
        recipient_addr = Address.from_primitive(recipient_address)

        # ponytail: ADA-only transfer for testnet MVP
        lovelace_amount = int(amount_djed * 1_000_000)

        # Blockfrost context
        # ponytail: network=Network.TESTNET (enum, not string; base_url is future direction)
        context = BlockFrostChainContext(
            project_id=settings.blockfrost_project_id,
            network=network,
        )

        # Build transaction
        builder = TransactionBuilder(context)
        output = TransactionOutput(recipient_addr, lovelace_amount)
        builder.add_output(output)
        builder.add_change_address(sender_addr)

        # Build & sign
        signed_tx = builder.build_and_sign(
            signing_keys=[payment_sk],
            change_address=sender_addr,
        )

        # Submit
        tx_hash = context.submit_tx(signed_tx.to_cbor())

        return {
            "status": "submitted",
            "tx_hash": str(tx_hash),
            "amount": amount_djed,
            "token": "ADA",
            "recipient": recipient_address,
        }

    except TransactionFailedException as e:
        return {"status": "failed", "error": str(e)}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def get_balance(address: str) -> dict:
    """Get ADA and DJED balance for an address via Blockfrost"""
    import httpx

    settings = get_settings()
    headers = {"project_id": settings.blockfrost_project_id}

    try:
        # Get ADA balance
        with httpx.Client() as client:
            resp = client.get(
                f"https://cardano-{settings.cardano_network}.blockfrost.io/api/v0/addresses/{address}",
                headers=headers,
            )
            if resp.status_code in (400, 404):
                # Address not found on chain = empty balance (normal for new wallets)
                return {"status": "ok", "address": address, "ada": 0.0, "djed": 0.0}
            if resp.status_code != 200:
                return {"status": "error", "error": f"Blockfrost: {resp.status_code}"}

            data = resp.json()

            ada_amount = sum(
                int(amt["quantity"]) for amt in data.get("amount", [])
                if amt["unit"] == "lovelace"
            ) / 1_000_000

            # Find DJED balance
            djed_amount = 0.0
            for amt in data.get("amount", []):
                if "DJED" in amt.get("unit", ""):
                    djed_amount = int(amt["quantity"]) / 1_000_000

            return {
                "status": "ok",
                "address": address,
                "ada": ada_amount,
                "djed": djed_amount,
            }
    except Exception as e:
        return {"status": "error", "error": str(e)}