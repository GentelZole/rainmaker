# 🌧️ RainMaker — Complete Project Log

> **USSD-to-Cardano Bridge** | Feature Phone → Cardano Wallet  
> Last updated: 2026-06-29

---

## 1. Project Overview

**RainMaker** is a USSD-based mobile application that lets anyone with a **feature phone** (any phone that can dial USSD codes, e.g. `*384*XXX#`) send and receive **DJED** (a Cardano stablecoin) and **ADA**. It bridges the gap between the unbanked (1.7B people without smartphones) and the Cardano blockchain.

### Core Capabilities

| Capability | Description |
|---|---|
| **Register** | User enters a Cardano address, creates a PIN, gets a 12-word HD wallet generated and seed phrase encrypted with their PIN using AES-256-GCM |
| **Send DJED** | Enter recipient phone number → amount → PIN → transaction submitted on Cardano Preprod Testnet |
| **Wallet Info** | Check ADA and DJED balance on the linked Cardano address via Blockfrost |
| **Address Resolution** | 3-tier: phone number → $handle (stub) → full Cardano address |

### Technical Stack

- **Runtime**: Python 3.11, FastAPI (0.115+), Uvicorn
- **Blockchain**: pycardano, Blockfrost API (Preprod Testnet)
- **Database**: SQLite (SQLAlchemy ORM)
- **Encryption**: PBKDF2 + AES-256-GCM (AESGCM from `cryptography`), SHA-256 PIN hashing
- **USSD Gateway**: Africa's Talking USSD API (outbound from AT → FastAPI callback)
- **Network**: nginx reverse proxy → FastAPI on port 8000

---

## 2. Architecture Diagram (ASCII)

```
┌─────────────────────────────────────────────────────────────────────┐
│                        END USER (Feature Phone)                      │
│                    Dial *384*XXX# on any phone                       │
└────────────────────────┬────────────────────────────────────────────┘
                         │ USSD session
                         ▼
┌─────────────────────────────────────────────────────────────────────┐
│                   Africa's Talking USSD Gateway                      │
│               (Africa's Talking infrastructure)                      │
│                                                                      │
│  ┌──────────── USSD Flow ────────────┐                              │
│  │  1. User dials *384*XXX#          │                              │
│  │  2. AT sends POST /ussd/callback  │                              │
│  │  3. Server responds CON/END       │                              │
│  │  4. AT displays response on phone │                              │
│  └───────────────────────────────────┘                              │
└────────────────────────┬────────────────────────────────────────────┘
                         │ POST /ussd/callback
                         │ Form data: sessionId, serviceCode,
                         │ phoneNumber, text
                         ▼
┌─────────────────────────────────────────────────────────────────────┐
│                   🔒 NGINX (Reverse Proxy)                          │
│               /ussd/callback → localhost:8000                       │
│               / → localhost:8000                                    │
│               /health → localhost:8000                              │
└────────────────────────┬────────────────────────────────────────────┘
                         │ proxy_pass http://127.0.0.1:8000
                         ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    🌧️ RainMaker (FastAPI)                           │
│                    localhost:8000 (uvicorn)                         │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ main.py       FastAPI app, routes, startup                   │  │
│  │                POST /ussd/callback → handle_ussd()           │  │
│  │                GET  /health                                  │  │
│  │                GET  / (dashboard HTML)                       │  │
│  └──────────┬───────────────────────────────────────────────────┘  │
│             │                                                       │
│  ┌──────────▼───────────────────────────────────────────────────┐  │
│  │ ussd_handler.py   USSD menu state machine                   │  │
│  │                   Parse text= parts, build CON/END response  │  │
│  │                   Max 160 chars per menu screen              │  │
│  └──────────┬───────────────────────────────────────────────────┘  │
│             │                                                       │
│  ┌──────────▼──────────┐  ┌────────────▼──────────────┐           │
│  │  wallet_manager.py  │  │   address_book.py          │          │
│  │  - create_wallet()  │  │   - lookup_by_phone()      │          │
│  │  - get_wallet_for_  │  │   - register_phone()       │          │
│  │    send()            │  │   - resolve_destination()  │          │
│  │  - encrypt_seed()   │  │   (3-tier resolution)      │          │
│  │  - decrypt_seed()   │  └────────┬───────────────────┘          │
│  │  - hash_pin()       │           │                              │
│  │  - verify_pin()     │           │                              │
│  └──────────┬──────────┘           │                              │
│             │                      │                              │
│  ┌──────────▼──────────────────────▼───────────────────────────┐  │
│  │              cardano_tx.py                                   │  │
│  │  - build_and_submit_tx(sender_seed, sender_addr,             │  │
│  │                         recipient_addr, amount_djed) → dict  │  │
│  │  - get_balance(address) → dict                               │  │
│  └──────────────────────────────────────────────────────────────┘  │
│             │                                                       │
│  ┌──────────▼───────────────────────────────────────────────────┐  │
│  │              models.py (SQLAlchemy DB schema)                │  │
│  │  User | AddressBook | Transaction                            │  │
│  │  DB: rainmaker.db (SQLite)                                   │  │
│  └──────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    ☁️ Blockfrost API                                 │
│  https://cardano-preprod.blockfrost.io/api/v0/                     │
│  - Submit transactions                                              │
│  - Query balances                                                   │
│  - Check network status                                             │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 3. File-by-File Documentation

### 3.1 `main.py` — FastAPI Application Entry Point

**Purpose**: The HTTP server. Creates the FastAPI app, registers routes, initializes the database on startup, and serves the USSD callback endpoint, health check, and a web dashboard.

**Public API**:

| Route | Method | Description |
|---|---|---|
| `/ussd/callback` | POST | Africa's Talking USSD callback. Accepts form data (`sessionId`, `serviceCode`, `phoneNumber`, `text`). Returns `CON ...` or `END ...` plaintext. |
| `/health` | GET | Returns JSON `{"status": "ok", "service": "RainMaker", "version": "0.1.0"}` |
| `/` | GET | Returns an HTML dashboard page with server status and links |
| `/docs` | GET | FastAPI auto-generated OpenAPI/Swagger docs |

**Startup Behavior**:
- Creates database engine and all tables (`Base.metadata.create_all(engine)`)
- Logs "✅ Database initialized"

**Key code pattern**:
```python
@app.post("/ussd/callback", response_class=PlainTextResponse)
async def ussd_callback(request, sessionId, serviceCode, phoneNumber, text=""):
    response = handle_ussd(sessionId, phoneNumber, text)
    return response
