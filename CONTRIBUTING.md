# Contributing to RainMaker 🌧️

Thank you for your interest in RainMaker! We're building the bridge between feature phones and Cardano.

## Getting Started

1. Fork the repo
2. Clone your fork
3. Create a branch: `git checkout -b feature/your-feature`
4. Install dependencies: `pip install -r requirements.txt`
5. Copy `.env.example` to `.env` and configure

## Development Workflow

```bash
# Run tests
python3 -m pytest tests/

# Run the server
python3 -m uvicorn main:app --reload

# Simulate USSD
curl -X POST "http://localhost:8000/ussd/callback" \
  -d "sessionId=test" \
  -d "serviceCode=*384*225533#" \
  -d "phoneNumber=254712345678" \
  -d "text="
```

## Code Style

- **Python**: PEP 8, type hints encouraged
- **USSD handlers**: Keep responses under 160 characters
- **Security**: Never log seeds, PINs, or private keys
- **i18n**: USSD menus support Arabic; add new languages in `ussd_handler.py`

## Commit Messages

Conventional commits:

```
feat: add M-Pesa ramp integration
fix: handle empty address book lookup
docs: update API reference
security: upgrade bcrypt rounds to 14
```

## What We Need

| Area | Priority |
|------|----------|
| 🇰🇪 Kenya M-Pesa integration | 🔴 High |
| 🌍 Country-specific USSD menus | 🟡 Medium |
| 🧪 Integration tests | 🟡 Medium |
| 📱 SMS templates for edge cases | 🟢 Low |
| 🎨 USSD UI/UX improvements | 🟢 Low |

## Security

- **NEVER** commit `.env` files
- **NEVER** log PINs or seed phrases
- Report vulnerabilities to: security@rainmaker.dj
- We follow responsible disclosure

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
