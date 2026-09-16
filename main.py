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

CONFIG_FILE = "bot_saved_state.json"
import json

def load_saved_config():
    # 1. Controlla file di stato salvato
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                data = json.load(f)
                if data.get("api_key") and data.get("secret_key"):
                    bot.configure(data["api_key"], data["secret_key"], is_testnet=data.get("is_testnet", True))
                    bot.update_params(data)
                    bot.start()
                    return
        except Exception as e:
            print("Errore caricamento stato:", e)

    # 2. Fallback da env o credenziali fornite
    initial_key = os.getenv("BYBIT_API_KEY") or "2Zmj37uQYcUK8m7Gf4"
    initial_secret = os.getenv("BYBIT_SECRET_KEY") or "dshsZak0DaNhghLJ9DpaG4141hkccOL7rrNv"
    is_testnet = os.getenv("BYBIT_TESTNET", "true").lower() == "true"
    if initial_key and initial_secret:
        bot.configure(initial_key, initial_secret, is_testnet=is_testnet)
        bot.start()

load_saved_config()

def save_config(data: dict):
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(data, f)
    except Exception as e:
        print("Errore salvataggio config:", e)

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
    save_config(req.model_dump(exclude_unset=True))
    if not bot.is_running:
        try:
            bot.start()
        except Exception:
            pass
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