```

---

### 3.2 `ussd_handler.py` — USSD Menu State Machine

**Purpose**: Processes Africa's Talking USSD sessions. This is the core logic that interprets user inputs (separated by `*`) and returns menu text with `CON` (continue session) or `END` (terminate) prefix.

**Public API**:

| Function | Signature | Description |
|---|---|---|
| `handle_ussd` | `(session_id: str, phone_number: str, text: str) → str` | Main entry point. Routes based on `text` split by `*`. Returns a `CON ...` or `END ...` response. |
| `_build_menu` | `(text: str, is_end: bool = False) → str` | Wraps text with `CON ` or `END ` prefix. Truncates to ~155 chars (under the 160-char USSD limit). |

**Menu Structure (text parsing logic)**:

```
text=""              → Main menu (Level 0)
text="1"             → Send flow: enter recipient
text="1*254712345..." → Send flow: recipient entered, ask amount
text="1*254712345...*10"    → Send flow: amount entered, ask PIN
text="1*254712345...*10*1234" → Send flow: PIN entered, confirm & submit TX
text="2"             → My Wallet: show balance
text="3"             → Register: enter Cardano address
text="3*addr1..."     → Register: address entered, ask PIN
text="3*addr1...*1234" → Register: PIN entered, create wallet
```

**Flow handlers**:

| Function | Description |
|---|---|
| `_main_menu()` | Builds the root menu: "Send DJED / My Wallet / Register" |
| `_handle_main_menu(option, phone)` | Routes option 1→Send, 2→Wallet, 3→Register |
| `_handle_send_flow(parts, phone)` | Multi-step send: recipient → amount → PIN → submit |
| `_handle_register_flow(parts, phone)` | Multi-step register: address → PIN → create wallet |

**KYC Limits** enforced in send flow:

| KYC Level | Daily Send Limit |
|---|---|
| 0 (default) | $10 |
| 1 | $100 |
| 2 | $500 |

---

### 3.3 `address_book.py` — Address Resolution Engine

**Purpose**: Maps phone numbers to Cardano addresses. Implements a 3-tier resolution strategy. Also manages the `address_book` database table.

**Public API**:

| Function | Signature | Description |
|---|---|---|
| `lookup_by_phone` | `(phone_number: str) → dict or None` | Query `address_book` table by phone number. Returns address, stake_address, display_name, kyc_level, is_verified. |
| `register_phone` | `(phone_number, cardano_address, stake_address=None, handle_name=None, owner_user_id=None) → dict` | Create or update a phone↔address mapping in the DB. |
| `resolve_destination` | `(input_str: str) → dict` | **3-tier resolution** — the primary entry point for looking up a send destination. |

**3-Tier Resolution Algorithm** (`resolve_destination`):

```
Input string
    │
    ├─ isdigit() and len ≥ 10
    │   └─ Tier 1: Phone number lookup
    │       ├─ Found in DB → return {type: "phone", address, ...}
    │       └─ Not found → return {type: "unregistered", error}
    │
    ├─ starts with "$"
    │   └─ Tier 2: ADA Handle (post-MVP stub)
    │       └─ return {type: "handle_stub", error: "coming soon"}
    │
    ├─ starts with "addr" or "addr_test"
    │   └─ Tier 3: Full Cardano address
    │       └─ return {type: "full_address", address, display_name}
    │
    └─ else
        └─ return {type: "unknown", error}
```

---

### 3.4 `wallet_manager.py` — HD Wallet Generation & PIN Security

**Purpose**: Creates Cardano HD wallets (BIP-39), encrypts seed phrases with user PINs, handles PIN verification with lockout after 5 failed attempts.

**Public API**:

| Function | Signature | Description |
|---|---|---|
| `encrypt_seed` | `(seed_phrase: str, pin: str) → str` | Encrypts seed phrase with PBKDF2-derived AES-256-GCM key. Returns `salt_hex:nonce_hex:ciphertext_hex`. |
| `decrypt_seed` | `(encrypted: str, pin: str) → str or None` | Decrypts seed. Returns `None` on wrong PIN or corruption. |
| `hash_pin` | `(pin: str) → (hash: str, salt: str)` | SHA-256 hash with salt. Returns `(hash, salt)`. |
| `verify_pin` | `(pin: str, stored_hash: str, salt: str) → bool` | Verifies PIN against stored hash. |
| `create_wallet` | `(phone_number: str, pin: str) → dict` | Generates HD wallet, encrypts seed with PIN, stores in DB. Returns `{status, phone_number, cardano_address, seed_phrase}`. |
| `get_wallet_for_send` | `(phone_number: str, pin: str) → dict or None` | Retrieves and decrypts wallet for sending. Handles PIN attempts and lockout. Returns `{status, seed_phrase, ...}`. |

**Encryption Details**:
- **Algorithm**: PBKDF2-HMAC-SHA256 (600,000 iterations) → AES-256-GCM
- **Output format**: `salt:nonce:ciphertext` (all hex-encoded)
- **Seed phrase**: 12-word BIP-39 mnemonic
- **Key derivation path**: `m/1852'/1815'/0'/0/0` (CIP-1852)

