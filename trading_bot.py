import time
import threading
import logging
from typing import Optional, Dict, Any, List
import ccxt

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("BybitTradingBot")

class UniversalTradingBot:
    def __init__(self):
        self.is_running = False
        self.thread: Optional[threading.Thread] = None
        self.exchange: Optional[ccxt.bybit] = None
        
        # Parametri di configurazione
        self.symbol = "BTC/USDT"
        self.strategy = "dca"  # 'dca' o 'grid'
        self.amount_usdt = 25.0
        self.take_profit_pct = 2.0
        self.dip_buy_pct = 1.5
        self.check_interval_sec = 10
        self.is_testnet = True  # Default su Demo/Testnet per sicurezza

        # Parametri Grid
        self.grid_lower = 50000.0
        self.grid_upper = 70000.0
        self.grid_levels = 5

        # Stato interno
        self.last_price = 0.0
        self.last_buy_price: Optional[float] = None
        self.accumulated_base = 0.0
        self.total_spent_usdt = 0.0
        self.trade_history: List[Dict[str, Any]] = []
        self.system_logs: List[str] = []

    def _log(self, msg: str):
        logger.info(msg)
        ts = time.strftime("%H:%M:%S")
        self.system_logs.insert(0, f"[{ts}] {msg}")
        if len(self.system_logs) > 50:
            self.system_logs.pop()

    def configure(self, api_key: str, secret_key: str, is_testnet: bool = False):
        was_running = self.is_running
        if self.is_running:
            self.stop()
            time.sleep(1)

        self.is_testnet = is_testnet
        
        # Inizializzazione Bybit V5 con supporto specifico Bybit EU e Testnet
        exchange_config = {
            'apiKey': api_key.strip(),
            'secret': secret_key.strip(),
            'enableRateLimit': True,
            'options': {
                'defaultType': 'spot',
                'adjustForTimeDifference': True,
            },
            'urls': {
                'api': {
                    'spot': 'https://api-testnet.bybit.eu' if is_testnet else 'https://api.bybit.eu',
                    'public': 'https://api-testnet.bybit.eu' if is_testnet else 'https://api.bybit.eu',
                    'private': 'https://api-testnet.bybit.eu' if is_testnet else 'https://api.bybit.eu',
                    'v5': 'https://api-testnet.bybit.eu/v5' if is_testnet else 'https://api.bybit.eu/v5',
                }
            }
        }
        
        self.exchange = ccxt.bybit(exchange_config)
        if is_testnet:
            self.exchange.set_sandbox_mode(True)
            # Assicura che gli endpoint v5 puntino a bybit.eu o testnet
            self.exchange.urls['api']['v5'] = 'https://api-testnet.bybit.eu/v5'
            self.exchange.urls['api']['spot'] = 'https://api-testnet.bybit.eu'
            self.exchange.urls['api']['public'] = 'https://api-testnet.bybit.eu'
            self.exchange.urls['api']['private'] = 'https://api-testnet.bybit.eu'
            
        self._log(f"Exchange Bybit EU configurato con successo (Testnet: {is_testnet})")
        
        if was_running:
            self.start()

    def update_params(self, params: Dict[str, Any]):
        if 'symbol' in params:
            raw_sym = params['symbol'].replace('/', '').upper()
            if not '/' in params['symbol'] and 'USDT' in raw_sym:
                self.symbol = raw_sym.replace('USDT', '/USDT')
            else:
                self.symbol = params['symbol'].upper()
                
        if 'strategy' in params:
            self.strategy = params['strategy']
        if 'amount_usdt' in params:
            self.amount_usdt = float(params['amount_usdt'])
        if 'take_profit_pct' in params:
            self.take_profit_pct = float(params['take_profit_pct'])
        if 'dip_buy_pct' in params:
            self.dip_buy_pct = float(params['dip_buy_pct'])
        if 'grid_lower' in params:
            self.grid_lower = float(params['grid_lower'])
        if 'grid_upper' in params:
            self.grid_upper = float(params['grid_upper'])
        if 'grid_levels' in params:
            self.grid_levels = int(params['grid_levels'])

    def start(self):
        if self.is_running:
            return
        if not self.exchange:
            raise ValueError("Chiavi API non configurate. Configura prima le credenziali.")
        
        self.is_running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        logger.info(f"Bot Bybit avviato per {self.symbol} - Strategia: {self.strategy.upper()} (Demo: {self.is_testnet})")

    def stop(self):
        self.is_running = False
        logger.info("Bot Bybit arrestato.")

    def get_status(self) -> Dict[str, Any]:
        avg_price = (self.total_spent_usdt / self.accumulated_base) if self.accumulated_base > 0 else 0.0
        return {
            "is_running": self.is_running,
            "exchange": "Bybit",
            "symbol": self.symbol,
            "strategy": self.strategy,
            "current_price": self.last_price,
            "last_buy_price": self.last_buy_price,
            "average_entry_price": avg_price,
            "accumulated_base": self.accumulated_base,
            "total_spent_usdt": self.total_spent_usdt,
            "amount_per_trade": self.amount_usdt,
            "take_profit_pct": self.take_profit_pct,
            "dip_buy_pct": self.dip_buy_pct,
            "is_testnet": self.is_testnet,
            "account_mode": "DEMO (Testnet)" if self.is_testnet else "REALE (Mainnet)",
        }

    def get_balances(self) -> List[Dict[str, Any]]:
        if not self.exchange:
            return []
        try:
            balance = self.exchange.fetch_balance()
            total = balance.get('total', {})
            free = balance.get('free', {})
            results = []
            for asset, qty in total.items():
                if qty and qty > 0:
                    results.append({
                        "asset": asset,
                        "free": free.get(asset, 0.0),
                        "total": qty,
                    })
            return results
        except Exception as e:
            logger.error(f"Errore recupero saldi Bybit: {e}")
            return []

    def _run_loop(self):
        self._log(f"Caricamento mercati Bybit EU...")
        try:
            self.exchange.load_markets()
            self._log(f"Mercati caricati ({len(self.exchange.markets)} coppie disponibili).")
        except Exception as e:
            self._log(f"Avviso load_markets: {e}")

        # Trova il simbolo corrispondente esatto nei mercati Bybit EU
        symbol_to_use = None
        for candidate in [self.symbol, self.symbol.replace('/', ''), f"{self.symbol}:USDT", "BTC/USDT:USDT", "BTC/EUR", "BTC/USDC"]:
            if candidate in self.exchange.markets:
                symbol_to_use = candidate
                break

        if not symbol_to_use:
            # Prendi la prima coppia BTC disponibile
            btc_markets = [m for m in self.exchange.markets.keys() if 'BTC' in m]
            self._log(f"Mercati BTC trovati: {btc_markets[:5]}")
            symbol_to_use = btc_markets[0] if btc_markets else list(self.exchange.markets.keys())[0]

        self.active_symbol = symbol_to_use
        self._log(f"Loop di trading avviato per {symbol_to_use}...")
        while self.is_running:
            try:
                ticker = self.exchange.fetch_ticker(symbol_to_use)
                self.last_price = float(ticker['last'])
                self._log(f"Prezzo {symbol_to_use}: ${self.last_price}")

                if self.strategy == "dca":
                    self._evaluate_dca(self.last_price)
                elif self.strategy == "grid":
                    self._evaluate_grid(self.last_price)

            except Exception as e:
                self._log(f"Errore ciclo trading: {e}")

            time.sleep(self.check_interval_sec)

    def _evaluate_dca(self, price: float):
        # 1. Take Profit
        if self.accumulated_base > 0:
            avg_entry = self.total_spent_usdt / self.accumulated_base
            profit_pct = ((price - avg_entry) / avg_entry) * 100.0
            if profit_pct >= self.take_profit_pct:
                logger.info(f"Target Take Profit raggiunto (+{profit_pct:.2f}%). Vendita...")
                self._execute_order("sell", self.accumulated_base, price, f"Take Profit (+{profit_pct:.2f}%)")
                self.accumulated_base = 0.0
                self.total_spent_usdt = 0.0
                self.last_buy_price = None
                return

        # 2. Buy Condition (Primo acquisto o Ritracciamento)
        should_buy = False
        reason = ""
        if self.last_buy_price is None:
            should_buy = True
            reason = "Primo acquisto DCA"
        else:
            dip = ((self.last_buy_price - price) / self.last_buy_price) * 100.0
            if dip >= self.dip_buy_pct:
                should_buy = True
                reason = f"Acquisto su ritracciamento (-{dip:.2f}%)"

        if should_buy:
            qty = self.amount_usdt / price
            # Arrotonda la quantità alla precisione corretta
            target_sym = getattr(self, 'active_symbol', self.symbol)
            market = self.exchange.markets.get(target_sym, {})
            min_amount = market.get('limits', {}).get('amount', {}).get('min', 0.0001)
            if qty < min_amount:
                qty = min_amount
            qty_formatted = float(self.exchange.amount_to_precision(target_sym, qty))
            self._execute_order("buy", qty_formatted, price, reason)
            self.last_buy_price = price
            self.accumulated_base += qty_formatted
            self.total_spent_usdt += self.amount_usdt

    def _evaluate_grid(self, price: float):
        if price < self.grid_lower or price > self.grid_upper:
            return
        step = (self.grid_upper - self.grid_lower) / self.grid_levels
        if self.last_buy_price is None:
            qty = self.amount_usdt / price
            self._execute_order("buy", qty, price, "Inizializzazione Grid")
            self.last_buy_price = price
            self.accumulated_base += qty
            self.total_spent_usdt += self.amount_usdt
        else:
            diff = price - self.last_buy_price
            if diff >= step and self.accumulated_base > 0:
                qty_sell = self.accumulated_base / self.grid_levels
                self._execute_order("sell", qty_sell, price, "Uscita livello Grid")
                self.last_buy_price = price
                self.accumulated_base = max(0.0, self.accumulated_base - qty_sell)
            elif -diff >= step:
                qty_buy = self.amount_usdt / price
                self._execute_order("buy", qty_buy, price, "Entrata livello Grid")
                self.last_buy_price = price
                self.accumulated_base += qty_buy
                self.total_spent_usdt += self.amount_usdt

    def _execute_order(self, side: str, amount: float, price: float, note: str):
        target_sym = getattr(self, 'active_symbol', self.symbol)
        try:
            self._log(f"Esecuzione ordine {side.upper()} di {amount:.6f} {target_sym} @ ~${price}")
            order = self.exchange.create_market_order(target_sym, side, amount)
            log_item = {
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "symbol": target_sym,
                "side": side.upper(),
                "price": price,
                "amount": amount,
                "total_usdt": amount * price,
                "note": note,
                "order_id": order.get('id', 'N/A')
            }
            self.trade_history.insert(0, log_item)
            self._log(f"Ordine {side.upper()} eseguito con successo! ID: {order.get('id', 'N/A')}")
            if len(self.trade_history) > 100:
                self.trade_history.pop()
        except Exception as e:
            self._log(f"Fallimento ordine {side.upper()}: {e}")
