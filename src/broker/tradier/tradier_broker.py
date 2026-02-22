"""Tradier broker implementation using the Tradier REST API."""

import logging
from datetime import datetime, timedelta
from typing import List, Optional

import requests

from ..broker import Broker
from ..models import Allocation

logger = logging.getLogger(__name__)


class TradierBroker(Broker):
    """Tradier broker implementation using the REST API via requests."""

    def __init__(self, access_token: str, account_id: str, base_url: str):
        self.account_id = account_id
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        })
        is_sandbox = "sandbox" in base_url
        logger.info(f"Initialized Tradier broker (sandbox={is_sandbox})")

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def get_current_allocation(self) -> List[Allocation]:
        """Get current portfolio allocation from Tradier."""
        try:
            resp = self.session.get(
                self._url(f"/v1/accounts/{self.account_id}/positions")
            )
            resp.raise_for_status()
            data = resp.json()

            positions_data = data.get("positions", {})
            if positions_data == "null" or not positions_data:
                logger.info("No positions found in Tradier account")
                return []

            positions = positions_data.get("position", [])
            if isinstance(positions, dict):
                positions = [positions]

            allocations = []
            for pos in positions:
                quantity = float(pos.get("quantity", 0))
                cost_basis = float(pos.get("cost_basis", 0))
                symbol = pos.get("symbol", "")

                if quantity <= 0 or not symbol:
                    continue

                quote_price = self._get_quote(symbol)
                market_value = quantity * quote_price

                allocations.append(Allocation(
                    symbol=symbol,
                    quantity=quantity,
                    current_price=quote_price,
                    market_value=market_value,
                ))

            logger.info(f"Retrieved {len(allocations)} positions from Tradier")
            return allocations
        except Exception as e:
            logger.error(f"Error getting positions from Tradier: {e}")
            raise

    def sell(self, symbol: str, quantity: float, tag: Optional[str] = None) -> bool:
        """Sell a stock via Tradier."""
        try:
            payload = {
                "class": "equity",
                "symbol": symbol,
                "side": "sell",
                "quantity": quantity,
                "type": "market",
                "duration": "day",
            }
            if tag:
                payload["tag"] = tag
            resp = self.session.post(
                self._url(f"/v1/accounts/{self.account_id}/orders"),
                data=payload,
            )
            resp.raise_for_status()
            result = resp.json()

            order_info = result.get("order", {})
            order_id = order_info.get("id")
            status = order_info.get("status")

            if status == "ok" and order_id:
                logger.info(f"Sold {quantity} shares of {symbol}. Order ID: {order_id}")
                return True

            logger.error(f"Tradier sell order rejected for {symbol}: {result}")
            return False
        except Exception as e:
            logger.error(f"Error selling {symbol}: {e}")
            return False

    def buy(self, symbol: str, amount: float, tag: Optional[str] = None) -> bool:
        """Buy a stock with a specific dollar amount via Tradier."""
        try:
            price = self._get_quote(symbol)
            if price <= 0:
                logger.error(f"Invalid price for {symbol}")
                return False

            quantity = round(amount / price, 6)
            if quantity <= 0:
                logger.error(f"Calculated quantity for {symbol} is zero or negative")
                return False

            payload = {
                "class": "equity",
                "symbol": symbol,
                "side": "buy",
                "quantity": quantity,
                "type": "market",
                "duration": "day",
            }
            if tag:
                payload["tag"] = tag
            resp = self.session.post(
                self._url(f"/v1/accounts/{self.account_id}/orders"),
                data=payload,
            )
            resp.raise_for_status()
            result = resp.json()

            order_info = result.get("order", {})
            order_id = order_info.get("id")
            status = order_info.get("status")

            if status == "ok" and order_id:
                logger.info(f"Bought ${amount} worth of {symbol} ({quantity} shares). Order ID: {order_id}")
                return True

            logger.error(f"Tradier buy order rejected for {symbol}: {result}")
            return False
        except Exception as e:
            logger.error(f"Error buying {symbol}: {e}")
            return False

    def get_account_cash(self) -> float:
        """Get available cash in the Tradier account."""
        try:
            resp = self.session.get(
                self._url(f"/v1/accounts/{self.account_id}/balances")
            )
            resp.raise_for_status()
            data = resp.json()

            balances = data.get("balances", {})
            cash = balances.get("total_cash", balances.get("cash", {}).get("cash_available", 0))
            return float(cash)
        except Exception as e:
            logger.error(f"Error getting account cash from Tradier: {e}")
            raise

    def get_trade_history(self, since_days: int = 7) -> List[dict]:
        """Get trade history from Tradier."""
        try:
            resp = self.session.get(
                self._url(f"/v1/accounts/{self.account_id}/orders"),
                params={"limit": 500, "includeTags": "true"},
            )
            resp.raise_for_status()
            data = resp.json()

            orders_data = data.get("orders", {})
            if orders_data == "null" or not orders_data:
                return []

            orders = orders_data.get("order", [])
            if isinstance(orders, dict):
                orders = [orders]

            cutoff_date = datetime.now() - timedelta(days=since_days)
            trades = []

            for order in orders:
                if order.get("status") != "filled":
                    continue

                symbol = order.get("symbol")
                if not symbol:
                    continue

                side = order.get("side", "").upper()
                if side not in ("BUY", "SELL"):
                    continue

                exec_qty = float(order.get("exec_quantity", order.get("quantity", 0)))
                if exec_qty <= 0:
                    continue

                avg_price = float(order.get("avg_fill_price", 0))
                if avg_price <= 0:
                    continue

                timestamp_str = order.get("transaction_date") or order.get("create_date")
                if timestamp_str:
                    try:
                        timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                        if timestamp.tzinfo:
                            timestamp = timestamp.replace(tzinfo=None)
                        if timestamp < cutoff_date:
                            continue
                    except (ValueError, TypeError):
                        timestamp = datetime.now()
                else:
                    timestamp = datetime.now()

                trade_entry = {
                    "symbol": symbol,
                    "action": side,
                    "quantity": exec_qty,
                    "price": avg_price,
                    "total": exec_qty * avg_price,
                    "timestamp": timestamp,
                    "trade_id": str(order.get("id", "")),
                }
                order_tag = order.get("tag")
                if order_tag:
                    trade_entry["tag"] = order_tag
                trades.append(trade_entry)

            logger.info(f"Retrieved {len(trades)} filled orders from Tradier")
            return trades
        except Exception as e:
            logger.warning(f"Error getting trade history from Tradier: {e}")
            return []

    def _get_quote(self, symbol: str) -> float:
        """Fetch the last trade price for a symbol."""
        try:
            resp = self.session.get(
                self._url("/v1/markets/quotes"),
                params={"symbols": symbol, "greeks": "false"},
            )
            resp.raise_for_status()
            data = resp.json()

            quotes = data.get("quotes", {})
            quote = quotes.get("quote", {})
            if isinstance(quote, list):
                quote = quote[0] if quote else {}

            return float(quote.get("last", 0))
        except Exception as e:
            logger.error(f"Error getting quote for {symbol}: {e}")
            return 0.0