**PIN Security**:
- PIN hashed with SHA-256 + random salt
- Stored as `salt:hash` in `users.pin_hash`
- Max 5 attempts before 24-hour lockout
- PIN minimum length: 4 digits (configurable)

---

### 3.5 `cardano_tx.py` — Blockchain Transaction Builder

**Purpose**: Builds, signs, and submits Cardano transactions using pycardano. Queries balances via Blockfrost API.

**Public API**:

| Function | Signature | Description |
|---|---|---|
| `build_and_submit_tx` | `(sender_seed: str, sender_address: str, recipient_address: str, amount_djed: float) → dict` | Builds a Cardano transaction from the sender's seed phrase. Currently sends ADA lovelace (testnet placeholder). Returns `{status, tx_hash, amount, token, recipient}`. |
| `get_balance` | `(address: str) → dict` | Queries Blockfrost for ADA and DJED balance at a given address. Returns `{status, address, ada: float, djed: float}`. |

**Transaction Details**:
- **Network**: Preprod Testnet (configurable to mainnet)
- **Current token sent**: ADA (lovelace) — DJED sending is stubbed pending testnet DJED policy ID confirmation
- **Min ADA**: 2,000,000 lovelace (2 ADA)
- **Fee**: $0.10 DJED (hardcoded in USD, applied in business logic)
- **Signing**: Uses pycardano `TransactionBuilder.build_and_sign()` with the sender's signing key derived from seed

**Blockfrost Integration**:
- Context: `BlockFrostChainContext(project_id, network)`
- Balance: `GET https://cardano-{network}.blockfrost.io/api/v0/addresses/{address}`

---

### 3.6 `models.py` — SQLAlchemy ORM Models

**Purpose**: Defines the database schema and provides database connection utilities.

**Public API**:

| Function/Class | Description |
|---|---|
| `Base` | SQLAlchemy `declarative_base()` instance |
| `User` | ORM class for `users` table |
| `AddressBook` | ORM class for `address_book` table |
| `Transaction` | ORM class for `transactions` table |
| `get_engine()` | Creates SQLAlchemy engine from `DATABASE_URL` setting. Handles SQLite-specific `check_same_thread`. |
| `get_session()` | Creates all tables and returns a new session. |

---

### 3.7 `config.py` — Pydantic Settings

**Purpose**: Central configuration loaded from environment variables (`.env` file or system env). Uses Pydantic's `BaseSettings` for validation.

**Configuration Fields**:

| Variable | Default | Description |
|---|---|---|
| `AT_USERNAME` | `"sandbox"` | Africa's Talking API username |
| `AT_API_KEY` | `""` | Africa's Talking API key |
| `BLOCKFROST_PROJECT_ID` | `""` | Blockfrost project ID (for preprod) |
| `CARDANO_NETWORK` | `"preprod"` | `preprod` or `mainnet` |
| `SECRET_KEY` | `"change-me-in-production"` | App secret key |
| `DATABASE_URL` | `"sqlite+aiosqlite:///./rainmaker.db"` | Database URL (SQLite for dev) |
| `USSD_SHORT_CODE` | `"*384*000#"` | USSD short code users dial |
| `PIN_MIN_LENGTH` | `4` | Minimum PIN digits |
| `PIN_MAX_ATTEMPTS` | `5` | PIN attempts before lockout |
| `PIN_LOCKOUT_MINUTES` | `1440` | Lockout duration (24h) |

**Public API**:

| Function | Signature | Description |
|---|---|---|
| `get_settings()` | `() → Settings` | Returns cached `Settings` singleton (LRU cached) |

---

### 3.8 `requirements.txt` — Python Dependencies

```
fastapi>=0.115.0         # Web framework
uvicorn[standard]>=0.32.0  # ASGI server
pycardano>=0.12.0        # Cardano blockchain library (HD wallet, tx building)
blockfrost>=0.6.0        # Blockfrost API client
pydantic>=2.0            # Settings validation
python-dotenv>=1.0       # .env file loading
cryptography>=42.0       # AES-256-GCM encryption
httpx>=0.27.0            # HTTP client (for Blockfrost queries)
aiosqlite>=0.20.0        # Async SQLite driver (for FastAPI async compatibility)
```

---

### 3.9 `.env.example` — Environment Template

Detailed in Section 6 below.

---

## 4. USSD Callback Flow (Complete ASCII Sequence)

