"""Persistence manager for tracking trades and ownership in Firebase Firestore."""

import os
import json
import logging
from datetime import datetime, timedelta, timedelta
from typing import Dict, List, Optional, Set, Union
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    import firebase_admin
    from firebase_admin import credentials, firestore
    from google.cloud.firestore_v1.base_query import FieldFilter
    FIREBASE_AVAILABLE = True
except ImportError:
    FIREBASE_AVAILABLE = False
    FieldFilter = None

from .models import TradeRecord, OwnershipRecord, ExternalSaleRecord, PortfolioCashRecord, ExecutionRunRecord
from src.broker.models import Allocation
from typing import List as TypingList


class PersistenceManager:
    """Manages trade and ownership persistence in Firebase Firestore."""
    
    def __init__(self, project_id: str, credentials_path: Optional[str] = None, credentials_json: Optional[str] = None):
        """
        Initialize Firebase connection.
        
        Args:
            project_id: Firebase project ID
            credentials_path: Path to Firebase service account JSON file (optional if credentials_json is provided)
            credentials_json: Firebase service account JSON as string (optional if credentials_path is provided)
        """
        if not FIREBASE_AVAILABLE:
            raise ImportError("firebase-admin is not installed. Install it with: pip install firebase-admin")
        
        # Validate that at least one credential method is provided
        if not credentials_path and not credentials_json:
            raise ValueError("Either credentials_path or credentials_json must be provided")
        
        # Initialize Firebase Admin SDK
        if credentials_json:
            # Parse JSON string and create credentials from dict
            try:
                cred_dict = json.loads(credentials_json)
                cred = credentials.Certificate(cred_dict)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON in credentials_json: {e}")
        else:
            # Use file path
            if not os.path.exists(credentials_path):
                raise FileNotFoundError(f"Firebase credentials file not found: {credentials_path}")
            cred = credentials.Certificate(credentials_path)
        
        try:
            firebase_admin.initialize_app(cred, {'projectId': project_id})
        except ValueError:
            # App already initialized (e.g., in tests)
            pass
        
        self.db = firestore.client()
        self.project_id = project_id
    
    def record_trade(self, trade: TradeRecord) -> None:
        """Record a trade in Firestore."""
        collection = self.db.collection('trades')
        doc_ref = collection.document()
        doc_ref.set(trade.to_dict())
        
        # Update ownership record
        self._update_ownership(trade)
    
    def _update_ownership(self, trade: TradeRecord) -> None:
        """Update ownership record based on trade."""
        symbol = trade.symbol.upper()
        portfolio_name = trade.portfolio_name
        # Use composite key: {portfolio_name}_{symbol}
        doc_id = f"{portfolio_name}_{symbol}"
        ownership_ref = self.db.collection('ownership').document(doc_id)
        ownership_doc = ownership_ref.get()
        
        if trade.action == "BUY":
            # Calculate quantity from total cost and price if quantity is 0 or not provided
            # But only if price is reasonable (not equal to total, which would indicate wrong price)
            if trade.quantity <= 0:
                if trade.price > 0 and trade.price != trade.total and trade.total > 0:
                    # Price looks valid - calculate quantity
                    calculated_quantity = trade.total / trade.price
                else:
                    # Price is wrong or missing - defer calculation until we get actual quantity from broker
                    # Set quantity to 0 for now, will be updated when we reconcile with broker
                    calculated_quantity = 0.0
            else:
                calculated_quantity = trade.quantity
            
            # If we have a valid quantity, update ownership
            if calculated_quantity > 0:
                if ownership_doc.exists:
                    # Update existing ownership
                    data = ownership_doc.to_dict()
                    old_quantity = data.get('quantity', 0.0)
                    old_cost = data.get('total_cost', 0.0)
                    
                    new_quantity = old_quantity + calculated_quantity
                    new_cost = old_cost + trade.total
                    
                    ownership_ref.update({
                        'quantity': new_quantity,
                        'total_cost': new_cost,
                        'last_purchase_date': trade.timestamp,
                        'last_updated': trade.timestamp,
                    })
                else:
                    # Create new ownership record
                    ownership_ref.set({
                        'symbol': symbol,
                        'portfolio_name': portfolio_name,
                        'quantity': calculated_quantity,
                        'total_cost': trade.total,
                        'first_purchase_date': trade.timestamp,
                        'last_purchase_date': trade.timestamp,
                        'last_updated': trade.timestamp,
                    })
            else:
                # Quantity is 0 or couldn't be calculated - create/update record with cost but 0 quantity
                # This will be fixed when we reconcile with broker allocations
                if ownership_doc.exists:
                    data = ownership_doc.to_dict()
                    old_cost = data.get('total_cost', 0.0)
                    ownership_ref.update({
                        'total_cost': old_cost + trade.total,
                        'last_purchase_date': trade.timestamp,
                        'last_updated': trade.timestamp,
                    })
                else:
                    ownership_ref.set({
                        'symbol': symbol,
                        'portfolio_name': portfolio_name,
                        'quantity': 0.0,  # Will be updated when reconciled
                        'total_cost': trade.total,
                        'first_purchase_date': trade.timestamp,
                        'last_purchase_date': trade.timestamp,
                        'last_updated': trade.timestamp,
                    })
        
        elif trade.action == "SELL":
            if ownership_doc.exists:
                data = ownership_doc.to_dict()
                old_quantity = data.get('quantity', 0.0)
                old_cost = data.get('total_cost', 0.0)
                
                # Calculate cost basis proportionally
                if old_quantity > 0:
                    cost_per_share = old_cost / old_quantity
                    cost_of_sold = cost_per_share * trade.quantity
                    new_quantity = old_quantity - trade.quantity
                    new_cost = old_cost - cost_of_sold
                    
                    if new_quantity <= 0:
                        # All shares sold, delete ownership record
                        ownership_ref.delete()
                    else:
                        ownership_ref.update({
                            'quantity': new_quantity,
                            'total_cost': new_cost,
                            'last_updated': trade.timestamp,
                        })
    
    def get_owned_symbols(self, portfolio_name: str = "SP400") -> Set[str]:
        """Get set of symbols we own according to persistence for a specific portfolio."""
        ownership_ref = self.db.collection('ownership')
        # Use FieldFilter to avoid positional argument warning
        if FieldFilter:
            docs = ownership_ref.where(filter=FieldFilter('portfolio_name', '==', portfolio_name)).stream()
        else:
            # Fallback to positional arguments if FieldFilter not available
            docs = ownership_ref.where('portfolio_name', '==', portfolio_name).stream()
        
        owned_symbols = set()
        for doc in docs:
            data = doc.to_dict()
            quantity = data.get('quantity', 0.0)
            if quantity > 0:
                owned_symbols.add(data.get('symbol', '').upper())
        
        return owned_symbols
    
    def get_ownership_quantity(self, symbol: str, portfolio_name: str = "SP400") -> float:
        """Get owned quantity for a symbol in a specific portfolio."""
        symbol = symbol.upper()
        doc_id = f"{portfolio_name}_{symbol}"
        ownership_ref = self.db.collection('ownership').document(doc_id)
        ownership_doc = ownership_ref.get()
        
        if ownership_doc.exists:
            data = ownership_doc.to_dict()
            return data.get('quantity', 0.0)
        return 0.0
    
    def can_sell(self, symbol: str, quantity: float, portfolio_name: str = "SP400", broker_total_quantity: Optional[float] = None) -> bool:
        """
        Check if we can sell the requested quantity for a specific portfolio.
        
        When multiple portfolios own the same stock, we need to check:
        1. Portfolio has enough tracked quantity
        2. Broker has enough total quantity (across all portfolios)
        
        Args:
            symbol: Stock symbol
            quantity: Quantity to sell
            portfolio_name: Portfolio name
            broker_total_quantity: Optional total quantity from broker (across all portfolios).
                                  If provided, ensures broker has enough total holdings.
        
        Returns:
            True if portfolio has enough tracked quantity AND (if broker_total_quantity provided) broker has enough total
        """
        owned_quantity = self.get_ownership_quantity(symbol, portfolio_name)
        
        # Check if portfolio has enough tracked quantity
        if owned_quantity < quantity:
            return False
        
        # If broker total quantity is provided, check if broker has enough total holdings
        # This is important when multiple portfolios own the same stock - broker account
        # has all portfolios' shares combined, so we need to ensure broker has enough total
        if broker_total_quantity is not None:
            # Broker must have at least the requested quantity (since it holds all portfolios' shares)
            if broker_total_quantity < quantity:
                return False
            
            # Also verify that the portfolio's share of broker holdings is sufficient
            # Calculate portfolio's fraction of total tracked ownership
            total_tracked = self.get_total_tracked_ownership(symbol)
            if total_tracked > 0:
                portfolio_fraction = owned_quantity / total_tracked
                # Portfolio's share of broker holdings
                portfolio_broker_share = broker_total_quantity * portfolio_fraction
                # Portfolio can only sell up to its share of broker holdings
                if portfolio_broker_share < quantity:
                    return False
        
        return True
    
    def get_total_tracked_ownership(self, symbol: str) -> float:
        """Get total tracked ownership across all portfolios for a symbol."""
        symbol = symbol.upper()
        ownership_ref = self.db.collection('ownership')
        if FieldFilter:
            docs = ownership_ref.where(filter=FieldFilter('symbol', '==', symbol)).stream()
        else:
            docs = ownership_ref.where('symbol', '==', symbol).stream()
        
        total_quantity = 0.0
        for doc in docs:
            data = doc.to_dict()
            quantity = data.get('quantity', 0.0)
            if quantity > 0:
                total_quantity += quantity
        
        return total_quantity
    
    def get_portfolio_fraction(self, symbol: str, portfolio_name: str) -> float:
        """Calculate portfolio's fraction of total tracked ownership for a symbol."""
        symbol = symbol.upper()
        portfolio_quantity = self.get_ownership_quantity(symbol, portfolio_name)
        total_quantity = self.get_total_tracked_ownership(symbol)
        
        if total_quantity == 0:
            return 0.0
        
        return portfolio_quantity / total_quantity
    
    def get_portfolio_ownership_records(self, portfolio_name: str) -> Dict[str, Dict[str, float]]:
        """
        Get ownership records with purchase prices for a portfolio.
        
        Returns:
            Dict mapping symbol to dict with 'quantity', 'total_cost', and 'avg_price'
        """
        ownership_ref = self.db.collection('ownership')
        if FieldFilter:
            docs = ownership_ref.where(filter=FieldFilter('portfolio_name', '==', portfolio_name)).stream()
        else:
            docs = ownership_ref.where('portfolio_name', '==', portfolio_name).stream()
        
        records = {}
        for doc in docs:
            data = doc.to_dict()
            symbol = data.get('symbol', '').upper()
            quantity = data.get('quantity', 0.0)
            total_cost = data.get('total_cost', 0.0)
            
            if quantity > 0 and symbol:
                avg_price = total_cost / quantity if quantity > 0 else 0.0
                records[symbol] = {
                    'quantity': quantity,
                    'total_cost': total_cost,
                    'avg_price': avg_price
                }
        
        return records
    
    def get_all_portfolios_owning_symbol(self, symbol: str) -> TypingList[str]:
        """Get list of portfolio names that own a symbol."""
        symbol = symbol.upper()
        ownership_ref = self.db.collection('ownership')
        if FieldFilter:
            docs = ownership_ref.where(filter=FieldFilter('symbol', '==', symbol)).stream()
        else:
            docs = ownership_ref.where('symbol', '==', symbol).stream()
        
        portfolios = []
        for doc in docs:
            data = doc.to_dict()
            quantity = data.get('quantity', 0.0)
            portfolio_name = data.get('portfolio_name', 'SP400')
            if quantity > 0 and portfolio_name not in portfolios:
                portfolios.append(portfolio_name)
        
        return portfolios
    
    def detect_external_sales(
        self,
        broker_allocations: List[Allocation],
        broker_transactions: Optional[List[dict]] = None,
        portfolio_name: str = "SP400"
    ) -> List[ExternalSaleRecord]:
        """Detect external sales by comparing DB ownership vs broker positions for a specific portfolio."""
        external_sales = []
        
        # Get DB ownership for this portfolio
        db_ownership: Dict[str, float] = {}
        ownership_ref = self.db.collection('ownership')
        if FieldFilter:
            docs = ownership_ref.where(filter=FieldFilter('portfolio_name', '==', portfolio_name)).stream()
        else:
            docs = ownership_ref.where('portfolio_name', '==', portfolio_name).stream()
        for doc in docs:
            data = doc.to_dict()
            symbol = data.get('symbol', '').upper()
            quantity = data.get('quantity', 0.0)
            if quantity > 0:
                db_ownership[symbol] = quantity
        
        # Get broker positions
        broker_positions: Dict[str, float] = {}
        for allocation in broker_allocations:
            symbol = allocation.symbol.upper()
            broker_positions[symbol] = allocation.quantity
        
        # Compare: if DB says we own more than broker has, external sale occurred
        for symbol, db_quantity in db_ownership.items():
            broker_quantity = broker_positions.get(symbol, 0.0)
            if db_quantity > broker_quantity:
                # Calculate how many bot-owned shares were sold
                # Strategy: Assume remaining shares (up to bot's purchase count) are bot-owned
                # This allows bot to continue managing remaining shares
                
                doc_id = f"{portfolio_name}_{symbol}"
                ownership_ref = self.db.collection('ownership').document(doc_id)
                ownership_doc = ownership_ref.get()
                if not ownership_doc.exists:
                    continue
                
                data = ownership_doc.to_dict()
                total_cost = data.get('total_cost', 0.0)
                cost_per_share = total_cost / db_quantity if db_quantity > 0 else 0.0
                
                if broker_quantity == 0:
                    # All bot-owned shares were sold (broker has none)
                    sold_quantity = db_quantity
                    estimated_proceeds = cost_per_share * sold_quantity
                    # Delete ownership record
                    ownership_ref.delete()
                elif broker_quantity < db_quantity:
                    # Some shares were sold externally
                    # Assume remaining shares (up to bot's purchase count) are bot-owned
                    sold_quantity = db_quantity - broker_quantity
                    estimated_proceeds = cost_per_share * sold_quantity
                    
                    # Update ownership: keep broker_quantity as bot-owned
                    # Adjust cost basis proportionally
                    remaining_cost = total_cost * (broker_quantity / db_quantity)
                    ownership_ref.update({
                        'quantity': broker_quantity,
                        'total_cost': remaining_cost,
                        'last_updated': datetime.now(),
                    })
                else:
                    # broker_quantity >= db_quantity (shouldn't happen, but handle gracefully)
                    continue
                
                external_sale = ExternalSaleRecord(
                    symbol=symbol,
                    quantity=sold_quantity,
                    estimated_proceeds=estimated_proceeds,
                    detected_date=datetime.now(),
                    portfolio_name=portfolio_name,
                )
                external_sales.append(external_sale)
                
                # Record external sale
                self._record_external_sale(external_sale)
        
        # Also check broker transactions if available
        if broker_transactions:
            external_sales.extend(self._detect_external_sales_from_transactions(broker_transactions))
        
        return external_sales
    
    def _detect_external_sales_from_transactions(self, transactions: List[dict]) -> List[ExternalSaleRecord]:
        """Detect external sales by comparing broker transactions with DB records."""
        external_sales = []
        
        # Get all DB trades
        db_trades: Set[str] = set()
        trades_ref = self.db.collection('trades')
        docs = trades_ref.stream()
        for doc in docs:
            data = doc.to_dict()
            trade_id = data.get('trade_id')
            if trade_id:
                db_trades.add(trade_id)
        
        # Check broker transactions
        for transaction in transactions:
            trade_id = transaction.get('id') or transaction.get('trade_id')
            action = transaction.get('side', '').upper() or transaction.get('action', '').upper()
            
            if action == "SELL" and trade_id and trade_id not in db_trades:
                # This is a sell transaction not in our DB
                symbol = transaction.get('symbol', '').upper()
                quantity = float(transaction.get('quantity', 0))
                price = float(transaction.get('price', 0))
                proceeds = quantity * price
                
                external_sale = ExternalSaleRecord(
                    symbol=symbol,
                    quantity=quantity,
                    estimated_proceeds=proceeds,
                    detected_date=datetime.now(),
                )
                external_sales.append(external_sale)
                self._record_external_sale(external_sale)
        
        return external_sales
    
    def _record_external_sale(self, sale: ExternalSaleRecord) -> None:
        """Record an external sale detection."""
        collection = self.db.collection('external_sales')
        doc_ref = collection.document()
        doc_ref.set(sale.to_dict())
    
    def get_unused_external_sale_proceeds(self, portfolio_name: str = "SP400") -> float:
        """Get total proceeds from external sales not yet used for reinvestment for a specific portfolio."""
        external_sales_ref = self.db.collection('external_sales')
        if FieldFilter:
            docs = external_sales_ref.where(filter=FieldFilter('used_for_reinvestment', '==', False)).where(filter=FieldFilter('portfolio_name', '==', portfolio_name)).stream()
        else:
            docs = external_sales_ref.where('used_for_reinvestment', '==', False).where('portfolio_name', '==', portfolio_name).stream()
        
        total_proceeds = 0.0
        for doc in docs:
            data = doc.to_dict()
            total_proceeds += data.get('estimated_proceeds', 0.0)
        
        return total_proceeds
    
    def mark_external_sales_used(self, amount: float, portfolio_name: str = "SP400") -> None:
        """Mark external sales as used for reinvestment for a specific portfolio."""
        external_sales_ref = self.db.collection('external_sales')
        if FieldFilter:
            docs = external_sales_ref.where(filter=FieldFilter('used_for_reinvestment', '==', False)).where(filter=FieldFilter('portfolio_name', '==', portfolio_name)).stream()
        else:
            docs = external_sales_ref.where('used_for_reinvestment', '==', False).where('portfolio_name', '==', portfolio_name).stream()
        
        remaining = amount
        for doc in docs:
            if remaining <= 0:
                break
            
            data = doc.to_dict()
            proceeds = data.get('estimated_proceeds', 0.0)
            
            if proceeds <= remaining:
                # Mark this sale as fully used
                doc.reference.update({
                    'used_for_reinvestment': True,
                    'reinvestment_date': datetime.now(),
                })
                remaining -= proceeds
            else:
                # Partial use - would need to split records, but for simplicity mark as used
                doc.reference.update({
                    'used_for_reinvestment': True,
                    'reinvestment_date': datetime.now(),
                })
                remaining = 0
    
    def reconcile_with_broker_history(self, broker_trades: List[dict]) -> dict:
        """
        Reconcile Firestore trade records with broker trade history.
        
        Args:
            broker_trades: List of trade dicts from broker with keys:
                symbol, action, quantity, price, total, timestamp, trade_id
        
        Returns:
            Dictionary with reconciliation results:
            {
                'updated': int,  # Number of trades updated
                'missing': int,   # Number of broker trades not in Firestore
                'unfilled': int   # Number of Firestore trades not filled in broker
            }
        """
        if not broker_trades:
            return {'updated': 0, 'missing': 0, 'unfilled': 0}
        
        # Get all Firestore trades from recent period for this portfolio
        trades_ref = self.db.collection('trades')
        # Get trades from last 7 days (adjust as needed)
        cutoff_date = datetime.now() - timedelta(days=7)
        
        db_trades = {}
        db_trades_by_id = {}
        # Note: reconcile_with_broker_history doesn't have portfolio_name parameter yet
        # For now, filter by portfolio_name if provided in broker_trades
        if FieldFilter:
            query = trades_ref.where(filter=FieldFilter('timestamp', '>=', cutoff_date))
        else:
            query = trades_ref.where('timestamp', '>=', cutoff_date)
        
        for doc in query.stream():
            data = doc.to_dict()
            trade_id = data.get('trade_id')
            symbol = data.get('symbol', '').upper()
            action = data.get('action', '').upper()
            timestamp = data.get('timestamp')
            doc_portfolio = data.get('portfolio_name', 'SP400')
            
            # Create key for matching
            key = f"{symbol}_{action}_{timestamp}"
            db_trades[key] = {
                'doc_id': doc.id,
                'data': data,
                'matched': False
            }
            
            if trade_id:
                db_trades_by_id[trade_id] = {
                    'doc_id': doc.id,
                    'data': data,
                    'matched': False
                }
        
        # Match broker trades with Firestore records
        updated_count = 0
        missing_count = 0
        
        for broker_trade in broker_trades:
            symbol = broker_trade.get('symbol', '').upper()
            action = broker_trade.get('action', '').upper()
            trade_id = broker_trade.get('trade_id')
            broker_quantity = broker_trade.get('quantity', 0.0)
            broker_price = broker_trade.get('price', 0.0)
            broker_total = broker_trade.get('total', 0.0)
            broker_timestamp = broker_trade.get('timestamp')
            
            # Try to match by trade_id first
            matched = False
            if trade_id and trade_id in db_trades_by_id:
                db_trade = db_trades_by_id[trade_id]
                matched = True
            else:
                # Try to match by symbol, action, and timestamp (within 1 hour)
                for key, db_trade in db_trades.items():
                    if db_trade['matched']:
                        continue
                    
                    db_data = db_trade['data']
                    db_symbol = db_data.get('symbol', '').upper()
                    db_action = db_data.get('action', '').upper()
                    db_timestamp = db_data.get('timestamp')
                    
                    if (db_symbol == symbol and db_action == action and 
                        broker_timestamp and db_timestamp):
                        # Check if timestamps are within 1 hour
                        # Handle both datetime objects and Firestore Timestamp objects
                        if hasattr(db_timestamp, 'timestamp'):
                            db_ts = db_timestamp.timestamp()
                        elif isinstance(db_timestamp, datetime):
                            db_ts = db_timestamp.timestamp()
                        else:
                            continue
                        
                        if isinstance(broker_timestamp, datetime):
                            broker_ts = broker_timestamp.timestamp()
                        else:
                            continue
                        
                        time_diff = abs(broker_ts - db_ts)
                        if time_diff < 3600:  # 1 hour
                            matched = True
                            break
            
            if matched:
                # Update Firestore record with actual fill data
                db_data = db_trade['data']
                doc_id = db_trade['doc_id']
                
                # Check if update is needed
                needs_update = False
                if abs(db_data.get('quantity', 0) - broker_quantity) > 0.01:
                    needs_update = True
                if abs(db_data.get('price', 0) - broker_price) > 0.01:
                    needs_update = True
                if abs(db_data.get('total', 0) - broker_total) > 0.01:
                    needs_update = True
                
                # Clear reconciliation_status if it was set to 'unfilled'
                has_unfilled_status = db_data.get('reconciliation_status') == 'unfilled'
                if needs_update or has_unfilled_status:
                    update_data = {
                        'reconciled_at': datetime.now(),
                        'trade_id': trade_id or db_data.get('trade_id'),
                    }
                    
                    if needs_update:
                        update_data.update({
                            'quantity': broker_quantity,
                            'price': broker_price,
                            'total': broker_total,
                        })
                    
                    # Clear reconciliation_status since trade is now matched/filled
                    if has_unfilled_status:
                        update_data['reconciliation_status'] = 'filled'
                    
                    doc_ref = trades_ref.document(doc_id)
                    doc_ref.update(update_data)
                    
                    # Note: Ownership will be recalculated after reconciliation completes
                    # See recalculate_ownership_from_trades() method
                    
                    updated_count += 1
                
                db_trade['matched'] = True
            else:
                # Broker trade not found in Firestore - might be external trade
                missing_count += 1
        
        # Find Firestore trades that weren't matched (unfilled orders)
        unfilled_count = 0
        for db_trade in db_trades.values():
            if not db_trade['matched']:
                db_data = db_trade['data']
                # Check if trade has valid fill data (quantity > 0 and price > 0)
                db_quantity = db_data.get('quantity', 0)
                db_price = db_data.get('price', 0)
                db_total = db_data.get('total', 0)
                has_valid_fill_data = db_quantity > 0 and db_price > 0 and db_total > 0
                
                # Check if this trade is recent (within last 24 hours)
                db_timestamp = db_data.get('timestamp')
                if db_timestamp:
                    # Handle Firestore Timestamp objects
                    if hasattr(db_timestamp, 'timestamp'):
                        db_ts = db_timestamp.timestamp()
                    elif isinstance(db_timestamp, datetime):
                        db_ts = db_timestamp.timestamp()
                    else:
                        continue
                    
                    now_ts = datetime.now().timestamp()
                    time_diff = now_ts - db_ts
                    if time_diff < 86400:  # 24 hours
                        if has_valid_fill_data:
                            # Trade has valid fill data but wasn't matched - clear unfilled status
                            # This can happen if broker doesn't return the trade in history but it was filled
                            current_status = db_data.get('reconciliation_status')
                            if current_status == 'unfilled':
                                doc_ref = trades_ref.document(db_trade['doc_id'])
                                doc_ref.update({
                                    'reconciliation_status': 'filled',
                                    'reconciled_at': datetime.now(),
                                })
                        else:
                            # Trade doesn't have valid fill data - mark as potentially unfilled
                            doc_ref = trades_ref.document(db_trade['doc_id'])
                            doc_ref.update({
                                'reconciliation_status': 'unfilled',
                                'reconciled_at': datetime.now(),
                            })
                            unfilled_count += 1
        
        # After reconciliation, recalculate ownership records from all trade records
        # This ensures ownership reflects actual fill prices and quantities
        if updated_count > 0:
            try:
                # Get all portfolios that had trades updated
                portfolios_to_recalculate = set()
                for db_trade in db_trades.values():
                    if db_trade.get('matched'):
                        db_data = db_trade['data']
                        portfolio_name = db_data.get('portfolio_name')
                        if portfolio_name:
                            portfolios_to_recalculate.add(portfolio_name)
                
                # Recalculate ownership for each affected portfolio
                for portfolio_name in portfolios_to_recalculate:
                    try:
                        self.recalculate_ownership_from_trades(portfolio_name)
                        logger.info(f"Recalculated ownership records for {portfolio_name} after reconciliation")
                    except Exception as e:
                        logger.warning(f"Error recalculating ownership for {portfolio_name}: {e}")
            except Exception as e:
                logger.warning(f"Error recalculating ownership after reconciliation: {e}")
        
        return {
            'updated': updated_count,
            'missing': missing_count,
            'unfilled': unfilled_count
        }
    
    def reconcile_ownership_with_broker(
        self,
        broker_allocations: List[Allocation],
        portfolio_name: str = "SP400"
    ) -> dict:
        """
        Reconcile ownership records with broker allocations to fix quantities.
        
        Updates ownership records to match actual broker positions.
        This fixes cases where quantities were incorrectly calculated.
        
        IMPORTANT: Only reconciles if all recent trades have filled. Skips reconciliation
        if there are any unfilled trades to avoid incorrect quantity updates.
        
        Args:
            broker_allocations: List of Allocation objects from broker
            portfolio_name: Portfolio name to reconcile
            
        Returns:
            Dictionary with reconciliation results:
            {
                'updated': int,  # Number of ownership records updated
                'fixed': int      # Number of records with quantity corrections
            }
        """
        # Check if there are recent unfilled trades
        if self.has_recent_unfilled_trades(portfolio_name):
            logger.info(f"[{portfolio_name}] Skipping ownership reconciliation - trades are still pending fill")
            return {'updated': 0, 'fixed': 0}
        
        # Get broker positions for this portfolio
        broker_positions = {}
        for alloc in broker_allocations:
            symbol = alloc.symbol.upper()
            # Check if this portfolio owns this symbol
            if symbol in self.get_owned_symbols(portfolio_name):
                # Get portfolio fraction if multiple portfolios own it
                portfolios_owning = self.get_all_portfolios_owning_symbol(symbol)
                if len(portfolios_owning) > 1:
                    portfolio_fraction = self.get_portfolio_fraction(symbol, portfolio_name)
                    broker_positions[symbol] = {
                        'quantity': alloc.quantity * portfolio_fraction,
                        'current_price': alloc.current_price,
                        'market_value': alloc.market_value * portfolio_fraction,
                    }
                else:
                    broker_positions[symbol] = {
                        'quantity': alloc.quantity,
                        'current_price': alloc.current_price,
                        'market_value': alloc.market_value,
                    }
        
        # Get DB ownership records
        ownership_ref = self.db.collection('ownership')
        if FieldFilter:
            docs = ownership_ref.where(filter=FieldFilter('portfolio_name', '==', portfolio_name)).stream()
        else:
            docs = ownership_ref.where('portfolio_name', '==', portfolio_name).stream()
        
        updated_count = 0
        fixed_count = 0
        
        for doc in docs:
            data = doc.to_dict()
            symbol = data.get('symbol', '').upper()
            db_quantity = data.get('quantity', 0.0)
            db_total_cost = data.get('total_cost', 0.0)
            
            if symbol in broker_positions:
                broker_quantity = broker_positions[symbol]['quantity']
                broker_price = broker_positions[symbol]['current_price']
                
                # Check if quantity needs fixing
                quantity_diff = abs(db_quantity - broker_quantity)
                if quantity_diff > 0.01:  # More than 0.01 shares difference
                    # Update quantity to match broker
                    doc.reference.update({
                        'quantity': broker_quantity,
                        'last_updated': datetime.now(),
                    })
                    fixed_count += 1
                    updated_count += 1
                    logger.info(f"Fixed quantity for {symbol} in {portfolio_name}: DB={db_quantity:.2f} -> Broker={broker_quantity:.2f}")
                elif db_quantity == 0 and broker_quantity > 0:
                    # Quantity was 0, now we have actual quantity
                    doc.reference.update({
                        'quantity': broker_quantity,
                        'last_updated': datetime.now(),
                    })
                    fixed_count += 1
                    updated_count += 1
                    logger.info(f"Set quantity for {symbol} in {portfolio_name}: {broker_quantity:.2f} (was 0)")
            elif db_quantity > 0:
                # Broker doesn't have this position but DB says we own it
                # This might be an external sale - don't update here, let detect_external_sales handle it
                pass
        
        return {
            'updated': updated_count,
            'fixed': fixed_count
        }
    
    def has_recent_unfilled_trades(self, portfolio_name: str, hours: int = 24) -> bool:
        """
        Check if there are recent unfilled trades for a portfolio.
        
        Args:
            portfolio_name: Portfolio name to check
            hours: Time window in hours to check (default 24)
            
        Returns:
            True if there are unfilled trades, False otherwise
        """
        trades_ref = self.db.collection('trades')
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        if FieldFilter:
            query = trades_ref.where(filter=FieldFilter('portfolio_name', '==', portfolio_name))
        else:
            query = trades_ref.where('portfolio_name', '==', portfolio_name)
        
        for doc in query.stream():
            data = doc.to_dict()
            timestamp = data.get('timestamp')
            reconciliation_status = data.get('reconciliation_status')
            
            # Check if trade is recent and unfilled
            if timestamp:
                if hasattr(timestamp, 'timestamp'):
                    trade_time = datetime.fromtimestamp(timestamp.timestamp())
                elif isinstance(timestamp, datetime):
                    trade_time = timestamp
                else:
                    continue
                
                if trade_time >= cutoff_time:
                    # Check if trade is unfilled
                    if reconciliation_status == 'unfilled':
                        return True
                    # Also check if trade has no valid fill data (quantity/price/total)
                    quantity = data.get('quantity', 0.0)
                    price = data.get('price', 0.0)
                    total = data.get('total', 0.0)
                    if quantity <= 0 or price <= 0 or total <= 0:
                        return True
        
        return False
    
    def recalculate_ownership_from_trades(self, portfolio_name: str) -> dict:
        """
        Recalculate ownership records from all trade records for a portfolio.
        
        This ensures ownership reflects actual fill prices and quantities after reconciliation.
        
        Args:
            portfolio_name: Portfolio name to recalculate
            
        Returns:
            Dictionary with recalculation results:
            {
                'updated': int,  # Number of ownership records updated
                'recalculated': int  # Number of symbols recalculated
            }
        """
        # Get all trade records for this portfolio
        trades_ref = self.db.collection('trades')
        if FieldFilter:
            trades_query = trades_ref.where(filter=FieldFilter('portfolio_name', '==', portfolio_name))
        else:
            trades_query = trades_ref.where('portfolio_name', '==', portfolio_name)
        
        trades = trades_query.stream()
        
        # Aggregate trades by symbol
        symbol_trades = {}
        for trade_doc in trades:
            trade_data = trade_doc.to_dict()
            symbol = trade_data.get('symbol', '').upper()
            action = trade_data.get('action', '').upper()
            quantity = trade_data.get('quantity', 0.0)
            price = trade_data.get('price', 0.0)
            total = trade_data.get('total', 0.0)
            
            # Only use trades with valid fill data
            if quantity <= 0 or price <= 0 or total <= 0:
                continue
            
            if symbol not in symbol_trades:
                symbol_trades[symbol] = {
                    'buys': [],
                    'sells': [],
                }
            
            if action == 'BUY':
                symbol_trades[symbol]['buys'].append({
                    'quantity': quantity,
                    'price': price,
                    'total': total,
                })
            elif action == 'SELL':
                symbol_trades[symbol]['sells'].append({
                    'quantity': quantity,
                    'price': price,
                    'total': total,
                })
        
        # Recalculate ownership for each symbol
        updated_count = 0
        recalculated_count = 0
        
        for symbol, trades_data in symbol_trades.items():
            # Calculate net quantity and total cost
            total_buy_quantity = sum(buy['quantity'] for buy in trades_data['buys'])
            total_buy_cost = sum(buy['total'] for buy in trades_data['buys'])
            total_sell_quantity = sum(sell['quantity'] for sell in trades_data['sells'])
            
            # Net quantity owned
            net_quantity = total_buy_quantity - total_sell_quantity
            
            # Calculate cost basis (FIFO: reduce cost basis proportionally when selling)
            # For simplicity, we'll use average cost basis
            # If we've sold some shares, reduce cost basis proportionally
            if total_buy_quantity > 0:
                cost_basis = total_buy_cost * (net_quantity / total_buy_quantity) if net_quantity > 0 else 0.0
            else:
                cost_basis = 0.0
            
            # Update or create ownership record
            doc_id = f"{portfolio_name}_{symbol}"
            ownership_ref = self.db.collection('ownership').document(doc_id)
            ownership_doc = ownership_ref.get()
            
            if net_quantity > 0:
                # We own shares - update ownership record
                avg_price = cost_basis / net_quantity if net_quantity > 0 else 0.0
                
                if ownership_doc.exists:
                    # Update existing record
                    ownership_ref.update({
                        'quantity': net_quantity,
                        'total_cost': cost_basis,
                        'last_updated': datetime.now(),
                    })
                else:
                    # Create new record
                    # Get first and last purchase dates from trades
                    first_purchase_date = datetime.now()
                    last_purchase_date = datetime.now()
                    if trades_data['buys']:
                        # Get timestamps from trade records
                        buy_trades = trades_ref.where('portfolio_name', '==', portfolio_name).where('symbol', '==', symbol).where('action', '==', 'BUY').order_by('timestamp').stream()
                        buy_timestamps = []
                        for doc in buy_trades:
                            ts = doc.to_dict().get('timestamp')
                            if ts:
                                if hasattr(ts, 'timestamp'):
                                    buy_timestamps.append(datetime.fromtimestamp(ts.timestamp()))
                                elif isinstance(ts, datetime):
                                    buy_timestamps.append(ts)
                        
                        if buy_timestamps:
                            first_purchase_date = min(buy_timestamps)
                            last_purchase_date = max(buy_timestamps)
                    
                    ownership_ref.set({
                        'symbol': symbol,
                        'portfolio_name': portfolio_name,
                        'quantity': net_quantity,
                        'total_cost': cost_basis,
                        'first_purchase_date': first_purchase_date,
                        'last_purchase_date': last_purchase_date,
                        'last_updated': datetime.now(),
                    })
                
                updated_count += 1
                recalculated_count += 1
            else:
                # We don't own any shares - delete ownership record if it exists
                if ownership_doc.exists:
                    ownership_ref.delete()
                    updated_count += 1
        
        return {
            'updated': updated_count,
            'recalculated': recalculated_count
        }
    
    def get_all_trades_for_portfolio(self, portfolio_name: str) -> List[dict]:
        """
        Get all historical trades for a portfolio from Firestore.
        
        Returns all trades (BUY and SELL) for the given portfolio, excluding
        unfilled trades or trades from the current run that haven't been recorded yet.
        
        Args:
            portfolio_name: Portfolio name to get trades for
            
        Returns:
            List of trade dictionaries with keys: action, total, quantity, price, timestamp
        """
        trades_ref = self.db.collection('trades')
        
        if FieldFilter:
            query = trades_ref.where(filter=FieldFilter('portfolio_name', '==', portfolio_name))
        else:
            query = trades_ref.where('portfolio_name', '==', portfolio_name)
        
        trades = []
        for doc in query.stream():
            data = doc.to_dict()
            action = data.get('action', '').upper()
            total = data.get('total', 0.0)
            quantity = data.get('quantity', 0.0)
            price = data.get('price', 0.0)
            timestamp = data.get('timestamp')
            reconciliation_status = data.get('reconciliation_status')
            
            # Only include trades with valid fill data
            # Exclude unfilled trades (they haven't executed yet)
            if action in ['BUY', 'SELL'] and total > 0 and quantity > 0 and price > 0:
                # Skip unfilled trades - they're from current run and haven't executed
                # Include trades with None reconciliation_status (filled but not yet reconciled)
                # or 'filled' status, but exclude 'unfilled'
                if reconciliation_status is None or reconciliation_status != 'unfilled':
                    trades.append({
                        'action': action,
                        'total': total,
                        'quantity': quantity,
                        'price': price,
                        'timestamp': timestamp,
                    })

        return trades

    # ============================================================
    # Portfolio Cash Tracking Methods
    # ============================================================

    def initialize_portfolio_cash(self, portfolio_name: str, initial_capital: float) -> None:
        """
        Initialize cash balance for a portfolio if not exists.

        Called once per portfolio setup. Does not overwrite existing balance.

        Args:
            portfolio_name: Portfolio name
            initial_capital: Initial capital amount
        """
        cash_ref = self.db.collection('portfolio_cash').document(portfolio_name)
        cash_doc = cash_ref.get()

        if not cash_doc.exists:
            now = datetime.now()
            cash_record = PortfolioCashRecord(
                portfolio_name=portfolio_name,
                initial_capital=initial_capital,
                cash_balance=initial_capital,
                created_at=now,
                last_updated=now,
            )
            cash_ref.set(cash_record.to_dict())
            logger.info(f"[{portfolio_name}] Initialized cash balance: ${initial_capital:.2f}")
        else:
            logger.debug(f"[{portfolio_name}] Cash balance already exists, not overwriting")

    def get_portfolio_cash(self, portfolio_name: str) -> float:
        """
        Get current cash balance for a portfolio.

        Args:
            portfolio_name: Portfolio name

        Returns:
            Current cash balance, or 0.0 if not initialized
        """
        cash_ref = self.db.collection('portfolio_cash').document(portfolio_name)
        cash_doc = cash_ref.get()

        if cash_doc.exists:
            data = cash_doc.to_dict()
            return data.get('cash_balance', 0.0)
        return 0.0

    def update_portfolio_cash(self, portfolio_name: str, amount: float, is_buy: bool) -> float:
        """
        Update cash balance: subtract on buy, add on sell.

        Args:
            portfolio_name: Portfolio name
            amount: Amount to add/subtract
            is_buy: True for buy (subtract), False for sell (add)

        Returns:
            New cash balance
        """
        cash_ref = self.db.collection('portfolio_cash').document(portfolio_name)
        cash_doc = cash_ref.get()

        if not cash_doc.exists:
            logger.warning(f"[{portfolio_name}] Cash record not found, cannot update")
            return 0.0

        data = cash_doc.to_dict()
        current_balance = data.get('cash_balance', 0.0)

        if is_buy:
            new_balance = current_balance - amount
        else:
            new_balance = current_balance + amount

        cash_ref.update({
            'cash_balance': new_balance,
            'last_updated': datetime.now(),
        })

        action = "debited" if is_buy else "credited"
        logger.info(f"[{portfolio_name}] Cash {action}: ${amount:.2f}, new balance: ${new_balance:.2f}")
        return new_balance

    # ============================================================
    # Execution Run Tracking Methods
    # ============================================================

    def _get_today_date_et(self) -> str:
        """Get today's date in ET timezone as YYYY-MM-DD string."""
        import pytz
        eastern = pytz.timezone('America/New_York')
        now_et = datetime.now(eastern)
        return now_et.strftime('%Y-%m-%d')

    def start_execution_run(self, portfolio_name: str) -> str:
        """
        Start a new execution run for a portfolio.

        Args:
            portfolio_name: Portfolio name

        Returns:
            Execution run ID (format: {portfolio_name}_{date})
        """
        date_str = self._get_today_date_et()
        run_id = f"{portfolio_name}_{date_str}"

        run_ref = self.db.collection('execution_runs').document(run_id)
        run_doc = run_ref.get()

        now = datetime.now()

        if run_doc.exists:
            # Run already exists - update to started
            run_ref.update({
                'status': 'started',
                'started_at': now,
                'completed_at': None,
                'error_message': None,
            })
            logger.info(f"[{portfolio_name}] Restarted execution run: {run_id}")
        else:
            # Create new run
            run_record = ExecutionRunRecord(
                portfolio_name=portfolio_name,
                date=date_str,
                status='started',
                started_at=now,
            )
            run_ref.set(run_record.to_dict())
            logger.info(f"[{portfolio_name}] Started new execution run: {run_id}")

        return run_id

    def get_execution_run(self, portfolio_name: str, date_str: Optional[str] = None) -> Optional[dict]:
        """
        Get execution run for a portfolio on a specific date.

        Args:
            portfolio_name: Portfolio name
            date_str: Date string (YYYY-MM-DD). Defaults to today in ET.

        Returns:
            Execution run data dict, or None if not found
        """
        if date_str is None:
            date_str = self._get_today_date_et()

        run_id = f"{portfolio_name}_{date_str}"
        run_ref = self.db.collection('execution_runs').document(run_id)
        run_doc = run_ref.get()

        if run_doc.exists:
            data = run_doc.to_dict()
            data['run_id'] = run_id
            return data
        return None

    def was_successful_today(self, portfolio_name: str) -> bool:
        """
        Check if portfolio already completed successfully today.

        A run is successful when:
        1. status == "completed"
        2. trades_submitted == 0 (all trades reached terminal status)

        Args:
            portfolio_name: Portfolio name

        Returns:
            True if successful today, False otherwise
        """
        run = self.get_execution_run(portfolio_name)
        if not run:
            return False

        status = run.get('status', '')
        trades_submitted = run.get('trades_submitted', 0)

        # Successful = completed AND no trades stuck in submitted state
        return status == 'completed' and trades_submitted == 0

    def update_execution_run(self, execution_run_id: str, **kwargs) -> None:
        """
        Update execution run fields.

        Args:
            execution_run_id: Run ID (format: {portfolio_name}_{date})
            **kwargs: Fields to update (status, trades_planned, trades_submitted,
                      trades_filled, trades_failed, completed_at, error_message)
        """
        run_ref = self.db.collection('execution_runs').document(execution_run_id)
        run_doc = run_ref.get()

        if not run_doc.exists:
            logger.warning(f"Execution run not found: {execution_run_id}")
            return

        # Filter to allowed fields
        allowed_fields = {
            'status', 'trades_planned', 'trades_submitted', 'trades_filled',
            'trades_failed', 'completed_at', 'error_message'
        }
        update_data = {k: v for k, v in kwargs.items() if k in allowed_fields}

        if update_data:
            run_ref.update(update_data)
            logger.debug(f"Updated execution run {execution_run_id}: {update_data}")

    # ============================================================
    # Trade Status Tracking Methods
    # ============================================================

    def record_planned_trade(self, trade: TradeRecord, execution_run_id: str) -> str:
        """
        Record a planned trade with execution run ID.

        Args:
            trade: Trade record (will have status set to 'planned')
            execution_run_id: Associated execution run ID

        Returns:
            Firestore document ID for the trade
        """
        trade.status = 'planned'
        trade.execution_run_id = execution_run_id

        collection = self.db.collection('trades')
        doc_ref = collection.document()
        doc_ref.set(trade.to_dict())

        logger.debug(f"Recorded planned trade: {trade.symbol} {trade.action}")
        return doc_ref.id

    def update_trade_submitted(self, trade_doc_id: str, broker_order_id: Optional[str] = None) -> None:
        """
        Update trade status to submitted.

        Args:
            trade_doc_id: Firestore document ID
            broker_order_id: Broker's order ID (optional)
        """
        trade_ref = self.db.collection('trades').document(trade_doc_id)
        update_data = {
            'status': 'submitted',
            'submitted_at': datetime.now(),
        }
        if broker_order_id:
            update_data['broker_order_id'] = broker_order_id

        trade_ref.update(update_data)
        logger.debug(f"Trade {trade_doc_id} marked as submitted (order_id: {broker_order_id})")

    def update_trade_filled(
        self,
        trade_doc_id: str,
        quantity: float,
        price: float,
        total: float,
    ) -> None:
        """
        Update trade status to filled with actual fill data.

        Args:
            trade_doc_id: Firestore document ID
            quantity: Filled quantity
            price: Fill price
            total: Total value
        """
        trade_ref = self.db.collection('trades').document(trade_doc_id)
        trade_ref.update({
            'status': 'filled',
            'filled_at': datetime.now(),
            'quantity': quantity,
            'price': price,
            'total': total,
        })
        logger.debug(f"Trade {trade_doc_id} marked as filled: {quantity} @ ${price:.2f}")

    def update_trade_failed(self, trade_doc_id: str, error_message: str) -> None:
        """
        Update trade status to failed.

        Args:
            trade_doc_id: Firestore document ID
            error_message: Error description
        """
        trade_ref = self.db.collection('trades').document(trade_doc_id)
        trade_ref.update({
            'status': 'failed',
            'failed_at': datetime.now(),
            'error_message': error_message,
        })
        logger.debug(f"Trade {trade_doc_id} marked as failed: {error_message}")

    def get_submitted_trades(self, portfolio_name: str) -> List[dict]:
        """
        Get all trades with status 'submitted' for a portfolio.

        Args:
            portfolio_name: Portfolio name

        Returns:
            List of trade dicts with doc_id included
        """
        trades_ref = self.db.collection('trades')

        if FieldFilter:
            query = trades_ref.where(
                filter=FieldFilter('portfolio_name', '==', portfolio_name)
            ).where(
                filter=FieldFilter('status', '==', 'submitted')
            )
        else:
            query = trades_ref.where(
                'portfolio_name', '==', portfolio_name
            ).where(
                'status', '==', 'submitted'
            )

        trades = []
        for doc in query.stream():
            data = doc.to_dict()
            data['doc_id'] = doc.id
            trades.append(data)

        return trades

    def get_pending_trades(self, portfolio_name: str) -> List[dict]:
        """
        Get all trades with status 'planned' or 'submitted' for a portfolio.

        Args:
            portfolio_name: Portfolio name

        Returns:
            List of trade dicts with doc_id included
        """
        trades_ref = self.db.collection('trades')

        # Get planned trades
        if FieldFilter:
            planned_query = trades_ref.where(
                filter=FieldFilter('portfolio_name', '==', portfolio_name)
            ).where(
                filter=FieldFilter('status', '==', 'planned')
            )
        else:
            planned_query = trades_ref.where(
                'portfolio_name', '==', portfolio_name
            ).where(
                'status', '==', 'planned'
            )

        trades = []
        for doc in planned_query.stream():
            data = doc.to_dict()
            data['doc_id'] = doc.id
            trades.append(data)

        # Get submitted trades
        submitted_trades = self.get_submitted_trades(portfolio_name)
        trades.extend(submitted_trades)

        return trades
