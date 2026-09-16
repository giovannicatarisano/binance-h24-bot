import os
from typing import Optional, Dict, Any
from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests
from trading_bot import UniversalTradingBot

app = FastAPI(title="Bybit & Crypto 24/7 Cloud Trading Bot API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SERVER_API_KEY = os.getenv("SERVER_SECRET_KEY", "binance_secret_token_1234")
bot = UniversalTradingBot()

# Caricamento iniziale se fornite via env
INITIAL_KEY = os.getenv("BYBIT_API_KEY") or os.getenv("BINANCE_API_KEY")
INITIAL_SECRET = os.getenv("BYBIT_SECRET_KEY") or os.getenv("BINANCE_SECRET_KEY")
IS_TESTNET = os.getenv("BYBIT_TESTNET", "true").lower() == "true"

if INITIAL_KEY and INITIAL_SECRET:
    bot.configure(INITIAL_KEY, INITIAL_SECRET, is_testnet=IS_TESTNET)

def verify_token(authorization: Optional[str] = Header(None)):
    if not authorization:
        raise HTTPException(status_code=401, detail="Token di autorizzazione mancante")
    token = authorization.replace("Bearer ", "").strip()
    if token != SERVER_API_KEY:
        raise HTTPException(status_code=403, detail="Token di autorizzazione non valido")
    return True

class ConfigRequest(BaseModel):
    api_key: Optional[str] = None
    secret_key: Optional[str] = None
    is_testnet: Optional[bool] = False
    symbol: Optional[str] = "BTC/USDT"
    strategy: Optional[str] = "dca"
    amount_usdt: Optional[float] = 25.0
    take_profit_pct: Optional[float] = 2.0
    dip_buy_pct: Optional[float] = 1.5
    grid_lower: Optional[float] = 50000.0
    grid_upper: Optional[float] = 70000.0
    grid_levels: Optional[int] = 5

@app.get("/")
def home():
    return {
        "service": "24/7 Cloud Trading Bot (Bybit & Demo Ready)",
        "status": "online",
        "bot_active": bot.is_running,
        "mode": "DEMO / TESTNET" if bot.is_testnet else "REAL / MAINNET"
    }

@app.get("/api/my-ip")
def get_my_ip():
    try:
        res = requests.get("https://api.ipify.org?format=json", timeout=5)
        ip = res.json().get("ip", "unknown")
        return {"outbound_ip": ip}
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/status", dependencies=[Depends(verify_token)])
def get_status():
    try:
        return bot.get_status()
    except Exception as e:
        import traceback
        trace = traceback.format_exc()
        return {"error": str(e), "trace": trace, "is_running": bot.is_running}

@app.get("/api/balances", dependencies=[Depends(verify_token)])
def get_balances():
    return bot.get_balances()

@app.get("/api/history", dependencies=[Depends(verify_token)])
def get_history():
    return bot.trade_history

@app.get("/api/logs", dependencies=[Depends(verify_token)])
def get_logs():
    return {"logs": bot.system_logs}

@app.post("/api/configure", dependencies=[Depends(verify_token)])
def configure_bot(req: ConfigRequest):
    if req.api_key and req.secret_key:
        bot.configure(req.api_key, req.secret_key, is_testnet=bool(req.is_testnet))
    
    bot.update_params(req.model_dump(exclude_unset=True))
    return {"status": "ok", "config": bot.get_status()}

@app.post("/api/start", dependencies=[Depends(verify_token)])
def start_bot():
    try:
        bot.start()
        return {"status": "started"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/stop", dependencies=[Depends(verify_token)])
def stop_bot():
    bot.stop()
    return {"status": "stopped"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