```
┌──────┐          ┌──────────────┐          ┌──────────┐          ┌──────────┐          ┌───────────┐
│ User │          │  Feature     │          │  Africa's │          │  NGINX   │          │  FastAPI  │
│Phone  │          │  Phone       │          │  Talking  │          │  (proxy) │          │  (Port    │
│      │          │              │          │  Gateway  │          │          │          │   8000)   │
└──┬───┘          └──────────────┘          └─────┬─────┘          └─────┬────┘          └─────┬────┘
   │                                                     │                      │                      │
   │  1. Dial *384*XXX#                                  │                      │                      │
   │─────────────────────────────────►                   │                      │                      │
   │                                                     │                      │                      │
   │                                                     │  2. POST /ussd/callback                      │
   │                                                     │     sessionId=abc                             │
   │                                                     │     serviceCode=*384*XXX#                    │
   │                                                     │     phoneNumber=254712345678                  │
   │                                                     │     text=""                                  │
   │                                                     │──────────────────────────────────────────────►│
   │                                                     │                      │                      │
   │                                                     │                      │   3. handle_ussd()    │
   │                                                     │                      │     → text=""         │
   │                                                     │                      │     → _main_menu()    │
   │                                                     │                      │                      │
   │                                                     │  4. "CON 🌧️ RainMaker│                      │
   │                                                     │        1. Send DJED  │                      │
   │                                                     │        2. My Wallet  │                      │
   │                                                     │        3. Register"  │                      │
   │                                                     │◄─────────────────────────────────────────────┤
   │                                                     │                      │                      │
   │  5. Display menu on phone                           │                      │                      │
   │◄────────────────────────────────────────────────────│                      │                      │
   │                                                     │                      │                      │
   │  6. User replies "1" (Send DJED)                    │                      │                      │
   │─────────────────────────────────►                   │                      │                      │
   │                                                     │  7. POST /ussd/callback                      │
   │                                                     │     text="1"                                 │
   │                                                     │──────────────────────────────────────────────►│
   │                                                     │                      │                      │
   │                                                     │                      │   8. handle_ussd()    │
   │                                                     │                      │     → parts=["1"]     │
   │                                                     │                      │     → _handle_main_   │
   │                                                     │                      │       menu("1",...)   │
   │                                                     │  9. "CON 📤 Enter    │                      │
   │                                                     │      recipient phone│                      │
   │                                                     │      number:"       │                      │
   │                                                     │◄─────────────────────────────────────────────┤
   │                                                     │                      │                      │
   │ 10. Display "Enter recipient"                       │                      │                      │
   │◄────────────────────────────────────────────────────│                      │                      │
   │                                                     │                      │                      │
   │ 11. User enters "254712345678"                      │                      │                      │
   │─────────────────────────────────►                   │                      │                      │
   │                                                     │ 12. POST /ussd/callback                      │
   │                                                     │    text="1*254712345678"                     │
   │                                                     │──────────────────────────────────────────────►│
   │                                                     │                      │                      │
   │                                                     │                      │ 13. resolve_destination│
   │                                                     │                      │     ("254712345678") │
   │                                                     │                      │     → address_book   │
   │                                                     │ 14. "CON 📤 Recipient:│                      │
   │                                                     │     Alice            │                      │
   │                                                     │     Enter amount     │                      │
   │                                                     │     (DJED):"         │                      │
   │                                                     │◄─────────────────────────────────────────────┤
   │                                                     │                      │                      │
   │ 15. Display "Enter amount"                          │                      │                      │
   │◄────────────────────────────────────────────────────│                      │                      │
   │                                                     │                      │                      │
   │ 16. User enters "10"                                │                      │                      │
   │─────────────────────────────────►                   │                      │                      │
   │                                                     │ 17. POST /ussd/callback                      │
   │                                                     │    text="1*254712345678*10"                   │
   │                                                     │──────────────────────────────────────────────►│
   │                                                     │                      │                      │
   │                                                     │ 18. "CON 🔐 Enter    │                      │
   │                                                     │     your 4-digit PIN:│                      │
   │                                                     │◄─────────────────────────────────────────────┤
   │                                                     │                      │                      │
   │ 19. Display "Enter PIN"                             │                      │                      │
   │◄────────────────────────────────────────────────────│                      │                      │
   │                                                     │                      │                      │
   │ 20. User enters "1234"                              │                      │                      │
   │─────────────────────────────────►                   │                      │                      │
   │                                                     │ 21. POST /ussd/callback                      │
   │                                                     │text="1*254712345678*10*1234"                 │
   │                                                     │──────────────────────────────────────────────►│
   │                                                     │                      │                      │
   │                                                     │                      │ 22. get_wallet_for_   │
   │                                                     │                      │     send(phone, "1234")│
   │                                                     │                      │ 23. build_and_submit_  │
   │                                                     │                      │     tx(...)            │
   │                                                     │                      │ 24. Blockfrost submit │
   │                                                     │ 25. "END ✅ Sent 10  │                      │
   │                                                     │     DJED             │                      │
   │                                                     │     To: Alice        │                      │
   │                                                     │     Fee: $0.10       │                      │
   │                                                     │     Tx: abc123..."   │                      │
   │                                                     │◄─────────────────────────────────────────────┤
   │                                                     │                      │                      │
   │ 26. Display final result on phone                   │                      │                      │
   │◄────────────────────────────────────────────────────│                      │                      │
   │                                                     │                      │                      │
   │                     SESSION ENDS                                                    │
```

---

## 5. Database Schema

### 5.1 `users` Table

```ascii
┌─────────────────┬──────────────┬──────────────────────────────────────────┐
│ Column          │ Type         │ Notes                                    │
├─────────────────┼──────────────┼──────────────────────────────────────────┤
│ id              │ VARCHAR(36)  │ UUID primary key                          │
│ phone_number    │ VARCHAR(20)  │ UNIQUE, NOT NULL, INDEXED                │
│ cardano_address │ VARCHAR(255) │ NOT NULL — user's Cardano wallet address │
│ stake_address   │ VARCHAR(255) │ NULLABLE — staking key address           │
│ encrypted_seed  │ TEXT         │ NULLABLE — AES-256-GCM encrypted seed    │
│ pin_hash        │ VARCHAR(128) │ NULLABLE — "salt:sha256_hash"            │
│ handle_name     │ VARCHAR(64)  │ NULLABLE — optional alias                │
│ kyc_level       │ INTEGER      │ DEFAULT 0 — 0, 1, or 2                  │
│ is_active       │ BOOLEAN      │ DEFAULT TRUE                             │
│ pin_attempts    │ INTEGER      │ DEFAULT 0 — failed PIN count             │
│ locked_until    │ DATETIME     │ NULLABLE — PIN lockout timestamp         │
│ created_at      │ DATETIME     │ DEFAULT now()                            │
│ updated_at      │ DATETIME     │ DEFAULT now(), on update now()           │
└─────────────────┴──────────────┴──────────────────────────────────────────┘
```

