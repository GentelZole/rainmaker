# RainMaker 🌧️

> **USSD-to-Cardano Bridge for Feature Phones**  
> Send DJED by phone number — no internet, no wallet app, no blockchain knowledge.  

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![Cardano Preprod](https://img.shields.io/badge/Cardano-Preprod-blueviolet)](https://preprod.cardanoscan.io/)

---

## 🧠 What is RainMaker?

**RainMaker turns any feature phone into a Cardano wallet.**  

Callers dial `*384*225533#`, register with a 4-digit PIN, and instantly get a Cardano wallet. All they need to send money is the **recipient's phone number** — RainMaker resolves it to a Cardano address behind the scenes.

| 🌍 Focus | 💱 Token | 📱 Interface | ⛓️ Blockchain |
|----------|----------|--------------|--------------|
| Africa-first (Kenya → 54 nations) | DJED stablecoin | USSD (every phone) | Cardano Preprod |

---

## ✨ Features

- **📞 Phone-as-Wallet** — Phone number IS your wallet address  
- **🔐 PIN Security** — bcrypt hashing + 24h lockout after 5 wrong attempts  
- **🌱 Auto-Generated Wallets** — HD wallet with 12-word seed phrase (encrypted AES-256-GCM)  
- **📨 SMS Delivery** — Wallet credentials sent via SMS after registration  
- **📖 Address Book** — 3-tier resolution: Phone → $Handle → Full Cardano address  
- **🛡️ Rate Limiting** — 30 requests/minute per phone number  
- **🧭 Guided UX** — Back options at every step + Help menu  
- **💰 Minimal Fees** — $0.10 per transfer  

---

## 🏗️ Architecture

<p align="center">
  <a href="docs/architecture.html">
    <img src="docs/architecture.png" alt="RainMaker Architecture" width="800">
  </a>
</p>

**[📊 Interactive Architecture Diagram →](docs/architecture.html)**

| Layer | Technology |
|-------|-----------|
| **USSD Gateway** | Africa's Talking API |
| **SMS Notifications** | Africa's Talking Messaging |
| **Backend Server** | FastAPI (Python) + uvicorn |
| **Database** | SQLite (PostgreSQL in production) |
| **Blockchain** | Cardano Preprod via Blockfrost |
| **Wallet Manager** | pycardano HD Wallet (CIP-1852) |
| **Reverse Proxy** | nginx + Let's Encrypt SSL |
| **DNS** | DuckDNS (dynamic → static domain) |
| **Security** | bcrypt PIN hashing, AES-256-GCM seed encryption |

---

## 🚀 Quick Start

### 1. Clone & Install

```bash
git clone https://github.com/GentelZole/rainmaker.git
cd rainmaker

# Python 3.11+ required
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure

Copy `.env.example` to `.env` and fill in your keys:

```bash
cp .env.example .env
```

Required environment variables:

| Key | Description |
|-----|------------|
| `AT_USERNAME` | Africa's Talking username (sandbox for testing) |
| `AT_API_KEY` | Africa's Talking API key |
| `BLOCKFROST_PROJECT_ID` | Blockfrost project ID (preprod recommended) |
| `CARDANO_NETWORK` | `preprod` or `mainnet` |

### 3. Run

```bash
# Development
python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# Production (behind nginx)
gunicorn -w 4 -k uvicorn.workers.UvicornWorker main:app
```

### 4. Expose USSD Callback

Africa's Talking needs a public HTTPS endpoint. We use nginx + DuckDNS:

```nginx
# /etc/nginx/sites-available/default
location /ussd/callback {
    proxy_pass http://127.0.0.1:8000/ussd/callback;
}
```

Set your Africa's Talking USSD channel callback URL to:
```
https://your-domain.duckdns.org/ussd/callback
```

### 5. Test

```bash
# Simulate USSD session from Africa's Talking
curl -X POST "http://localhost:8000/ussd/callback" \
  -d "sessionId=test1" \
  -d "serviceCode=*384*225533#" \
  -d "phoneNumber=254712345678" \
  -d "text="

# Should respond: CON 🌧️ RainMaker
#                   1. Send DJED
#                   2. My Wallet
#                   3. Register 🔐
#                   4. Help ❓
#                   0. Exit
```

---

## 📋 USSD Menu Flow

```
🌧️ RainMaker
├─ 1. Send DJED ─── Enter receiver's phone ─── Amount ─── PIN ─── ✅ Sent!
├─ 2. My Wallet ─── Balance + Address (guides to register if new)
├─ 3. Register 🔐 ── PIN ─── Confirm PIN ─── 🎉 Wallet created + SMS
├─ 4. Help ❓ ────── Usage guide
└─ 0. Exit
```

[Back (`0`) option available at every step]

---

## 🔒 Security

| Concern | Solution |
|---------|----------|
| PIN storage | **bcrypt** with 12 rounds — GPU-resistant |
| Seed phrase at rest | **AES-256-GCM** encrypted with PIN-derived key (PBKDF2, 600K iterations) |
| Brute-force PIN | **5 max attempts**, then 24-hour lockout |
| USSD spam | **Rate limiter** — 30 requests/minute per phone number |
| Man-in-the-middle | HTTPS-only via Let's Encrypt + nginx |
| Request verification | Africa's Talking origin IP validation (production) |

### Threat Model

1. **Feature phone stolen** → PIN required for sends, seed phrase encrypted  
2. **SMS interception** → SMS is best-effort; full seed also shown on USSD  
3. **SIM swap** → PIN protects wallet; KYC planned for high-value accounts  
4. **Blockfrost compromise** → Only public data exposed; private keys never stored on Blockfrost  

---

## 📁 Project Structure

```
rainmaker/
├── main.py              # FastAPI app + rate limiter
├── ussd_handler.py      # USSD menu logic (all flows)
├── wallet_manager.py    # HD wallet creation + PIN mgmt
├── cardano_tx.py        # Cardano transaction builder
├── address_book.py      # Phone ↔ Address resolution
├── sms_service.py       # Africa's Talking SMS sender
├── models.py            # SQLAlchemy models (User, Transaction, AddressBook)
├── config.py            # Pydantic settings (loads .env)
├── requirements.txt     # Python dependencies
├── .env.example         # Environment template
├── rainmaker.db         # SQLite database
├── docs/
│   └── architecture.html  # Interactive architecture diagram
└── LOG.md               # Development log
```

---

## 🗺️ Roadmap

- [x] USSD-to-Cardano bridge (MVP)
- [x] Phone-number-as-wallet
- [x] Auto-generated HD wallets
- [x] SMS wallet delivery
- [x] PIN-based security (bcrypt + AES-256-GCM)
- [x] Address book (phone → address resolution)
- [x] Rate limiting
- [ ] **Q3 2026:** DJED mainnet support
- [ ] **Q3 2026:** $handle resolution ($tarig.monaffal)
- [ ] **Q4 2026:** KYC integration (tiered limits: $10 → $100 → $500)
- [ ] **Q4 2026:** PostgreSQL migration
- [ ] **2027:** Rwanda, Tanzania, Uganda
- [ ] **2027:** On/off-ramp via M-Pesa
- [ ] **2027:** 54 African nations

---

## 🤝 Contributing

RainMaker is open source under MIT license. Areas where contributions are welcome:

- **Multi-country phone number formats** (currently Kenya `254`-prefixed)
- **Additional African languages** for USSD menus
- **On/off-ramp integrations** (M-Pesa, Airtel Money, MTN)
- **Cardano mainnet hardening**
- **Security audits** (penetration testing reports welcome)

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

---

## ⚠️ Disclaimer

RainMaker is in **active development** on Cardano Preprod. Not yet deployed to mainnet. Seed phrases are sent via SMS — this is a deliberate MVP trade-off for feature phone users who cannot back up data. In production, recovery will be USSD-based with encrypted storage.

---

<sub>Built with ❤️ by [TariQ](https://github.com/GentelZole) for the unbanked billions. 🌍</sub>
