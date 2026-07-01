"""
🌧️ RainMaker — USSD-to-Cardano Bridge
FastAPI application serving Africa's Talking USSD callbacks.
"""
import logging
import time
import threading
from collections import defaultdict
from fastapi import FastAPI, Form, Request, HTTPException
from fastapi.responses import PlainTextResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from ussd_handler import handle_ussd
from models import get_session, Base, get_engine
from config import get_settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("rainmaker")

# ==================== Rate Limiter ====================
class RateLimiter:
    """Simple in-memory sliding window rate limiter per phone number"""
    def __init__(self, max_requests: int = 30, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._buckets: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def is_allowed(self, key: str) -> tuple[bool, int]:
        """
        Check if key is allowed. Returns (allowed, remaining).
        Key is typically a phone number.
        """
        now = time.time()
        cutoff = now - self.window_seconds

        with self._lock:
            bucket = self._buckets[key]
            # Remove old timestamps
            bucket[:] = [t for t in bucket if t > cutoff]

            remaining = self.max_requests - len(bucket)

            if len(bucket) >= self.max_requests:
                return False, 0

            bucket.append(now)
            return True, remaining

    def cleanup(self):
        """Periodic cleanup of stale buckets (call from background task)"""
        now = time.time()
        cutoff = now - self.window_seconds
        with self._lock:
            stale = [k for k, v in self._buckets.items() if not any(t > cutoff for t in v)]
            for k in stale:
                del self._buckets[k]


rate_limiter = RateLimiter(max_requests=30, window_seconds=60)

app = FastAPI(title="RainMaker", version="0.1.0")

# Create DB tables on startup
@app.on_event("startup")
async def startup():
    engine = get_engine()
    Base.metadata.create_all(engine)
    logger.info("✅ Database initialized")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "RainMaker", "version": "0.1.0"}


# ==================== USSD Callback (Africa's Talking) ====================

@app.post("/ussd/callback", response_class=PlainTextResponse)
async def ussd_callback(
    request: Request,
    sessionId: str = Form(...),
    serviceCode: str = Form(...),
    phoneNumber: str = Form(...),
    text: str = Form(""),
):
    """
    Africa's Talking USSD callback.
    
    Receives POST with form data:
      - sessionId: unique session identifier
      - serviceCode: the USSD code dialed
      - phoneNumber: caller's number
      - text: user input (empty on first call, *-separated on subsequent)
    
    Returns CON <text> to continue session, or END <text> to terminate.
    Response must be text/plain and arrive within 10 seconds.
    """
    logger.info(f"📞 USSD Callback | session={sessionId[:12]}... | phone={phoneNumber} | text='{text}'")

    # Rate limit per phone number (30 req/min)
    allowed, remaining = rate_limiter.is_allowed(phoneNumber)
    if not allowed:
        logger.warning(f"🚫 Rate limit exceeded for {phoneNumber}")
        return "END ⏳ Too many requests. Please wait."

    try:
        response = handle_ussd(sessionId, phoneNumber, text)
        logger.info(f"📤 Response: {response[:80]}...")
        return response
    except Exception as e:
        logger.exception("❌ USSD handler error")
        return "END ❌ System error. Please try again."


# ==================== Web Dashboard ====================

@app.get("/", response_class=HTMLResponse)
async def index():
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>🌧️ RainMaker — Bridge</title>
        <style>
            body { font-family: system-ui, sans-serif; background: #050505; color: #fff;
                   display: flex; align-items: center; justify-content: center; 
                   min-height: 100vh; margin: 0; text-align: center; }
            .card { background: #111; border: 1px solid #1e1e1e; border-radius: 16px;
                    padding: 48px; max-width: 500px; }
            h1 { font-size: 32px; margin-bottom: 8px; }
            h1 span { background: linear-gradient(135deg, #3b82f6, #06b6d4);
                      -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
            .status { display: inline-block; padding: 4px 12px; background: rgba(16,185,129,0.15);
                      border: 1px solid rgba(16,185,129,0.3); border-radius: 9999px;
                      font-size: 12px; color: #10b981; margin: 16px 0; }
            p { color: #a1a1aa; font-size: 14px; line-height: 1.6; }
        </style>
    </head>
    <body>
        <div class="card">
            <div style="font-size:48px; margin-bottom:16px;">🌧️</div>
            <h1>Rain<span>Maker</span></h1>
            <div class="status">✅ Server Running</div>
            <p>USSD-to-Cardano Bridge<br>Feature Phone → Any Cardano Wallet</p>
            <p style="font-size:12px; color:#52525b; margin-top:24px;">
                📞 USSD Callback: /ussd/callback<br>
                🔗 <a href="/docs" style="color:#3b82f6;">API Docs</a>
            </p>
        </div>
    </body>
    </html>
    """


if __name__ == "__main__":
    import uvicorn
    settings = get_settings()
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)