### 5.2 `address_book` Table

```ascii
┌─────────────────┬──────────────┬──────────────────────────────────────────┐
│ Column          │ Type         │ Notes                                    │
├─────────────────┼──────────────┼──────────────────────────────────────────┤
│ id              │ VARCHAR(36)  │ UUID primary key                          │
│ phone_number    │ VARCHAR(20)  │ UNIQUE, NOT NULL, INDEXED                │
│ cardano_address │ VARCHAR(255) │ NOT NULL — resolved Cardano address      │
│ stake_address   │ VARCHAR(255) │ NULLABLE                                 │
│ handle_name     │ VARCHAR(64)  │ NULLABLE — alias/nickname                │
│ owner_user_id   │ VARCHAR(36)  │ FK → users.id, NULLABLE                  │
│ is_verified     │ BOOLEAN      │ DEFAULT FALSE                            │
│ kyc_level       │ INTEGER      │ DEFAULT 0                                │
│ created_at      │ DATETIME     │ DEFAULT now()                            │
│ updated_at      │ DATETIME     │ DEFAULT now(), on update now()           │
└─────────────────┴──────────────┴──────────────────────────────────────────┘
```

### 5.3 `transactions` Table

```ascii
┌──────────────────┬──────────────┬──────────────────────────────────────────┐
│ Column           │ Type         │ Notes                                    │
├──────────────────┼──────────────┼──────────────────────────────────────────┤
│ id               │ VARCHAR(36)  │ UUID primary key                          │
│ sender_phone     │ VARCHAR(20)  │ NOT NULL, INDEXED                        │
│ recipient_input  │ VARCHAR(255) │ NOT NULL — what the user typed           │
│ resolved_address │ VARCHAR(255) │ NULLABLE — the resolved Cardano address  │
│ resolution_type  │ VARCHAR(20)  │ DEFAULT 'phone' — phone/handle/full_addr │
│ amount           │ FLOAT        │ NOT NULL — amount sent                   │
│ token            │ VARCHAR(20)  │ DEFAULT 'DJED'                           │
│ cardano_tx_hash  │ VARCHAR(128) │ NULLABLE — on-chain transaction hash     │
│ fee_djed         │ FLOAT        │ DEFAULT 0.10                             │
│ status           │ VARCHAR(20)  │ DEFAULT 'pending' — pending/confirmed/   │
│                  │              │                    failed                 │
│ error_message    │ TEXT         │ NULLABLE — failure reason                │
│ created_at       │ DATETIME     │ DEFAULT now()                            │
│ confirmed_at     │ DATETIME     │ NULLABLE — when confirmed on-chain       │
└──────────────────┴──────────────┴──────────────────────────────────────────┘
```

### 5.4 Entity Relationship

```
┌─────────┐          ┌─────────────┐          ┌──────────────┐
│  User   │          │ AddressBook │          │ Transaction  │
├─────────┤          ├─────────────┤          ├──────────────┤
│ id (PK) │──┬──────►│ owner_user_id (FK)     │ sender_phone │
│ phone   │  │       │ phone_number │          │ (indexed)    │
│ address │  │       │ address      │          │ recipient    │
│ seed*   │  │       └─────────────┘          │ amount       │
│ pin*    │  │                                │ tx_hash      │
└─────────┘  │                                └──────────────┘
             │
             └── Each User typically has one AddressBook entry
                 (self-registration creates both)
```

---

## 6. How to Set Up and Run

### 6.1 Prerequisites

- Python 3.11+
- An **Africa's Talking** account (sandbox is free) → https://africastalking.com
- A **Blockfrost** account (free tier for preprod) → https://blockfrost.io
- A domain or public IP (for AT callback registration)

### 6.2 Environment Setup

```bash
# Clone the project
cd /home/moe/rainmaker

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
```

### 6.3 Environment Variables (`.env`)

```bash
# Africa's Talking — from your AT dashboard
AT_USERNAME=sandbox              # Your AT username (usually "sandbox" for sandbox)
AT_API_KEY=your_sandbox_api_key  # From AT dashboard → API Keys

# Cardano (Preprod Testnet) — from your Blockfrost dashboard
BLOCKFROST_PROJECT_ID=preprod_YOUR_BLOCKFROST_KEY_HERE  # Create a "Preprod" project
CARDANO_NETWORK=preprod          # Change to "mainnet" for production

# App
SECRET_KEY=generate-a-random-secret-key  # Use: python3 -c "import secrets; print(secrets.token_urlsafe(32))"
DATABASE_URL=sqlite+aiosqlite:///./rainmaker.db
USSD_SHORT_CODE=*384*000#        # Your AT-registered USSD code
```

### 6.4 Running the Server

```bash
# Development (with auto-reload)
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Production
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

### 6.5 Africa's Talking USSD Configuration

1. Log in to [Africa's Talking Dashboard](https://account.africastalking.com)
2. Go to **USSD** → **Create Channel**
3. Set the USSD code (e.g. `*384*000#`)
4. Set callback URL: `https://your-domain.com/ussd/callback`
5. Choose **Application** mode (default)
6. Save and activate

