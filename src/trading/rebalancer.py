"""Portfolio rebalancing logic."""

import logging
from datetime import datetime
from typing import List, Optional, Dict, Any
from ..broker import Broker
from ..broker.models import Allocation, TradeSummary
from ..leaderboard import LeaderboardClient
from ..notifications import EmailNotifier

logger = logging.getLogger(__name__)


class Rebalancer:
    """Handles portfolio rebalancing based on leaderboard rankings."""
    
    def __init__(
        self,
        broker: Broker,
        leaderboard_client: LeaderboardClient,
        initial_capital: float,
        portfolio_name: str,
        index_id: str,
        stockcount: int = 5,
        slack: int = 0,
        email_notifier: Optional[EmailNotifier] = None,
        persistence_manager: Optional[object] = None,  # PersistenceManager type
    ):
        """
        Initialize rebalancer.

        Args:
            broker: Broker instance
            leaderboard_client: Leaderboard API client
            initial_capital: Initial capital for portfolio allocation
            portfolio_name: Portfolio name (e.g., "SP400", "SP500")
            index_id: Internal API index ID (e.g., "13", "9")
            stockcount: Number of stocks to hold in portfolio (default: 5)
            slack: Position buffer - sell when rank > stockcount + slack (default: 0)
            email_notifier: Optional email notifier
            persistence_manager: Optional persistence manager for trade tracking
        """
        self.broker = broker
        self.leaderboard_client = leaderboard_client
        self.initial_capital = initial_capital
        self.portfolio_name = portfolio_name
        self.index_id = index_id
        self.stockcount = stockcount
        self.slack = slack
        self.email_notifier = email_notifier
        self.persistence_manager = persistence_manager
        self._current_execution_run_id = None  # Set during rebalance()
    
    def rebalance(self, dry_run: bool = False, execution_run_id: Optional[str] = None) -> TradeSummary:
        """
        Execute portfolio rebalancing based on week-over-week leaderboard comparison.

        Args:
            dry_run: If True, print actions but don't execute trades. If False, execute trades normally.
            execution_run_id: Optional execution run ID for tracking trades.

        Returns:
            TradeSummary with details of executed trades (or simulated trades in dry-run mode)
        """
        self._current_execution_run_id = execution_run_id
        logger.info(f"[{self.portfolio_name}] Starting portfolio rebalancing (stockcount={self.stockcount}, slack={self.slack})")

        # Fetch current week leaderboard with ranks
        # Need to fetch stockcount + slack + buffer to see if current holdings dropped out
        fetch_count = self.stockcount + self.slack + 5  # Extra buffer for safety

        try:
            # Current week (week-1): previous Sunday
            current_week_mom_day = self.leaderboard_client._get_previous_sunday()
            current_week_data = self.leaderboard_client.get_symbols_with_ranks(
                top_n=fetch_count, mom_day=current_week_mom_day, index_id=self.index_id
            )

            # Build rank lookup: symbol -> rank
            current_ranks = {item['symbol']: item['rank'] for item in current_week_data}

            # Top N symbols to buy (within stockcount)
            current_week_symbols = [item['symbol'] for item in current_week_data[:self.stockcount]]
            logger.info(f"[{self.portfolio_name}] Current week top {self.stockcount}: {current_week_symbols}")

            # Previous week (week-2): Sunday from two weeks ago
            previous_week_mom_day = self.leaderboard_client._get_previous_week_sunday()
            previous_week_data = self.leaderboard_client.get_symbols_with_ranks(
                top_n=fetch_count, mom_day=previous_week_mom_day, index_id=self.index_id
            )
            previous_week_symbols = [item['symbol'] for item in previous_week_data[:self.stockcount]]
            logger.info(f"[{self.portfolio_name}] Previous week top {self.stockcount}: {previous_week_symbols}")
        except Exception as e:
            logger.error(f"Error fetching leaderboard: {e}")
            raise
        
        # Get current allocation
        try:
            all_allocations = self.broker.get_current_allocation()
            # Filter allocations to only include symbols owned by this portfolio for rebalancing logic
            current_allocations = self._filter_allocations_by_portfolio(all_allocations)
            current_symbols = {alloc.symbol.upper() for alloc in current_allocations}
            logger.info(f"[{self.portfolio_name}] Current positions: {current_symbols}")
        except Exception as e:
            logger.error(f"[{self.portfolio_name}] Error getting current allocation: {e}")
            raise
        
        # Reconcile with broker trade history if persistence is enabled
        if self.persistence_manager:
            try:
                # Get trade history from broker (last 7 days)
                broker_trades = self.broker.get_trade_history(since_days=7)
                if broker_trades:
                    logger.info(f"[{self.portfolio_name}] Reconciling {len(broker_trades)} broker trades with Firestore...")
                    reconciliation_result = self.persistence_manager.reconcile_with_broker_history(broker_trades)
                    logger.info(f"[{self.portfolio_name}] Reconciliation complete: {reconciliation_result['updated']} updated, "
                              f"{reconciliation_result['missing']} missing, "
                              f"{reconciliation_result['unfilled']} unfilled")
            except Exception as e:
                logger.warning(f"[{self.portfolio_name}] Error reconciling trade history: {e}")
                # Continue without reconciliation if there's an error
        
        # Detect external sales if persistence is enabled
        # Use all_allocations (unfiltered) for external sales detection to compare with DB ownership
        external_sale_proceeds = 0.0
        external_sales_by_symbol = {}  # Track external sales per symbol
        if self.persistence_manager:
            try:
                logger.info("Checking for external sales...")
                external_sales = self.persistence_manager.detect_external_sales(all_allocations, portfolio_name=self.portfolio_name)
                if external_sales:
                    logger.info(f"Detected {len(external_sales)} external sale(s)")
                    for sale in external_sales:
                        logger.info(f"  - {sale.symbol}: {sale.quantity} shares, ~${sale.estimated_proceeds:.2f}")
                        external_sales_by_symbol[sale.symbol.upper()] = sale
                    external_sale_proceeds = self.persistence_manager.get_unused_external_sale_proceeds(self.portfolio_name)
                    logger.info(f"Total unused external sale proceeds: ${external_sale_proceeds:.2f}")
            except Exception as e:
                logger.warning(f"Error detecting external sales: {e}")
                # Continue without persistence if there's an error
        
        # Normalize symbols to uppercase
        current_week_symbols_upper = [s.upper() for s in current_week_symbols]
        previous_week_symbols_upper = [s.upper() for s in previous_week_symbols]
        previous_week_symbols_set = {s.upper() for s in previous_week_symbols}
        
        # Check if any stocks from previous week's LB exist in current positions
        positions_from_prev_week = current_symbols & previous_week_symbols_set
        
        # Get cash balance
        try:
            cash_balance = self.broker.get_account_cash()
            logger.info(f"[{self.portfolio_name}] Current cash balance: ${cash_balance}")
        except Exception as e:
            logger.error(f"[{self.portfolio_name}] Error getting account cash: {e}")
            raise
        
        # Case 1: No stocks from previous week's LB exist and 10k cash balance exists
        # If persistence is enabled, also check if we have external sale proceeds
        available_capital = cash_balance + external_sale_proceeds
        if not positions_from_prev_week and available_capital >= 10000.0:
            capital_to_use = self.initial_capital + external_sale_proceeds
            logger.info(f"[{self.portfolio_name}] No stocks from previous week's LB exist and available capital >= $10k. Entering trades for top 5 stocks using ${capital_to_use:.2f} (initial_capital + external sale proceeds).")
            return self._initial_allocation(current_week_symbols_upper, capital_to_use, dry_run=dry_run)
        
        # Case 2: Compare leaderboards using rank-based logic with slack
        # Sell stocks that dropped below stockcount + slack threshold
        # Buy stocks that entered top stockcount
        logger.info(f"[{self.portfolio_name}] Comparing leaderboards and executing rebalancing...")
        return self._execute_week_over_week_rebalancing(
            current_allocations,
            current_week_symbols_upper,
            previous_week_symbols_upper,
            current_ranks=current_ranks,
            external_sale_proceeds=external_sale_proceeds,
            external_sales_by_symbol=external_sales_by_symbol,
            dry_run=dry_run
        )
    
    def _allocations_match(self, allocations: List[Allocation], target_symbols: List[str]) -> bool:
        """Check if current allocations match target symbols."""
        current_symbols = {alloc.symbol.upper() for alloc in allocations}
        target_set = {s.upper() for s in target_symbols}

        # Check if we have exactly the top stockcount symbols
        return current_symbols == target_set and len(current_symbols) == self.stockcount
    
    def _initial_allocation(self, symbols: List[str], amount: Optional[float] = None, dry_run: bool = False) -> TradeSummary:
        """
        Perform initial allocation when portfolio is empty.

        Args:
            symbols: List of symbols to buy
            amount: Amount to allocate. If None, uses initial_capital.
            dry_run: If True, print actions but don't execute trades.
        """
        # Use only top stockcount symbols
        symbols = symbols[:self.stockcount]

        buys = []
        failed_trades = []  # Track failed trades
        allocation_amount = amount if amount is not None else self.initial_capital
        # Round to 2 decimal places (Alpaca requires notional values to be limited to 2 decimal places)
        allocation_per_stock = round(allocation_amount / len(symbols), 2)
        
        if dry_run:
            logger.info(f"[{self.portfolio_name}] [DRY-RUN] Would divide ${allocation_amount} into {len(symbols)} stocks: ${allocation_per_stock} each")
        else:
            logger.info(f"[{self.portfolio_name}] Dividing ${allocation_amount} into {len(symbols)} stocks: ${allocation_per_stock} each")
        
        for symbol in symbols:
            if dry_run:
                buys.append({
                    "symbol": symbol,
                    "quantity": 0,  # Will be estimated
                    "cost": allocation_per_stock,
                    "status": "planned",
                    "error": None,
                    "order_id": None,
                })
                logger.info(f"[{self.portfolio_name}] [DRY-RUN] Would buy ${allocation_per_stock} of {symbol}")
            else:
                try:
                    success = self.broker.buy(symbol, allocation_per_stock)
                    # Try to get order ID if broker supports it
                    order_id = None
                    try:
                        if hasattr(self.broker, '_last_order_id'):
                            order_id = getattr(self.broker, '_last_order_id', None)
                    except:
                        pass
                    
                    if success:
                        buys.append({
                            "symbol": symbol,
                            "quantity": 0,  # Will be updated after getting positions
                            "cost": allocation_per_stock,
                            "status": "submitted",
                            "error": None,
                            "order_id": order_id,
                        })
                        logger.info(f"[{self.portfolio_name}] Bought ${allocation_per_stock} of {symbol}")
                        
                        # Record trade in persistence
                        if self.persistence_manager:
                            from ..persistence.models import TradeRecord
                            # Get price from updated allocations
                            try:
                                updated_allocations = self.broker.get_current_allocation()
                                current_price = next(
                                    (alloc.current_price for alloc in updated_allocations if alloc.symbol.upper() == symbol.upper()),
                                    allocation_per_stock
                                )
                            except:
                                current_price = allocation_per_stock
                            
                            trade = TradeRecord(
                                symbol=symbol,
                                action="BUY",
                                quantity=0,  # Will be updated below
                                price=current_price,
                                total=allocation_per_stock,
                                timestamp=datetime.now(),
                                portfolio_name=self.portfolio_name,
                            )
                            self.persistence_manager.record_trade(trade)
                    else:
                        error_msg = f"Broker rejected buy order for {symbol}"
                        logger.warning(f"Failed to buy {symbol}")
                        failed_trades.append({
                            "symbol": symbol,
                            "action": "BUY",
                            "quantity": 0.0,
                            "cost": allocation_per_stock,
                            "error": error_msg,
                        })
                        buys.append({
                            "symbol": symbol,
                            "quantity": 0,
                            "cost": allocation_per_stock,
                            "status": "failed",
                            "error": error_msg,
                            "order_id": None,
                        })
                except Exception as e:
                    error_msg = f"Error buying {symbol}: {str(e)}"
                    logger.error(error_msg)
                    failed_trades.append({
                        "symbol": symbol,
                        "action": "BUY",
                        "quantity": 0.0,
                        "cost": allocation_per_stock,
                        "error": error_msg,
                    })
                    buys.append({
                        "symbol": symbol,
                        "quantity": 0,
                        "cost": allocation_per_stock,
                        "status": "failed",
                        "error": error_msg,
                        "order_id": None,
                    })
        
        # Get updated allocations (or current if dry-run)
        try:
            all_allocations = self.broker.get_current_allocation()
            # Filter allocations to only include symbols owned by this portfolio
            final_allocations = self._filter_allocations_by_portfolio(all_allocations)
            
            # Reconcile ownership records with broker allocations to fix quantities
            if not dry_run and self.persistence_manager and buys:
                try:
                    reconcile_result = self.persistence_manager.reconcile_ownership_with_broker(
                        all_allocations, self.portfolio_name
                    )
                    if reconcile_result['fixed'] > 0:
                        logger.info(f"[{self.portfolio_name}] Fixed {reconcile_result['fixed']} ownership quantity records")
                except Exception as e:
                    logger.warning(f"[{self.portfolio_name}] Error reconciling ownership: {e}")
            
            # Update quantities in buys
            for buy in buys:
                for alloc in final_allocations:
                    if alloc.symbol.upper() == buy["symbol"].upper():
                        buy["quantity"] = alloc.quantity
                        # Update persistence trade record quantity if needed
                        # (Ownership is already updated in record_trade, so this is mainly for logging)
                        break
        except Exception as e:
            logger.error(f"Error getting final allocations: {e}")
            final_allocations = []
        
        return self._create_summary(buys, [], final_allocations, failed_trades=failed_trades)
    
    def _execute_week_over_week_rebalancing(
        self,
        current_allocations: List[Allocation],
        current_week_symbols: List[str],
        previous_week_symbols: List[str],
        current_ranks: Dict[str, int],
        external_sale_proceeds: float = 0.0,
        external_sales_by_symbol: Optional[Dict[str, Any]] = None,
        dry_run: bool = False,
    ) -> TradeSummary:
        """
        Execute rebalancing based on week-over-week leaderboard comparison with slack.

        Buy stocks ranked 1 to stockcount that we don't hold.
        Sell stocks that dropped below stockcount + slack threshold.

        Args:
            current_allocations: Current portfolio positions
            current_week_symbols: Top stockcount symbols from current week's leaderboard
            previous_week_symbols: Top stockcount symbols from previous week's leaderboard
            current_ranks: Dictionary mapping symbol to current rank
            external_sale_proceeds: Proceeds from external sales available for reinvestment
            external_sales_by_symbol: Dict of external sales by symbol
            dry_run: If True, print actions but don't execute trades.
        """
        current_symbols = {alloc.symbol.upper() for alloc in current_allocations}
        current_week_set = {s.upper() for s in current_week_symbols}  # Top stockcount symbols

        # Sell threshold: stockcount + slack
        sell_threshold = self.stockcount + self.slack

        # Find symbols to sell: current holdings that dropped below threshold
        symbols_to_sell = set()
        for symbol in current_symbols:
            rank = current_ranks.get(symbol)
            if rank is None:
                # Symbol not in leaderboard anymore - sell it
                logger.info(f"[{self.portfolio_name}] {symbol} no longer in leaderboard. Will sell.")
                symbols_to_sell.add(symbol)
            elif rank > sell_threshold:
                # Rank dropped below threshold - sell it
                logger.info(f"[{self.portfolio_name}] {symbol} rank={rank} > threshold={sell_threshold}. Will sell.")
                symbols_to_sell.add(symbol)
            else:
                logger.info(f"[{self.portfolio_name}] {symbol} rank={rank} <= threshold={sell_threshold}. Holding.")

        # Filter by persistence ownership if enabled
        if self.persistence_manager:
            owned_symbols = self.persistence_manager.get_owned_symbols(self.portfolio_name)
            symbols_to_sell = symbols_to_sell & owned_symbols
            logger.info(f"[{self.portfolio_name}] Persistence enabled: Only selling from owned symbols: {owned_symbols}")

        # Find symbols to buy: in top stockcount but not currently held
        symbols_to_buy = current_week_set - current_symbols

        for symbol in symbols_to_buy:
            rank = current_ranks.get(symbol, 999)
            logger.info(f"[{self.portfolio_name}] {symbol} rank={rank} in top {self.stockcount}. Will buy.")
        
        # If persistence is enabled, also buy:
        # 1. Symbols that are held but NOT purchased by bot (manually purchased stocks that enter top 5)
        # 2. Symbols that had external sales and are still in top 5 (buy back using external sale proceeds)
        if self.persistence_manager:
            owned_symbols = self.persistence_manager.get_owned_symbols(self.portfolio_name)
            # Find symbols in top 5 that are held but not owned by bot
            manually_held_in_top5 = (current_week_set & current_symbols) - owned_symbols
            if manually_held_in_top5:
                logger.info(f"[{self.portfolio_name}] Found manually purchased stocks in top 5: {manually_held_in_top5}. Will buy to bring to target allocation.")
                symbols_to_buy = symbols_to_buy | manually_held_in_top5
            
            # Find symbols in top 5 that had external sales (buy back using those proceeds)
            if external_sales_by_symbol:
                symbols_with_external_sales = set(external_sales_by_symbol.keys())
                symbols_to_buyback = (current_week_set & current_symbols) & symbols_with_external_sales
                if symbols_to_buyback:
                    logger.info(f"[{self.portfolio_name}] Found stocks in top 5 with external sales: {symbols_to_buyback}. Will buy back using external sale proceeds.")
                    symbols_to_buy = symbols_to_buy | symbols_to_buyback
        
        sells = []
        buys = []
        failed_trades = []  # Track failed trades
        
        # Sell positions that dropped out of top 5
        total_proceeds = 0.0
        for symbol in symbols_to_sell:
            allocation = next((a for a in current_allocations if a.symbol.upper() == symbol), None)
            if allocation:
                # Track portfolio quantity for deficit calculation (needed after sell)
                portfolio_tracked_quantity = 0.0
                
                if dry_run:
                    sells.append({
                        "symbol": symbol,
                        "quantity": allocation.quantity,
                        "proceeds": allocation.market_value,
                        "status": "planned",
                        "error": None,
                        "order_id": None,
                    })
                    total_proceeds += allocation.market_value
                    logger.info(f"[{self.portfolio_name}] [DRY-RUN] Would sell {allocation.quantity} shares of {symbol} for ${allocation.market_value} (dropped out of top 5)")
                else:
                    try:
                        # Check persistence ownership if enabled
                        if self.persistence_manager:
                            # Get portfolio's tracked quantity - portfolio always sells ALL of its tracked shares
                            portfolio_tracked_quantity = self.persistence_manager.get_ownership_quantity(symbol, self.portfolio_name)
                            broker_total_quantity = allocation.quantity  # This is the total broker quantity (all portfolios combined)
                            
                            if portfolio_tracked_quantity > 0:
                                # Portfolio sells as much as it can: min of tracked quantity and broker total
                                # First portfolio gets priority - sells as much as it can
                                sellable_quantity = min(portfolio_tracked_quantity, broker_total_quantity)
                                deficit_quantity = portfolio_tracked_quantity - sellable_quantity
                                
                                # Check if other portfolios own this stock
                                other_portfolios = self.persistence_manager.get_all_portfolios_owning_symbol(symbol)
                                
                                if sellable_quantity > 0:
                                    if deficit_quantity > 0:
                                        # Portfolio wants to sell more than broker has - deficit will be treated as external sale
                                        logger.info(f"[{self.portfolio_name}] Selling {sellable_quantity:.2f} shares of {symbol} (broker has {broker_total_quantity:.2f}, portfolio tracked {portfolio_tracked_quantity:.2f}, deficit {deficit_quantity:.2f} will be treated as external sale)")
                                    else:
                                        if len(other_portfolios) > 1:
                                            logger.info(f"[{self.portfolio_name}] Selling ALL {sellable_quantity:.2f} shares of {symbol} (portfolio's full position, other portfolios: {[p for p in other_portfolios if p != self.portfolio_name]})")
                                        else:
                                            logger.info(f"[{self.portfolio_name}] Selling ALL {sellable_quantity:.2f} shares of {symbol} (portfolio's full position)")
                                    
                                    allocation.quantity = sellable_quantity
                                    allocation.market_value = allocation.current_price * sellable_quantity
                                else:
                                    # Broker has no shares available - all will be treated as external sale
                                    logger.warning(f"[{self.portfolio_name}] Broker has no shares of {symbol} available (portfolio tracked {portfolio_tracked_quantity:.2f}, all will be treated as external sale)")
                                    # Record entire position as external sale and skip broker sell
                                    if not dry_run:
                                        from ..persistence.models import ExternalSaleRecord
                                        # Get cost basis for calculating estimated proceeds
                                        ownership_records = self.persistence_manager.get_portfolio_ownership_records(self.portfolio_name)
                                        ownership = ownership_records.get(symbol.upper(), {})
                                        total_cost = ownership.get('total_cost', 0.0)
                                        avg_price = ownership.get('avg_price', 0.0)
                                        if avg_price == 0 and allocation.current_price > 0:
                                            avg_price = allocation.current_price
                                        
                                        estimated_proceeds = portfolio_tracked_quantity * avg_price
                                        external_sale = ExternalSaleRecord(
                                            symbol=symbol,
                                            quantity=portfolio_tracked_quantity,
                                            estimated_proceeds=estimated_proceeds,
                                            detected_date=datetime.now(),
                                            portfolio_name=self.portfolio_name,
                                        )
                                        self.persistence_manager._record_external_sale(external_sale)
                                        logger.info(f"[{self.portfolio_name}] Recorded external sale: {portfolio_tracked_quantity:.2f} shares of {symbol} (~${estimated_proceeds:.2f})")
                                    continue
                                
                                # Check if we can sell - verify portfolio has enough AND broker has enough total
                                if not self.persistence_manager.can_sell(symbol, allocation.quantity, self.portfolio_name, broker_total_quantity=broker_total_quantity):
                                    portfolio_owned = self.persistence_manager.get_ownership_quantity(symbol, self.portfolio_name)
                                    total_tracked = self.persistence_manager.get_total_tracked_ownership(symbol)
                                    logger.warning(f"[{self.portfolio_name}] Cannot sell {symbol}: Portfolio owns {portfolio_owned:.2f}, Total tracked: {total_tracked:.2f}, Broker total: {broker_total_quantity:.2f}, Requested: {allocation.quantity:.2f}")
                                    continue
                            else:
                                logger.warning(f"[{self.portfolio_name}] Cannot sell {symbol}: Portfolio has no tracked ownership")
                                continue
                        
                        success = self.broker.sell(symbol, allocation.quantity)
                        if success:
                            # Try to get order ID if broker supports it
                            order_id = None
                            try:
                                # Some brokers return order ID from sell() - check if available
                                if hasattr(self.broker, '_last_order_id'):
                                    order_id = getattr(self.broker, '_last_order_id', None)
                            except:
                                pass
                            
                            sells.append({
                                "symbol": symbol,
                                "quantity": allocation.quantity,
                                "proceeds": allocation.market_value,
                                "status": "submitted",
                                "error": None,
                                "order_id": order_id,
                            })
                            total_proceeds += allocation.market_value
                            logger.info(f"Sold {allocation.quantity} shares of {symbol} for ${allocation.market_value} (dropped out of top 5)")
                            
                            # Record trade in persistence
                            if self.persistence_manager:
                                from ..persistence.models import TradeRecord, ExternalSaleRecord
                                trade = TradeRecord(
                                    symbol=symbol,
                                    action="SELL",
                                    quantity=allocation.quantity,
                                    price=allocation.current_price,
                                    total=allocation.market_value,
                                    timestamp=datetime.now(),
                                    trade_id=order_id,
                                    portfolio_name=self.portfolio_name,
                                )
                                self.persistence_manager.record_trade(trade)
                                
                                # If there's a deficit (portfolio wanted to sell more than broker had), record as external sale
                                if portfolio_tracked_quantity > allocation.quantity:
                                    deficit_quantity = portfolio_tracked_quantity - allocation.quantity
                                    # Get cost basis for calculating estimated proceeds
                                    ownership_records = self.persistence_manager.get_portfolio_ownership_records(self.portfolio_name)
                                    ownership = ownership_records.get(symbol.upper(), {})
                                    total_cost = ownership.get('total_cost', 0.0)
                                    avg_price = ownership.get('avg_price', 0.0)
                                    if avg_price == 0 and allocation.current_price > 0:
                                        avg_price = allocation.current_price
                                    
                                    estimated_proceeds = deficit_quantity * avg_price
                                    external_sale = ExternalSaleRecord(
                                        symbol=symbol,
                                        quantity=deficit_quantity,
                                        estimated_proceeds=estimated_proceeds,
                                        detected_date=datetime.now(),
                                        portfolio_name=self.portfolio_name,
                                    )
                                    self.persistence_manager._record_external_sale(external_sale)
                                    logger.info(f"[{self.portfolio_name}] Recorded external sale for deficit: {deficit_quantity:.2f} shares of {symbol} (~${estimated_proceeds:.2f}) - broker didn't have enough shares")
                        else:
                            error_msg = f"Broker rejected sell order for {symbol}"
                            logger.warning(f"Failed to sell {symbol}")
                            failed_trades.append({
                                "symbol": symbol,
                                "action": "SELL",
                                "quantity": allocation.quantity,
                                "error": error_msg,
                            })
                            sells.append({
                                "symbol": symbol,
                                "quantity": allocation.quantity,
                                "proceeds": allocation.market_value,
                                "status": "failed",
                                "error": error_msg,
                                "order_id": None,
                            })
                    except Exception as e:
                        error_msg = f"Error selling {symbol}: {str(e)}"
                        logger.error(error_msg)
                        failed_trades.append({
                            "symbol": symbol,
                            "action": "SELL",
                            "quantity": allocation.quantity if allocation else 0.0,
                            "error": error_msg,
                        })
                        if allocation:
                            sells.append({
                                "symbol": symbol,
                                "quantity": allocation.quantity,
                                "proceeds": allocation.market_value,
                                "status": "failed",
                                "error": error_msg,
                                "order_id": None,
                            })
        
        # Use proceeds from sales + external sale proceeds to buy new stocks
        # Get current cash balance for logging purposes only
        try:
            current_cash = self.broker.get_account_cash()
            if dry_run:
                logger.info(f"[{self.portfolio_name}] Current cash balance: ${current_cash}")
                logger.info(f"[{self.portfolio_name}] Proceeds from sales: ${total_proceeds}")
                if external_sale_proceeds > 0:
                    logger.info(f"[{self.portfolio_name}] External sale proceeds: ${external_sale_proceeds}")
            else:
                logger.info(f"[{self.portfolio_name}] Available cash: ${current_cash}")
        except Exception as e:
            logger.error(f"[{self.portfolio_name}] Error getting account cash: {e}")
        
        # Buy new positions that entered top 5 (equal weight) using proceeds from sales + external sales
        total_available = total_proceeds + external_sale_proceeds

        # If no sale proceeds but missing stocks exist, use initial capital from portfolio cash
        if symbols_to_buy and total_available == 0 and self.persistence_manager:
            # Find stocks not held at all (truly missing from portfolio)
            owned_symbols = self.persistence_manager.get_owned_symbols(self.portfolio_name)
            missing_stocks = symbols_to_buy - current_symbols  # Not held by broker at all

            if missing_stocks:
                # Get available cash balance from portfolio cash tracking
                available_cash = self.persistence_manager.get_portfolio_cash(self.portfolio_name)

                if available_cash > 0:
                    # Calculate allocation per missing stock
                    target_allocation = self.initial_capital / self.stockcount
                    max_per_stock = available_cash / len(missing_stocks)
                    allocation_per_stock = min(target_allocation, max_per_stock)

                    if allocation_per_stock >= 1.0:  # Minimum viable trade ($1)
                        total_available = allocation_per_stock * len(missing_stocks)
                        symbols_to_buy = missing_stocks  # Only buy truly missing stocks
                        logger.info(
                            f"[{self.portfolio_name}] Using initial capital for missing stocks: "
                            f"${allocation_per_stock:.2f}/stock for {missing_stocks} "
                            f"(available cash: ${available_cash:.2f})"
                        )
                    else:
                        logger.warning(
                            f"[{self.portfolio_name}] Insufficient cash (${available_cash:.2f}) "
                            f"for missing stocks: {missing_stocks} (need at least $1/stock)"
                        )
                        symbols_to_buy = set()
                else:
                    logger.warning(
                        f"[{self.portfolio_name}] No cash available for missing stocks: {missing_stocks}"
                    )
                    symbols_to_buy = set()

        if symbols_to_buy:
            if total_available == 0:
                # Check if any are manually held stocks that need bot purchase
                if self.persistence_manager:
                    manually_held = symbols_to_buy & (current_symbols - self.persistence_manager.get_owned_symbols(self.portfolio_name))
                    if manually_held:
                        logger.warning(f"[{self.portfolio_name}] Manually purchased stocks in top 5: {manually_held}, but no proceeds from sales available. Cannot buy to bring to target allocation.")
                    else:
                        logger.warning(f"[{self.portfolio_name}] Symbols to buy: {symbols_to_buy}, but no proceeds available. Skipping purchases.")
                else:
                    logger.warning(f"[{self.portfolio_name}] Symbols to buy: {symbols_to_buy}, but no proceeds available. Skipping purchases.")
            else:
                # Use proceeds from sales + external sale proceeds
                # Round to 2 decimal places (Alpaca requires notional values to be limited to 2 decimal places)
                allocation_per_stock = round(total_available / len(symbols_to_buy), 2)
                if dry_run:
                    logger.info(f"[{self.portfolio_name}] [DRY-RUN] Would buy {len(symbols_to_buy)} new stocks with ${allocation_per_stock} each (using proceeds: ${total_available:.2f})")
                else:
                    logger.info(f"[{self.portfolio_name}] Buying {len(symbols_to_buy)} new stocks with ${allocation_per_stock} each (using proceeds: ${total_available:.2f})")
                
                for symbol in symbols_to_buy:
                    # Check if this is a manually held stock being bought by bot
                    is_manually_held = False
                    is_buyback = False
                    if self.persistence_manager and symbol in current_symbols:
                        owned_symbols = self.persistence_manager.get_owned_symbols(self.portfolio_name)
                        is_manually_held = symbol not in owned_symbols
                        is_buyback = external_sales_by_symbol and symbol in external_sales_by_symbol
                    
                    if dry_run:
                        buys.append({
                            "symbol": symbol,
                            "quantity": 0,  # Will be estimated
                            "cost": allocation_per_stock,
                            "status": "planned",
                            "error": None,
                            "order_id": None,
                        })
                        if is_buyback and external_sales_by_symbol:
                            external_sale = external_sales_by_symbol.get(symbol)
                            if external_sale:
                                logger.info(f"[{self.portfolio_name}] [DRY-RUN] Would buy ${allocation_per_stock} of {symbol} (buying back after external sale of {external_sale.quantity} shares)")
                        elif is_manually_held:
                            logger.info(f"[{self.portfolio_name}] [DRY-RUN] Would buy ${allocation_per_stock} of {symbol} (manually held stock entered top 5, buying to bring to target allocation)")
                        else:
                            logger.info(f"[{self.portfolio_name}] [DRY-RUN] Would buy ${allocation_per_stock} of {symbol} (entered top 5)")
                    else:
                        try:
                            success = self.broker.buy(symbol, allocation_per_stock)
                            # Try to get order ID if broker supports it
                            order_id = None
                            try:
                                if hasattr(self.broker, '_last_order_id'):
                                    order_id = getattr(self.broker, '_last_order_id', None)
                            except:
                                pass
                            
                            if success:
                                buys.append({
                                    "symbol": symbol,
                                    "quantity": 0,  # Will be updated
                                    "cost": allocation_per_stock,
                                    "status": "submitted",
                                    "error": None,
                                    "order_id": order_id,
                                })
                                if is_buyback and external_sales_by_symbol:
                                    external_sale = external_sales_by_symbol.get(symbol)
                                    if external_sale:
                                        logger.info(f"[{self.portfolio_name}] Bought ${allocation_per_stock} of {symbol} (buying back after external sale of {external_sale.quantity} shares)")
                                elif is_manually_held:
                                    logger.info(f"[{self.portfolio_name}] Bought ${allocation_per_stock} of {symbol} (manually held stock entered top 5, buying to bring to target allocation)")
                                else:
                                    logger.info(f"[{self.portfolio_name}] Bought ${allocation_per_stock} of {symbol} (entered top 5)")
                                
                                # Record trade in persistence
                                if self.persistence_manager:
                                    from ..persistence.models import TradeRecord
                                    # Get current price for the trade record
                                    current_price = next(
                                        (alloc.current_price for alloc in final_allocations if alloc.symbol.upper() == symbol.upper()),
                                        0.0
                                    )
                                    if current_price == 0.0:
                                        # Try to get from current allocations if final_allocations not updated yet
                                        try:
                                            updated_allocations = self.broker.get_current_allocation()
                                            current_price = next(
                                                (alloc.current_price for alloc in updated_allocations if alloc.symbol.upper() == symbol.upper()),
                                                allocation_per_stock  # Fallback to notional
                                            )
                                        except:
                                            current_price = allocation_per_stock
                                    
                                    trade = TradeRecord(
                                        symbol=symbol,
                                        action="BUY",
                                        quantity=0,  # Will be updated below
                                        price=current_price,
                                        total=allocation_per_stock,
                                        timestamp=datetime.now(),
                                        portfolio_name=self.portfolio_name,
                                    )
                                    self.persistence_manager.record_trade(trade)
                            else:
                                error_msg = f"Broker rejected buy order for {symbol}"
                                logger.warning(f"Failed to buy {symbol}")
                                failed_trades.append({
                                    "symbol": symbol,
                                    "action": "BUY",
                                    "quantity": 0.0,
                                    "cost": allocation_per_stock,
                                    "error": error_msg,
                                })
                                buys.append({
                                    "symbol": symbol,
                                    "quantity": 0,
                                    "cost": allocation_per_stock,
                                    "status": "failed",
                                    "error": error_msg,
                                    "order_id": None,
                                })
                        except Exception as e:
                            error_msg = f"Error buying {symbol}: {str(e)}"
                            logger.error(error_msg)
                            failed_trades.append({
                                "symbol": symbol,
                                "action": "BUY",
                                "quantity": 0.0,
                                "cost": allocation_per_stock,
                                "error": error_msg,
                            })
                            buys.append({
                                "symbol": symbol,
                                "quantity": 0,
                                "cost": allocation_per_stock,
                                "status": "failed",
                                "error": error_msg,
                                "order_id": None,
                            })
        
        # Get final allocations (use current if dry-run, since no trades were executed)
        try:
            all_allocations = self.broker.get_current_allocation()
            # Filter allocations to only include symbols owned by this portfolio
            final_allocations = self._filter_allocations_by_portfolio(all_allocations)
            
            # Reconcile ownership records with broker allocations to fix quantities
            if not dry_run and self.persistence_manager and buys:
                try:
                    reconcile_result = self.persistence_manager.reconcile_ownership_with_broker(
                        all_allocations, self.portfolio_name
                    )
                    if reconcile_result['fixed'] > 0:
                        logger.info(f"[{self.portfolio_name}] Fixed {reconcile_result['fixed']} ownership quantity records")
                except Exception as e:
                    logger.warning(f"[{self.portfolio_name}] Error reconciling ownership: {e}")
            
            # Update quantities in buys (only if not dry-run, since in dry-run we don't have actual quantities)
            if not dry_run:
                for buy in buys:
                    for alloc in final_allocations:
                        if alloc.symbol.upper() == buy["symbol"].upper():
                            buy["quantity"] = alloc.quantity
                            # Update persistence trade record with actual quantity
                            if self.persistence_manager:
                                # Find the most recent BUY trade for this symbol and update quantity
                                # Note: This is a simplification - in production you might want to track trade IDs
                                pass  # Quantity update handled in record_trade via ownership update
                            break
        except Exception as e:
            logger.error(f"Error getting final allocations: {e}")
            final_allocations = []
        
        # Mark external sales as used if we used them for reinvestment
        if not dry_run and self.persistence_manager and external_sale_proceeds > 0 and total_available > 0:
            # Calculate how much external sale proceeds were used
            external_portion = min(external_sale_proceeds, total_available)
            if external_portion > 0:
                self.persistence_manager.mark_external_sales_used(external_portion, self.portfolio_name)
                logger.info(f"[{self.portfolio_name}] Marked ${external_portion:.2f} of external sale proceeds as used for reinvestment")
        
        if not sells and not buys:
            if dry_run:
                logger.info(f"[{self.portfolio_name}] [DRY-RUN] No rebalancing needed - all positions match leaderboard changes")
            else:
                logger.info(f"[{self.portfolio_name}] No rebalancing needed - all positions match leaderboard changes")
        
        return self._create_summary(buys, sells, final_allocations, failed_trades=failed_trades)
    
    def _filter_allocations_by_portfolio(self, allocations: List[Allocation]) -> List[Allocation]:
        """
        Filter allocations to only include symbols owned by this portfolio.
        
        If persistence is enabled, filters by portfolio ownership.
        If a symbol is owned by multiple portfolios, calculates the portfolio's portion.
        """
        if not self.persistence_manager:
            # No persistence - return all allocations (backward compatibility)
            return allocations
        
        owned_symbols = self.persistence_manager.get_owned_symbols(self.portfolio_name)
        if not owned_symbols:
            # No owned symbols - return empty list
            return []
        
        filtered_allocations = []
        for alloc in allocations:
            symbol = alloc.symbol.upper()
            if symbol in owned_symbols:
                # Check if multiple portfolios own this symbol
                portfolios_owning = self.persistence_manager.get_all_portfolios_owning_symbol(symbol)
                if len(portfolios_owning) > 1:
                    # Multiple portfolios own this - calculate this portfolio's fraction
                    portfolio_fraction = self.persistence_manager.get_portfolio_fraction(symbol, self.portfolio_name)
                    filtered_allocations.append(Allocation(
                        symbol=alloc.symbol,
                        quantity=alloc.quantity * portfolio_fraction,
                        current_price=alloc.current_price,
                        market_value=alloc.market_value * portfolio_fraction,
                    ))
                else:
                    # Only this portfolio owns it - use full allocation
                    filtered_allocations.append(alloc)
        
        return filtered_allocations
    
    def _create_summary(
        self,
        buys: List[dict],
        sells: List[dict],
        final_allocations: List[Allocation],
        failed_trades: Optional[List[dict]] = None,
    ) -> TradeSummary:
        """Create trade summary."""
        # Filter allocations to only include symbols owned by this portfolio
        filtered_allocations = self._filter_allocations_by_portfolio(final_allocations)
        
        total_cost = sum(buy.get("cost", 0) for buy in buys)
        total_proceeds = sum(sell.get("proceeds", 0) for sell in sells)
        portfolio_value = sum(alloc.market_value for alloc in filtered_allocations)
        
        summary = TradeSummary(
            buys=buys,
            sells=sells,
            total_cost=total_cost,
            total_proceeds=total_proceeds,
            final_allocations=filtered_allocations,
            portfolio_value=portfolio_value,
            portfolio_name=self.portfolio_name,
            initial_capital=self.initial_capital,
            failed_trades=failed_trades or [],
        )
        
        # Note: Email notification is handled in main.py after rebalancing completes
        # to have access to config for recipient address
        
        return summary
