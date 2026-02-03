"""Abstract base class for email notifiers."""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Union
from datetime import datetime

from ..broker.models import Allocation, TradeSummary, MultiPortfolioSummary


class EmailNotifier(ABC):
    """Abstract base class for email notification providers."""
    
    def send_trade_summary(
        self,
        recipient: str,
        trade_summary: Union[TradeSummary, MultiPortfolioSummary],
        leaderboard_symbols: Optional[List[str]] = None,
        portfolio_leaderboards: Optional[Dict[str, List[str]]] = None,
        portfolio_ownership: Optional[Dict[str, Dict[str, Dict[str, float]]]] = None,
        pre_trade_performance: Optional[MultiPortfolioSummary] = None,
    ) -> bool:
        """
        Send trade summary email.
        
        Args:
            recipient: Email recipient address
            trade_summary: Trade summary data (single or multi-portfolio) - contains planned/executed trades
            leaderboard_symbols: List of symbols from leaderboard (for single portfolio)
            portfolio_leaderboards: Dict of portfolio_name -> symbols (for multi-portfolio)
            portfolio_ownership: Dict of portfolio_name -> {symbol: {quantity, total_cost, avg_price}}
            pre_trade_performance: Optional pre-trade performance summary (current holdings before trades)
            
        Returns:
            True if email sent successfully, False otherwise
        """
        # Format content (handled by base class)
        html_content = self._format_trade_summary_html(
            trade_summary, leaderboard_symbols, portfolio_leaderboards, portfolio_ownership, pre_trade_performance
        )
        text_content = self._format_trade_summary_text(
            trade_summary, leaderboard_symbols, portfolio_leaderboards, portfolio_ownership, pre_trade_performance
        )
        
        # Determine subject
        subject = "Portfolio Rebalancing Summary"
        if isinstance(trade_summary, MultiPortfolioSummary):
            subject = "Multi-Portfolio Rebalancing Summary"
        
        # Delegate actual sending to concrete implementation
        return self._send_email(recipient, subject, text_content, html_content)
    
    @abstractmethod
    def _send_email(
        self,
        recipient: str,
        subject: str,
        text_content: str,
        html_content: str,
    ) -> bool:
        """
        Send email (implemented by concrete classes).
        
        Args:
            recipient: Email recipient address
            subject: Email subject
            text_content: Plain text email content
            html_content: HTML email content
            
        Returns:
            True if email sent successfully, False otherwise
        """
        pass
    
    @abstractmethod
    def send_error_notification(
        self,
        recipient: str,
        error_message: str,
        context: Dict[str, Any] = None,
    ) -> bool:
        """
        Send error notification email.
        
        Args:
            recipient: Email recipient address
            error_message: Error message
            context: Additional context information
            
        Returns:
            True if email sent successfully, False otherwise
        """
        pass
    
    def _format_trade_summary_html(
        self,
        trade_summary: Union[TradeSummary, MultiPortfolioSummary],
        leaderboard_symbols: Optional[List[str]] = None,
        portfolio_leaderboards: Optional[Dict[str, List[str]]] = None,
        portfolio_ownership: Optional[Dict[str, Dict[str, Dict[str, float]]]] = None,
        pre_trade_performance: Optional[MultiPortfolioSummary] = None,
    ) -> str:
        """Format trade summary as HTML email."""
        # Check if it's multi-portfolio summary
        if isinstance(trade_summary, MultiPortfolioSummary):
            return self._format_multi_portfolio_html(trade_summary, portfolio_leaderboards or {}, portfolio_ownership, pre_trade_performance)
        
        # Single portfolio format
        html = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; }}
                h2 {{ color: #333; }}
                table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
                th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
                th {{ background-color: #4CAF50; color: white; }}
                .summary {{ background-color: #f2f2f2; padding: 15px; margin: 20px 0; }}
                .positive {{ color: #4CAF50; }}
                .negative {{ color: #f44336; }}
            </style>
        </head>
        <body>
            <h2>Portfolio Rebalancing Summary</h2>
            <p><strong>Date:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            
            <div class="summary">
                <h3>Leaderboard Top 5</h3>
                <p>{', '.join(leaderboard_symbols or [])}</p>
            </div>
        """
        
        if trade_summary.sells:
            html += """
            <h3>Stocks Sold</h3>
            <table>
                <tr>
                    <th>Symbol</th>
                    <th>Quantity</th>
                    <th>Proceeds</th>
                </tr>
            """
            for sell in trade_summary.sells:
                html += f"""
                <tr>
                    <td>{sell['symbol']}</td>
                    <td>{sell['quantity']:.2f}</td>
                    <td>${sell['proceeds']:.2f}</td>
                </tr>
                """
            html += "</table>"
        
        if trade_summary.buys:
            html += """
            <h3>Stocks Bought</h3>
            <table>
                <tr>
                    <th>Symbol</th>
                    <th>Quantity</th>
                    <th>Cost</th>
                </tr>
            """
            for buy in trade_summary.buys:
                html += f"""
                <tr>
                    <td>{buy['symbol']}</td>
                    <td>{buy['quantity']:.2f}</td>
                    <td>${buy['cost']:.2f}</td>
                </tr>
                """
            html += "</table>"
        
        html += f"""
            <div class="summary">
                <h3>Final Portfolio</h3>
                <table>
                    <tr>
                        <th>Symbol</th>
                        <th>Quantity</th>
                        <th>Current Price</th>
                        <th>Market Value</th>
                    </tr>
        """
        
        for allocation in trade_summary.final_allocations:
            html += f"""
                    <tr>
                        <td>{allocation.symbol}</td>
                        <td>{allocation.quantity:.2f}</td>
                        <td>${allocation.current_price:.2f}</td>
                        <td>${allocation.market_value:.2f}</td>
                    </tr>
            """
        
        html += f"""
                </table>
                <p><strong>Total Portfolio Value:</strong> ${trade_summary.portfolio_value:.2f}</p>
            </div>
        </body>
        </html>
        """
        
        return html
    
    def _format_multi_portfolio_html(
        self,
        multi_summary: MultiPortfolioSummary,
        portfolio_leaderboards: Dict[str, List[str]],
        portfolio_ownership: Optional[Dict[str, Dict[str, Dict[str, float]]]] = None,
        pre_trade_performance: Optional[MultiPortfolioSummary] = None,
    ) -> str:
        """Format multi-portfolio summary as HTML email."""
        html = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; }}
                h2 {{ color: #333; }}
                h3 {{ color: #555; margin-top: 30px; }}
                table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
                th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
                th {{ background-color: #4CAF50; color: white; }}
                .summary {{ background-color: #f2f2f2; padding: 15px; margin: 20px 0; }}
                .positive {{ color: #4CAF50; font-weight: bold; }}
                .negative {{ color: #f44336; font-weight: bold; }}
                .portfolio-section {{ margin: 30px 0; padding: 20px; border: 1px solid #ddd; }}
                .planned-trades {{ background-color: #fff3cd; padding: 15px; margin: 20px 0; border-left: 4px solid #ffc107; }}
            </style>
        </head>
        <body>
            <h2>Portfolio Rebalancing Summary - Multi-Portfolio</h2>
            <p><strong>Date:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            <p><strong>Note:</strong> Trades are queued and will execute when filled. Performance below reflects current holdings before trades.</p>
            
            {f'''
            <div class="summary">
                <h3>Current Performance (Before Trades)</h3>
                <table>
                    <tr>
                        <th>Metric</th>
                        <th>Value</th>
                    </tr>
                    <tr>
                        <td>Total Initial Capital</td>
                        <td>${pre_trade_performance.total_initial_capital:,.2f}</td>
                    </tr>
                    <tr>
                        <td>Total Net Invested</td>
                        <td>${pre_trade_performance.total_net_invested:,.2f}</td>
                    </tr>
                    <tr>
                        <td>Total Current Value</td>
                        <td>${pre_trade_performance.total_current_value:,.2f}</td>
                    </tr>
                    <tr>
                        <td>Overall Return</td>
                        <td class="{'positive' if pre_trade_performance.overall_return >= 0 else 'negative'}">
                            ${pre_trade_performance.overall_return:,.2f} ({pre_trade_performance.overall_return_pct:.2f}%)
                        </td>
                    </tr>
                </table>
            </div>
            ''' if pre_trade_performance else ''}
            
            <div class="planned-trades">
                <h3>Trades Status Summary</h3>
                <p>The following trades have been processed. Performance metrics reflect current holdings before trades.</p>
                <table>
                    <tr>
                        <th>Portfolio</th>
                        <th>Submitted Sells</th>
                        <th>Submitted Buys</th>
                        <th>Failed Trades</th>
                    </tr>
        """
        
        # Calculate trade status summary
        for portfolio_name, summary in multi_summary.portfolios.items():
            submitted_sells_count = len([s for s in summary.sells if s.get('status') == 'submitted'])
            submitted_buys_count = len([b for b in summary.buys if b.get('status') == 'submitted'])
            failed_count = len(summary.failed_trades) if summary.failed_trades else 0
            
            failed_class = "negative" if failed_count > 0 else ""
            
            html += f"""
                    <tr>
                        <td><strong>{portfolio_name}</strong></td>
                        <td>{submitted_sells_count}</td>
                        <td>{submitted_buys_count}</td>
                        <td class="{failed_class}">{failed_count}</td>
                    </tr>
            """
        
        html += """
                </table>
            </div>
            """
        
        if pre_trade_performance:
            html += """
            <h3>Portfolio Performance Summary (Current Holdings)</h3>
            <table>
                <tr>
                    <th>Portfolio</th>
                    <th>Initial Capital</th>
                    <th>Current Value</th>
                    <th>Return</th>
                    <th>Return %</th>
                    <th>Realized P&L</th>
                    <th>Unrealized P&L</th>
                </tr>
            """
        else:
            html += """
            <h3>Portfolio Performance Summary</h3>
            <table>
                <tr>
                    <th>Portfolio</th>
                    <th>Initial Capital</th>
                    <th>Current Value</th>
                    <th>Return</th>
                    <th>Return %</th>
                    <th>Realized P&L</th>
                    <th>Unrealized P&L</th>
                </tr>
            """
        
        # Use pre-trade performance if available, otherwise fall back to multi_summary
        performance_data = pre_trade_performance.performances if pre_trade_performance else multi_summary.performances
        
        for portfolio_name, performance in performance_data.items():
            return_class = "positive" if performance.total_return >= 0 else "negative"
            realized_class = "positive" if performance.realized_pnl >= 0 else "negative"
            unrealized_class = "positive" if performance.unrealized_pnl >= 0 else "negative"
            
            html += f"""
                <tr>
                    <td><strong>{portfolio_name}</strong></td>
                    <td>${performance.initial_capital:,.2f}</td>
                    <td>${performance.current_value:,.2f}</td>
                    <td class="{return_class}">${performance.total_return:,.2f}</td>
                    <td class="{return_class}">{performance.total_return_pct:.2f}%</td>
                    <td class="{realized_class}">${performance.realized_pnl:,.2f}</td>
                    <td class="{unrealized_class}">${performance.unrealized_pnl:,.2f}</td>
                </tr>
            """
        
        html += """
            </table>
        """
        
        # Add individual portfolio details
        for portfolio_name, summary in multi_summary.portfolios.items():
            leaderboard_symbols = portfolio_leaderboards.get(portfolio_name, [])
            performance = multi_summary.performances[portfolio_name]
            
            html += f"""
            <div class="portfolio-section">
                <h3>{portfolio_name} Portfolio Details</h3>
                <p><strong>Leaderboard Top 5:</strong> {', '.join(leaderboard_symbols)}</p>
                <p><strong>Performance:</strong> 
                    <span class="{'positive' if performance.total_return >= 0 else 'negative'}">
                        ${performance.total_return:,.2f} ({performance.total_return_pct:.2f}%)
                    </span>
                </p>
            """
            
            # Group trades by status
            planned_sells = [s for s in summary.sells if s.get('status') == 'planned']
            submitted_sells = [s for s in summary.sells if s.get('status') == 'submitted']
            failed_sells = [s for s in summary.sells if s.get('status') == 'failed']
            
            planned_buys = [b for b in summary.buys if b.get('status') == 'planned']
            submitted_buys = [b for b in summary.buys if b.get('status') == 'submitted']
            failed_buys = [b for b in summary.buys if b.get('status') == 'failed']
            
            # Show failed trades prominently first
            if failed_sells or failed_buys or (summary.failed_trades and len(summary.failed_trades) > 0):
                html += """
                <h4 style="color: #f44336;">⚠️ Failed Trades</h4>
                <table style="border: 2px solid #f44336;">
                    <tr>
                        <th>Action</th>
                        <th>Symbol</th>
                        <th>Quantity</th>
                        <th>Amount</th>
                        <th>Error</th>
                    </tr>
                """
                for trade in (summary.failed_trades or []):
                    action = trade.get('action', 'UNKNOWN')
                    symbol = trade.get('symbol', '')
                    quantity = trade.get('quantity', 0.0)
                    cost_or_proceeds = trade.get('cost') or trade.get('proceeds', 0.0)
                    error = trade.get('error', 'Unknown error')
                    html += f"""
                    <tr>
                        <td>{action}</td>
                        <td>{symbol}</td>
                        <td>{quantity:.2f}</td>
                        <td>${cost_or_proceeds:.2f}</td>
                        <td style="color: #f44336;">{error}</td>
                    </tr>
                    """
                html += "</table>"
            
            # Show submitted trades
            if submitted_sells:
                html += """
                <h4>✅ Stocks Sold (Submitted)</h4>
                <table>
                    <tr>
                        <th>Symbol</th>
                        <th>Quantity</th>
                        <th>Proceeds</th>
                        <th>Status</th>
                        <th>Order ID</th>
                    </tr>
                """
                for sell in submitted_sells:
                    order_id = sell.get('order_id', 'N/A')
                    html += f"""
                    <tr>
                        <td>{sell['symbol']}</td>
                        <td>{sell['quantity']:.2f}</td>
                        <td>${sell['proceeds']:.2f}</td>
                        <td style="color: #4CAF50;">Submitted</td>
                        <td>{order_id}</td>
                    </tr>
                    """
                html += "</table>"
            
            if submitted_buys:
                html += """
                <h4>✅ Stocks Bought (Submitted)</h4>
                <table>
                    <tr>
                        <th>Symbol</th>
                        <th>Quantity</th>
                        <th>Cost</th>
                        <th>Status</th>
                        <th>Order ID</th>
                    </tr>
                """
                for buy in submitted_buys:
                    order_id = buy.get('order_id', 'N/A')
                    html += f"""
                    <tr>
                        <td>{buy['symbol']}</td>
                        <td>{buy['quantity']:.2f}</td>
                        <td>${buy['cost']:.2f}</td>
                        <td style="color: #4CAF50;">Submitted</td>
                        <td>{order_id}</td>
                    </tr>
                    """
                html += "</table>"
            
            # Show planned trades (dry-run or not yet executed)
            if planned_sells:
                html += """
                <h4>📋 Stocks to Sell (Planned)</h4>
                <table>
                    <tr>
                        <th>Symbol</th>
                        <th>Quantity</th>
                        <th>Proceeds</th>
                        <th>Status</th>
                    </tr>
                """
                for sell in planned_sells:
                    html += f"""
                    <tr>
                        <td>{sell['symbol']}</td>
                        <td>{sell['quantity']:.2f}</td>
                        <td>${sell['proceeds']:.2f}</td>
                        <td style="color: #ff9800;">Planned</td>
                    </tr>
                    """
                html += "</table>"
            
            if planned_buys:
                html += """
                <h4>📋 Stocks to Buy (Planned)</h4>
                <table>
                    <tr>
                        <th>Symbol</th>
                        <th>Quantity</th>
                        <th>Cost</th>
                        <th>Status</th>
                    </tr>
                """
                for buy in planned_buys:
                    html += f"""
                    <tr>
                        <td>{buy['symbol']}</td>
                        <td>{buy['quantity']:.2f}</td>
                        <td>${buy['cost']:.2f}</td>
                        <td style="color: #ff9800;">Planned</td>
                    </tr>
                    """
                html += "</table>"
            
            # Legacy support: if no status field, show all trades as submitted
            if not any(s.get('status') for s in summary.sells) and summary.sells:
                html += """
                <h4>Stocks Sold</h4>
                <table>
                    <tr>
                        <th>Symbol</th>
                        <th>Quantity</th>
                        <th>Proceeds</th>
                    </tr>
                """
                for sell in summary.sells:
                    html += f"""
                    <tr>
                        <td>{sell['symbol']}</td>
                        <td>{sell['quantity']:.2f}</td>
                        <td>${sell['proceeds']:.2f}</td>
                    </tr>
                    """
                html += "</table>"
            
            if not any(b.get('status') for b in summary.buys) and summary.buys:
                html += """
                <h4>Stocks Bought</h4>
                <table>
                    <tr>
                        <th>Symbol</th>
                        <th>Quantity</th>
                        <th>Cost</th>
                    </tr>
                """
                for buy in summary.buys:
                    html += f"""
                    <tr>
                        <td>{buy['symbol']}</td>
                        <td>{buy['quantity']:.2f}</td>
                        <td>${buy['cost']:.2f}</td>
                    </tr>
                    """
                html += "</table>"
            
            # Add current holdings with purchase prices and gains
            if summary.final_allocations:
                ownership_data = (portfolio_ownership or {}).get(portfolio_name, {})
                html += """
                <h4>Current Holdings</h4>
                <table>
                    <tr>
                        <th>Symbol</th>
                        <th>Quantity</th>
                        <th>Purchase Price</th>
                        <th>Current Price</th>
                        <th>Cost Basis</th>
                        <th>Market Value</th>
                        <th>Gain/Loss</th>
                        <th>Gain %</th>
                    </tr>
                """
                for allocation in summary.final_allocations:
                    symbol = allocation.symbol.upper()
                    ownership = ownership_data.get(symbol, {})
                    avg_price = ownership.get('avg_price', 0.0)
                    cost_basis = ownership.get('total_cost', 0.0)
                    
                    # If we don't have ownership data, use current price as estimate
                    if avg_price == 0.0 and allocation.current_price > 0:
                        avg_price = allocation.current_price
                        cost_basis = allocation.market_value
                    
                    gain_loss = allocation.market_value - cost_basis
                    gain_pct = (gain_loss / cost_basis * 100) if cost_basis > 0 else 0.0
                    gain_class = "positive" if gain_loss >= 0 else "negative"
                    
                    html += f"""
                    <tr>
                        <td>{allocation.symbol}</td>
                        <td>{allocation.quantity:.2f}</td>
                        <td>${avg_price:.2f}</td>
                        <td>${allocation.current_price:.2f}</td>
                        <td>${cost_basis:.2f}</td>
                        <td>${allocation.market_value:.2f}</td>
                        <td class="{gain_class}">${gain_loss:.2f}</td>
                        <td class="{gain_class}">{gain_pct:.2f}%</td>
                    </tr>
                    """
                html += "</table>"
            
            html += f"""
                <p><strong>Portfolio Value:</strong> ${summary.portfolio_value:,.2f}</p>
            </div>
            """
        
        # Add aggregated Final Holdings section (once for all portfolios)
        # Aggregate allocations across all portfolios
        aggregated_allocations = {}
        for summary in multi_summary.portfolios.values():
            for allocation in summary.final_allocations:
                symbol = allocation.symbol
                if symbol in aggregated_allocations:
                    # Sum quantities and market values for overlapping symbols
                    aggregated_allocations[symbol].quantity += allocation.quantity
                    aggregated_allocations[symbol].market_value += allocation.market_value
                    # Use the latest price (they should be the same anyway)
                    aggregated_allocations[symbol].current_price = allocation.current_price
                else:
                    # Create a copy to avoid modifying the original
                    from ..broker.models import Allocation
                    aggregated_allocations[symbol] = Allocation(
                        symbol=allocation.symbol,
                        quantity=allocation.quantity,
                        current_price=allocation.current_price,
                        market_value=allocation.market_value
                    )
        
        if aggregated_allocations:
            html += """
            <div class="portfolio-section">
                <h3>Final Holdings (All Portfolios)</h3>
                <table>
                    <tr>
                        <th>Symbol</th>
                        <th>Quantity</th>
                        <th>Current Price</th>
                        <th>Market Value</th>
                    </tr>
            """
            
            # Sort by symbol for consistent display
            for symbol in sorted(aggregated_allocations.keys()):
                allocation = aggregated_allocations[symbol]
                html += f"""
                    <tr>
                        <td>{allocation.symbol}</td>
                        <td>{allocation.quantity:.2f}</td>
                        <td>${allocation.current_price:.2f}</td>
                        <td>${allocation.market_value:.2f}</td>
                    </tr>
                """
            
            total_portfolio_value = sum(alloc.market_value for alloc in aggregated_allocations.values())
            html += f"""
                </table>
                <p><strong>Total Portfolio Value:</strong> ${total_portfolio_value:,.2f}</p>
            </div>
            """
        
        html += """
        </body>
        </html>
        """
        
        return html
    
    def _format_trade_summary_text(
        self,
        trade_summary: Union[TradeSummary, MultiPortfolioSummary],
        leaderboard_symbols: Optional[List[str]] = None,
        portfolio_leaderboards: Optional[Dict[str, List[str]]] = None,
        portfolio_ownership: Optional[Dict[str, Dict[str, Dict[str, float]]]] = None,
        pre_trade_performance: Optional[MultiPortfolioSummary] = None,
    ) -> str:
        """Format trade summary as plain text email."""
        # Check if it's multi-portfolio summary
        if isinstance(trade_summary, MultiPortfolioSummary):
            return self._format_multi_portfolio_text(trade_summary, portfolio_leaderboards or {}, portfolio_ownership, pre_trade_performance)
        
        # Single portfolio format
        text = f"""
Portfolio Rebalancing Summary
Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Leaderboard Top 5: {', '.join(leaderboard_symbols or [])}

"""
        
        if trade_summary.sells:
            text += "Stocks Sold:\n"
            for sell in trade_summary.sells:
                text += f"  - {sell['symbol']}: {sell['quantity']:.2f} shares, ${sell['proceeds']:.2f}\n"
            text += "\n"
        
        if trade_summary.buys:
            text += "Stocks Bought:\n"
            for buy in trade_summary.buys:
                text += f"  - {buy['symbol']}: {buy['quantity']:.2f} shares, ${buy['cost']:.2f}\n"
            text += "\n"
        
        text += "Final Portfolio:\n"
        for allocation in trade_summary.final_allocations:
            text += f"  - {allocation.symbol}: {allocation.quantity:.2f} shares @ ${allocation.current_price:.2f} = ${allocation.market_value:.2f}\n"
        
        text += f"\nTotal Portfolio Value: ${trade_summary.portfolio_value:.2f}\n"
        
        return text
    
    def _format_multi_portfolio_text(
        self,
        multi_summary: MultiPortfolioSummary,
        portfolio_leaderboards: Dict[str, List[str]],
        portfolio_ownership: Optional[Dict[str, Dict[str, Dict[str, float]]]] = None,
        pre_trade_performance: Optional[MultiPortfolioSummary] = None,
    ) -> str:
        """Format multi-portfolio summary as plain text email."""
        text = f"""
Portfolio Rebalancing Summary - Multi-Portfolio
Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Note: Trades are queued and will execute when filled. Performance metrics will be updated once trades are executed.

{f'''
=== Current Performance (Before Trades) ===
Total Initial Capital: ${pre_trade_performance.total_initial_capital:,.2f}
Total Net Invested: ${pre_trade_performance.total_net_invested:,.2f}
Total Current Value: ${pre_trade_performance.total_current_value:,.2f}
Overall Return: ${pre_trade_performance.overall_return:,.2f} ({pre_trade_performance.overall_return_pct:.2f}%)

''' if pre_trade_performance else ''}
=== Trades Status Summary ===
"""
        
        # Calculate trade status summary
        for portfolio_name, summary in multi_summary.portfolios.items():
            submitted_sells_count = len([s for s in summary.sells if s.get('status') == 'submitted'])
            submitted_buys_count = len([b for b in summary.buys if b.get('status') == 'submitted'])
            failed_count = len(summary.failed_trades) if summary.failed_trades else 0
            
            text += f"""
{portfolio_name}:
  Submitted Sells: {submitted_sells_count}
  Submitted Buys: {submitted_buys_count}
  Failed Trades: {failed_count}
"""
        
        text += """
=== Trade Details ===

=== Portfolio Performance Summary (Current Holdings) ===
"""
        
        # Use pre-trade performance if available, otherwise fall back to multi_summary
        performance_data = pre_trade_performance.performances if pre_trade_performance else multi_summary.performances
        
        for portfolio_name, performance in performance_data.items():
            text += f"""
{portfolio_name}:
  Initial Capital: ${performance.initial_capital:,.2f}
  Current Value: ${performance.current_value:,.2f}
  Return: ${performance.total_return:,.2f} ({performance.total_return_pct:.2f}%)
  Realized P&L: ${performance.realized_pnl:,.2f}
  Unrealized P&L: ${performance.unrealized_pnl:,.2f}
"""
        
        # Add individual portfolio details
        for portfolio_name, summary in multi_summary.portfolios.items():
            leaderboard_symbols = portfolio_leaderboards.get(portfolio_name, [])
            performance = multi_summary.performances[portfolio_name]
            
            text += f"""
=== {portfolio_name} Portfolio Details ===
Leaderboard Top 5: {', '.join(leaderboard_symbols)}
Performance: ${performance.total_return:,.2f} ({performance.total_return_pct:.2f}%)

"""
            
            # Group trades by status
            planned_sells = [s for s in summary.sells if s.get('status') == 'planned']
            submitted_sells = [s for s in summary.sells if s.get('status') == 'submitted']
            failed_sells = [s for s in summary.sells if s.get('status') == 'failed']
            
            planned_buys = [b for b in summary.buys if b.get('status') == 'planned']
            submitted_buys = [b for b in summary.buys if b.get('status') == 'submitted']
            failed_buys = [b for b in summary.buys if b.get('status') == 'failed']
            
            # Show failed trades prominently first
            if failed_sells or failed_buys or (summary.failed_trades and len(summary.failed_trades) > 0):
                text += "⚠️ FAILED TRADES:\n"
                for trade in (summary.failed_trades or []):
                    action = trade.get('action', 'UNKNOWN')
                    symbol = trade.get('symbol', '')
                    quantity = trade.get('quantity', 0.0)
                    cost_or_proceeds = trade.get('cost') or trade.get('proceeds', 0.0)
                    error = trade.get('error', 'Unknown error')
                    text += f"  - {action} {symbol}: {quantity:.2f} shares, ${cost_or_proceeds:.2f} - ERROR: {error}\n"
                text += "\n"
            
            # Show submitted trades
            if submitted_sells:
                text += "✅ Stocks Sold (Submitted):\n"
                for sell in submitted_sells:
                    order_id = sell.get('order_id', 'N/A')
                    text += f"  - {sell['symbol']}: {sell['quantity']:.2f} shares, ${sell['proceeds']:.2f} [Order ID: {order_id}]\n"
                text += "\n"
            
            if submitted_buys:
                text += "✅ Stocks Bought (Submitted):\n"
                for buy in submitted_buys:
                    order_id = buy.get('order_id', 'N/A')
                    text += f"  - {buy['symbol']}: {buy['quantity']:.2f} shares, ${buy['cost']:.2f} [Order ID: {order_id}]\n"
                text += "\n"
            
            # Show planned trades
            if planned_sells:
                text += "📋 Stocks to Sell (Planned):\n"
                for sell in planned_sells:
                    text += f"  - {sell['symbol']}: {sell['quantity']:.2f} shares, ${sell['proceeds']:.2f} [Planned]\n"
                text += "\n"
            
            if planned_buys:
                text += "📋 Stocks to Buy (Planned):\n"
                for buy in planned_buys:
                    text += f"  - {buy['symbol']}: {buy['quantity']:.2f} shares, ${buy['cost']:.2f} [Planned]\n"
                text += "\n"
            
            # Legacy support: if no status field, show all trades as submitted
            if not any(s.get('status') for s in summary.sells) and summary.sells:
                text += "Stocks Sold:\n"
                for sell in summary.sells:
                    text += f"  - {sell['symbol']}: {sell['quantity']:.2f} shares, ${sell['proceeds']:.2f}\n"
                text += "\n"
            
            if not any(b.get('status') for b in summary.buys) and summary.buys:
                text += "Stocks Bought:\n"
                for buy in summary.buys:
                    text += f"  - {buy['symbol']}: {buy['quantity']:.2f} shares, ${buy['cost']:.2f}\n"
                text += "\n"
            
            # Add current holdings with purchase prices and gains
            if summary.final_allocations:
                ownership_data = (portfolio_ownership or {}).get(portfolio_name, {})
                text += "Current Holdings:\n"
                for allocation in summary.final_allocations:
                    symbol = allocation.symbol.upper()
                    ownership = ownership_data.get(symbol, {})
                    avg_price = ownership.get('avg_price', 0.0)
                    cost_basis = ownership.get('total_cost', 0.0)
                    
                    # If we don't have ownership data, use current price as estimate
                    if avg_price == 0.0 and allocation.current_price > 0:
                        avg_price = allocation.current_price
                        cost_basis = allocation.market_value
                    
                    gain_loss = allocation.market_value - cost_basis
                    gain_pct = (gain_loss / cost_basis * 100) if cost_basis > 0 else 0.0
                    gain_sign = "+" if gain_loss >= 0 else ""
                    
                    text += f"  - {allocation.symbol}: {allocation.quantity:.2f} shares\n"
                    text += f"    Purchase Price: ${avg_price:.2f} | Current Price: ${allocation.current_price:.2f}\n"
                    text += f"    Cost Basis: ${cost_basis:.2f} | Market Value: ${allocation.market_value:.2f}\n"
                    text += f"    Gain/Loss: {gain_sign}${gain_loss:.2f} ({gain_sign}{gain_pct:.2f}%)\n"
                text += "\n"
            
            text += f"Portfolio Value: ${summary.portfolio_value:,.2f}\n"
        
        # Add aggregated Final Holdings section (once for all portfolios)
        # Aggregate allocations across all portfolios
        aggregated_allocations = {}
        for summary in multi_summary.portfolios.values():
            for allocation in summary.final_allocations:
                symbol = allocation.symbol
                if symbol in aggregated_allocations:
                    # Sum quantities and market values for overlapping symbols
                    aggregated_allocations[symbol].quantity += allocation.quantity
                    aggregated_allocations[symbol].market_value += allocation.market_value
                    # Use the latest price (they should be the same anyway)
                    aggregated_allocations[symbol].current_price = allocation.current_price
                else:
                    # Create a copy to avoid modifying the original
                    from ..broker.models import Allocation
                    aggregated_allocations[symbol] = Allocation(
                        symbol=allocation.symbol,
                        quantity=allocation.quantity,
                        current_price=allocation.current_price,
                        market_value=allocation.market_value
                    )
        
        if aggregated_allocations:
            text += "\n=== Final Holdings (All Portfolios) ===\n"
            # Sort by symbol for consistent display
            for symbol in sorted(aggregated_allocations.keys()):
                allocation = aggregated_allocations[symbol]
                text += f"  - {allocation.symbol}: {allocation.quantity:.2f} shares @ ${allocation.current_price:.2f} = ${allocation.market_value:.2f}\n"
            
            total_portfolio_value = sum(alloc.market_value for alloc in aggregated_allocations.values())
            text += f"\nTotal Portfolio Value: ${total_portfolio_value:,.2f}\n"

        return text

    def send_trades_submitted_email(
        self,
        recipient: str,
        portfolio_name: str,
        trades: List[Dict[str, Any]],
    ) -> bool:
        """
        Send email when trades are submitted to broker.

        Args:
            recipient: Email recipient address
            portfolio_name: Portfolio name
            trades: List of trades with {symbol, action, amount, broker_order_id}

        Returns:
            True if email sent successfully, False otherwise
        """
        date_str = datetime.now().strftime('%Y-%m-%d')
        subject = f"[QMS Bot] Trades Submitted - {portfolio_name} - {date_str}"

        # Build HTML content
        html = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; }}
                h2 {{ color: #333; }}
                table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
                th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
                th {{ background-color: #4CAF50; color: white; }}
                .info {{ background-color: #e7f3fe; padding: 15px; margin: 20px 0; border-left: 4px solid #2196F3; }}
            </style>
        </head>
        <body>
            <h2>Trades Submitted - {portfolio_name}</h2>
            <p><strong>Date:</strong> {date_str}</p>

            <div class="info">
                <p>The following trades have been submitted to the broker. They will be checked for fills on subsequent runs.</p>
            </div>

            <h3>Submitted Trades</h3>
            <table>
                <tr>
                    <th>Symbol</th>
                    <th>Action</th>
                    <th>Amount</th>
                    <th>Order ID</th>
                </tr>
        """

        for trade in trades:
            html += f"""
                <tr>
                    <td>{trade.get('symbol', 'N/A')}</td>
                    <td>{trade.get('action', 'N/A')}</td>
                    <td>${trade.get('amount', 0):.2f}</td>
                    <td>{trade.get('broker_order_id', 'N/A')}</td>
                </tr>
            """

        html += """
            </table>
            <p><em>Waiting for fills...</em></p>
        </body>
        </html>
        """

        # Build text content
        text = f"""Trades Submitted - {portfolio_name}
Date: {date_str}

The following trades have been submitted to the broker:

"""
        for trade in trades:
            text += f"  - {trade.get('action', 'N/A')} {trade.get('symbol', 'N/A')}: ${trade.get('amount', 0):.2f} (Order ID: {trade.get('broker_order_id', 'N/A')})\n"

        text += "\nWaiting for fills...\n"

        return self._send_email(recipient, subject, text, html)

    def send_trades_finalized_email(
        self,
        recipient: str,
        portfolio_results: Dict[str, Dict[str, Any]],
        filled_trades: Optional[List[Dict[str, Any]]] = None,
        failed_trades: Optional[List[Dict[str, Any]]] = None,
    ) -> bool:
        """
        Send email when all trades have reached terminal status.

        Args:
            recipient: Email recipient address
            portfolio_results: Dict of portfolio_name -> execution run data
            filled_trades: Optional list of filled trade details
            failed_trades: Optional list of failed trade details

        Returns:
            True if email sent successfully, False otherwise
        """
        date_str = datetime.now().strftime('%Y-%m-%d')

        # Determine if single or multi-portfolio
        portfolio_names = list(portfolio_results.keys())
        if len(portfolio_names) == 1:
            subject = f"[QMS Bot] Trades Complete - {portfolio_names[0]} - {date_str}"
        else:
            subject = f"[QMS Bot] Trades Complete - {date_str}"

        # Calculate totals
        total_planned = sum(r.get('trades_planned', 0) for r in portfolio_results.values())
        total_filled = sum(r.get('trades_filled', 0) for r in portfolio_results.values())
        total_failed = sum(r.get('trades_failed', 0) for r in portfolio_results.values())

        # Build HTML content
        html = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; }}
                h2 {{ color: #333; }}
                table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
                th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
                th {{ background-color: #4CAF50; color: white; }}
                .summary {{ background-color: #f2f2f2; padding: 15px; margin: 20px 0; }}
                .positive {{ color: #4CAF50; font-weight: bold; }}
                .negative {{ color: #f44336; font-weight: bold; }}
            </style>
        </head>
        <body>
            <h2>Trading Complete - {date_str}</h2>

            <div class="summary">
                <h3>Summary</h3>
                <p><strong>Total Trades Planned:</strong> {total_planned}</p>
                <p><strong>Total Trades Filled:</strong> <span class="positive">{total_filled}</span></p>
                <p><strong>Total Trades Failed:</strong> <span class="{'negative' if total_failed > 0 else ''}">{total_failed}</span></p>
            </div>

            <h3>Portfolio Details</h3>
            <table>
                <tr>
                    <th>Portfolio</th>
                    <th>Status</th>
                    <th>Planned</th>
                    <th>Filled</th>
                    <th>Failed</th>
                </tr>
        """

        for portfolio_name, run in portfolio_results.items():
            status = run.get('status', 'unknown')
            status_class = 'positive' if status == 'completed' else 'negative'
            failed = run.get('trades_failed', 0)
            failed_class = 'negative' if failed > 0 else ''

            html += f"""
                <tr>
                    <td><strong>{portfolio_name}</strong></td>
                    <td class="{status_class}">{status}</td>
                    <td>{run.get('trades_planned', 0)}</td>
                    <td class="positive">{run.get('trades_filled', 0)}</td>
                    <td class="{failed_class}">{failed}</td>
                </tr>
            """

        html += """
            </table>
        """

        # Add filled trades details if provided
        if filled_trades:
            html += """
            <h3>Filled Trades</h3>
            <table>
                <tr>
                    <th>Symbol</th>
                    <th>Action</th>
                    <th>Quantity</th>
                    <th>Price</th>
                    <th>Total</th>
                </tr>
            """
            for trade in filled_trades:
                html += f"""
                <tr>
                    <td>{trade.get('symbol', 'N/A')}</td>
                    <td>{trade.get('action', 'N/A')}</td>
                    <td>{trade.get('quantity', 0):.2f}</td>
                    <td>${trade.get('price', 0):.2f}</td>
                    <td>${trade.get('total', 0):.2f}</td>
                </tr>
                """
            html += "</table>"

        # Add failed trades details if provided
        if failed_trades:
            html += """
            <h3>Failed Trades</h3>
            <table style="border: 2px solid #f44336;">
                <tr>
                    <th>Symbol</th>
                    <th>Action</th>
                    <th>Error</th>
                </tr>
            """
            for trade in failed_trades:
                html += f"""
                <tr>
                    <td>{trade.get('symbol', 'N/A')}</td>
                    <td>{trade.get('action', 'N/A')}</td>
                    <td style="color: #f44336;">{trade.get('error', 'Unknown error')}</td>
                </tr>
                """
            html += "</table>"

        html += """
        </body>
        </html>
        """

        # Build text content
        text = f"""Trading Complete - {date_str}

Summary:
  Total Trades Planned: {total_planned}
  Total Trades Filled: {total_filled}
  Total Trades Failed: {total_failed}

Portfolio Details:
"""
        for portfolio_name, run in portfolio_results.items():
            text += f"""
{portfolio_name}:
  Status: {run.get('status', 'unknown')}
  Planned: {run.get('trades_planned', 0)}
  Filled: {run.get('trades_filled', 0)}
  Failed: {run.get('trades_failed', 0)}
"""

        if filled_trades:
            text += "\nFilled Trades:\n"
            for trade in filled_trades:
                text += f"  - {trade.get('action', 'N/A')} {trade.get('symbol', 'N/A')}: {trade.get('quantity', 0):.2f} @ ${trade.get('price', 0):.2f} = ${trade.get('total', 0):.2f}\n"

        if failed_trades:
            text += "\nFailed Trades:\n"
            for trade in failed_trades:
                text += f"  - {trade.get('action', 'N/A')} {trade.get('symbol', 'N/A')}: {trade.get('error', 'Unknown error')}\n"

        return self._send_email(recipient, subject, text, html)