> **Important**: Africa's Talking sends `POST` requests with `Content-Type: application/x-www-form-urlencoded`. The server must respond within **10 seconds** with plain text starting with `CON ` (continue) or `END ` (terminate).

### 6.6 Verifying It Works

```bash
# Health check
curl https://your-domain.com/health
# Expected: {"status":"ok","service":"RainMaker","version":"0.1.0"}
```

---

## 7. How to Test (curl Commands for USSD Simulation)

Since you can't actually dial USSD from a terminal, simulate Africa's Talking callbacks with curl. Each "step" below represents one user input in a USSD session.

### 7.1 Main Menu (first dial — text is empty)

```bash
curl -X POST http://localhost:8000/ussd/callback \
  -d "sessionId=test123" \
  -d "serviceCode=*384*000#" \
  -d "phoneNumber=254712345678" \
  -d "text="
```

**Expected response**:
```
CON 🌧️ RainMaker
1. Send DJED
2. My Wallet
3. Register
```

### 7.2 Select "Register" (option 3)

```bash
curl -X POST http://localhost:8000/ussd/callback \
  -d "sessionId=test123" \
  -d "serviceCode=*384*000#" \
  -d "phoneNumber=254712345678" \
  -d "text=3"
```

**Expected response**:
```
CON 📝 Enter your Cardano address
(wallet addr1... or addr_test1...):
```

### 7.3 Enter Cardano Address

```bash
curl -X POST http://localhost:8000/ussd/callback \
  -d "sessionId=test123" \
  -d "serviceCode=*384*000#" \
  -d "phoneNumber=254712345678" \
  -d "text=3*addr_test1qzl8qxfmhug46vz3vmj4a0q6q3a0x8k5z5v5z5v5z5v5z5v5z5v5z5v5z5v5z5v5z5"
```

**Expected response**:
```
CON 🔐 Create a 4-digit PIN
(keep it safe!):
```

### 7.4 Enter PIN to Complete Registration

```bash
curl -X POST http://localhost:8000/ussd/callback \
  -d "sessionId=test123" \
  -d "serviceCode=*384*000#" \
  -d "phoneNumber=254712345678" \
  -d "text=3*addr_test1qzl8qxfmhug46vz3vmj4a0q6q3a0x8k5z5v5z5v5z5v5z5v5z5v5z5v5z5v5z5v5z5*1234"
```

**Expected response** (`END` — session terminates):
```
END ✅ Registered!
☂️ Your RainMaker: 254712345678
🔗 Address: addr_test1qzl...
⚠️ Your seed phrase:
abandon ability able about above absent absorb abstract absurd abuse access
✍️ WRITE THIS DOWN!
```

### 7.5 Check Wallet (option 2)

```bash
curl -X POST http://localhost:8000/ussd/callback \
  -d "sessionId=test456" \
  -d "serviceCode=*384*000#" \
  -d "phoneNumber=254712345678" \
  -d "text=2"
```

**Expected response** (with real Blockfrost data):
```
CON 💰 Wallet
ADA: 0.00
DJED: 0.00
addr_test1qz...
1. Send again
0. Back
```

### 7.6 Send DJED Flow (full sequence)

```bash
# Step 1: Select "Send DJED" (option 1)
curl -X POST http://localhost:8000/ussd/callback \
  -d "sessionId=test789" \
  -d "serviceCode=*384*000#" \
  -d "phoneNumber=254712345678" \
  -d "text=1"

# Step 2: Enter recipient (must already be registered in address book)
curl -X POST http://localhost:8000/ussd/callback \
  -d "sessionId=test789" \
  -d "serviceCode=*384*000#" \
  -d "phoneNumber=254712345678" \
  -d "text=1*254798765432"

# Step 3: Enter amount
curl -X POST http://localhost:8000/ussd/callback \
  -d "sessionId=test789" \
  -d "serviceCode=*384*000#" \
  -d "phoneNumber=254712345678" \
  -d "text=1*254798765432*10"

# Step 4: Enter PIN and submit
curl -X POST http://localhost:8000/ussd/callback \
  -d "sessionId=test789" \
  -d "serviceCode=*384*000#" \
  -d "phoneNumber=254712345678" \
  -d "text=1*254798765432*10*1234"
```

### 7.7 Testing with Unregistered Recipient

```bash
curl -X POST http://localhost:8000/ussd/callback \
  -d "sessionId=test999" \
  -d "serviceCode=*384*000#" \
  -d "phoneNumber=254712345678" \
  -d "text=1*254700000000"
```

**Expected response**:
```
CON ⚠️ Ask recipient to register first, or use their Cardano address
Try another number:
```

### 7.8 Testing with a Full Cardano Address (bypassing address book)

```bash
curl -X POST http://localhost:8000/ussd/callback \
  -d "sessionId=test888" \
  -d "serviceCode=*384*000#" \
  -d "phoneNumber=254712345678" \
  -d "text=1*addr_test1qzl8qxfmhug46vz3vmj4a0q6q3a0x8k5z5v5z5v5z5v5z5v5z5v5z5v5z5v5z5v5z5"
```

**Expected response**:
```
CON 📤 Recipient: addr_test1qz...
Enter amount (DJED):
```

### 7.9 Health Check

```bash
curl http://localhost:8000/health
# {"status":"ok","service":"RainMaker","version":"0.1.0"}
```

---

## 8. Deployed URLs and Locations

| Component | URL | Notes |
|---|---|---|
| **FastAPI App** | `http://localhost:8000` | Uvicorn on port 8000 |
| **API Docs** | `http://localhost:8000/docs` | Swagger UI (OpenAPI) |
| **Health** | `http://localhost:8000/health` | Health check endpoint |
| **Web Dashboard** | `http://localhost:8000` | HTML status page |
| **USSD Callback** | `POST http://localhost:8000/ussd/callback` | Africa's Talking endpoint |
| **Blockfrost API** | `https://cardano-preprod.blockfrost.io/api/v0/` | Cardano Preprod Testnet |
| **Database** | `/home/moe/rainmaker/rainmaker.db` | SQLite database file |

> **Production deployment**: Behind an nginx reverse proxy at `https://your-domain.com/ussd/callback`. Update Africa's Talking callback URL to point to the production domain.

---

## 9. Network Topology

```
                               INTERNET
                                  │
                    ┌─────────────▼────────────────┐
                    │   Africa's Talking USSD       │
                    │   Gateway                     │
                    │   (Cloud Infrastructure)      │
                    │                               │
                    │   POST /ussd/callback          │
                    │   Content-Type:               │
                    │   application/x-www-form-     │
                    │   urlencoded                  │
                    │                               │
                    │   Fields:                     │
                    │   • sessionId                 │
                    │   • serviceCode               │
                    │   • phoneNumber               │
                    │   • text                      │
                    └─────────────┬─────────────────┘
                                  │ HTTPS (443)
                                  │
                    ┌─────────────▼─────────────────┐
                    │   INTERNET / PUBLIC NETWORK    │
                    │                                │
                    │   DNS: your-domain.com          │
                    │   Firewall: 443 (HTTPS) only   │
                    └─────────────┬──────────────────┘
                                  │
                    ┌─────────────▼─────────────────┐
                    │   🔒 NGINX Reverse Proxy       │
                    │   Port 443 → 80                │
                    │   /ussd/callback → 8000        │
                    │   /health → 8000               │
                    │   / → 8000                     │
                    │   SSL termination (Let's       │
                    │   Encrypt / certbot)            │
                    └─────────────┬──────────────────┘
                                  │ localhost:8000
                    ┌─────────────▼─────────────────┐
                    │   UVICORN (ASGI Server)        │
                    │   Port 8000                    │
                    │   Workers: 4 (recommended)     │
                    │                                │
                    │   Process: main:app             │
                    └─────────────┬──────────────────┘
                                  │
                    ┌─────────────▼─────────────────┐
                    │   🌧️ RainMaker FastAPI App    │
                    │   Python 3.11                   │
                    │                                │
                    │   Routes:                      │
                    │   POST /ussd/callback          │
                    │   GET  /health                  │
                    │   GET  /                        │
                    │   GET  /docs (Swagger)         │
                    │                                │
                    │   → ussd_handler.handle_ussd()  │
                    │   → wallet_manager              │
                    │   → address_book                │
                    │   → cardano_tx                  │
                    └─────────────┬──────────────────┘
                                  │
                    ┌─────────────▼─────────────────┐
                    │   SQLite Database              │
                    │   rainmaker.db                 │
                    │   Tables: users, address_book, │
                    │            transactions        │
                    └─────────────┬──────────────────┘
                                  │
                    ┌─────────────▼─────────────────┐
                    │   ☁️ Blockfrost API            │
                    │   External service              │
                    │   cardano-preprod.blockfrost.io│
                    │                                │
                    │   /api/v0/addresses/{addr}     │
                    │   /api/v0/tx/submit            │
                    └────────────────────────────────┘
```

**Request Lifecycle**:

```
1. Phone ←→ Mobile Network (USSD)
2. Mobile Network ←→ Africa's Talking Gateway
3. Africa's Talking POST → https://your-domain.com/ussd/callback
4. DNS resolves → Server IP → NGINX (port 443)
5. NGINX terminates SSL → proxies to localhost:8000
6. FastAPI receives form data → handle_ussd()
7. handle_ussd() processes text → builds response
8. Response "CON ..." or "END ..." returned plain text
9. NGINX proxies response back to Africa's Talking
10. Africa's Talking sends response to phone display
11. If "CON", user replies → repeat from step 1
12. If "END", session terminates
```

---

## 10. Pitfalls and Known Issues

### 10.1 Critical Issues

| # | Issue | Impact | Workaround |
|---|---|---|---|
| 1 | **DJED policy ID not confirmed** — `cardano_tx.py` line 49 uses `"test_djed_policy_id"` placeholder | Sends ADA (lovelace) instead of DJED tokens | Update with real testnet DJED policy ID before mainnet launch |
| 2 | **PIN hashing uses SHA-256, not Argon2** — `wallet_manager.py` uses SHA-256 for speed (USSD 10s timeout). The `pin_hash` column comment says Argon2 but implementation differs. | Weaker hashing than intended | Acceptable for USSD latency constraints; upgrade to Argon2 if latency allows |
| 3 | **USSD 10-second timeout** — Africa's Talking waits max 10s for callback response | Blockfrost API calls can be slow, causing timeout | Implement in-memory session cache to avoid DB queries on every step; add timeout middleware |
| 4 | **SQLite concurrency** — SQLite `check_same_thread=False` with multiple uvicorn workers | Race conditions on DB writes under load | Switch to PostgreSQL for production; use single worker or `--workers 1` for SQLite |

### 10.2 Configuration Issues

| # | Issue | Detail |
|---|---|---|
| 5 | **`.env.example` variable names don't match `config.py`** | `.env.example` uses `AT_USERNAME` / `AT_API_KEY` / `BLOCKFROST_PROJECT_ID` but `Settings` class expects `at_username` / `at_api_key` / `blockfrost_project_id`. **Pydantic v2 converts env vars to lowercase automatically** so `AT_USERNAME` → `at_username` works. But it's confusing. |
| 6 | **`SECRET_KEY` unused** — The secret key is defined but never used anywhere in the application | No impact currently, but should be used for session signing or encryption |
| 7 | **`USSD_SHORT_CODE` not used** — The short code is defined in config but never referenced in the code | Informational only |

### 10.3 USSD Handler Issues

| # | Issue | Detail |
|---|---|---|
| 8 | **No session state persistence** — The handler is stateless; it re-parses `text` each time | Works correctly because AT sends concatenated text, but makes complex multi-page menus harder to implement |
| 9 | **160-char USSD limit** — `_build_menu` truncates at ~155 chars | Messages longer than this are silently cut off. The seed phrase display during registration is often truncated! |
| 10 | **Seed phrase shown on phone screen** — Registration displays the 12-word seed phrase in the USSD response | **Security risk**: seed phrase is visible on the phone screen and potentially logged. Users are told "Write this down" but it's ephemeral. |
| 11 | **No confirmation step before sending** — User enters PIN and the transaction is submitted immediately | Users could accidentally send to wrong recipient. Consider a confirmation step. |
| 12 | **Recipient validation is ephemeral** — The recipient is resolved at two different points (step 2 and step 4). If the address book changes between steps, the wrong address could be used. | Low probability, but should resolve once and cache in session. |

### 10.4 Security Issues

| # | Issue | Detail |
|---|---|---|
| 13 | **Seed phrase returned in `create_wallet` response** — The seed phrase is returned to the USSD handler and displayed on screen | Consider showing only first/last 4 words or requiring the user to call support |
| 14 | **No rate limiting** — No protection against brute-force PIN attempts via automated curl calls | The 5-attempt lockout per user is the only protection. Add IP-based rate limiting. |
| 15 | **No input sanitization beyond basic validation** — Only checks `isdigit()` and `startswith("addr")` | Potential for injection in edge cases |
| 16 | **No transaction confirmation on-chain verification** — The app trusts Blockfrost's submit response without verifying the transaction was actually included in a block | Add confirmation polling |

### 10.5 Development/Testing Issues

| # | Issue | Detail |
|---|---|---|
| 17 | **`requirements.txt` has no version pins** — All dependencies use `>=` bounds | Builds may break on new major releases. Pin to tested versions. |
| 18 | **No test suite** — No pytest or unit tests exist | Manual curl testing only. Add tests for `handle_ussd` parsing, `resolve_destination` tiers, and `encrypt_seed`/`decrypt_seed` roundtrip. |
| 19 | **`get_balance()` accepts either phone or address** — The function parameter is named `address` but `ussd_handler.py` calls it with `phone_number` | Works because `get_balance` makes a Blockfrost call; it'll fail with `Blockfrost: 404` when passed a phone number. Actually this is **buggy** — `wallet` option passes phone_number, Blockfrost expects an address. |

### 10.6 Infrastructure Issues

| # | Issue | Detail |
|---|---|---|
| 20 | **No TLS in development** — App runs on HTTP port 8000 | Africa's Talking requires HTTPS callback URLs. Use nginx + Let's Encrypt or ngrok for testing. |
| 21 | **No monitoring/logging infrastructure** — Only stdout logging with `logging.INFO` | No structured logging, no metrics, no alerting |
| 22 | **No database migration system** — Tables are created via `Base.metadata.create_all()` | Schema changes require manual migration or table drop |
| 23 | **No CI/CD pipeline** — No Dockerfile, no compose file, no deployment scripts | All deployment is manual |

---

## Appendix: Quick Reference

### Key File Paths

```
/home/moe/rainmaker/
├── main.py              # FastAPI app, routes, startup
├── ussd_handler.py      # USSD menu state machine
├── address_book.py      # Phone → Cardano address resolution
├── wallet_manager.py    # HD wallet generation, PIN encryption
├── cardano_tx.py        # Cardano transaction builder (pycardano)
├── models.py            # SQLAlchemy models and DB connection
├── config.py            # Pydantic Settings (env vars)
├── requirements.txt     # Python dependencies
├── .env.example         # Environment variable template
├── .env                 # Actual secrets (gitignored)
├── rainmaker.db         # SQLite database (gitignored)
├── LOG.md               # This file
└── venv/                # Python virtual environment (gitignored)
```

### Debugging Checklist

- [ ] Is the server running? `curl http://localhost:8000/health`
- [ ] Are env vars set? `source venv/bin/activate && python3 -c "from config import get_settings; s=get_settings(); print(s.blockfrost_project_id[:10])"`
- [ ] Is the database created? `ls -la /home/moe/rainmaker/rainmaker.db`
- [ ] Is Blockfrost responding? `curl -H "project_id: $BLOCKFROST_PROJECT_ID" https://cardano-preprod.blockfrost.io/api/v0/`
- [ ] Can AT reach the callback? `curl -X POST https://your-domain.com/ussd/callback -d "sessionId=debug&serviceCode=*384*000#&phoneNumber=254700000000&text="`
- [ ] NGINX logs: `sudo tail -f /var/log/nginx/access.log`
- [ ] App logs: `tail -f /home/moe/rainmaker/venv/bin/uvicorn` (or check systemd journal)

---

*End of RainMaker LOG.md — Generated 2026-06-29 by Hermes Agent*
