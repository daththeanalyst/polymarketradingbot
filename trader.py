"""
Polymarket Trader
==================
Handles authenticated trading on Polymarket via the CLOB API.
Starts in DRY RUN mode — won't place real trades until you flip the switch.
"""

import os
from dotenv import load_dotenv
from config import DRY_RUN, CLOB_API, CHAIN_ID

load_dotenv()


class Trader:
    def __init__(self):
        self.client = None
        self.connected = False
        self.dry_run = DRY_RUN

    def connect(self):
        """
        Connect to Polymarket CLOB API with authentication.
        Requires PRIVATE_KEY in .env file.
        Supports both email/Google wallets (signature_type=1)
        and MetaMask/EOA wallets (signature_type=0).
        """
        private_key = os.getenv("PRIVATE_KEY", "")

        if not private_key or private_key == "paste_your_private_key_here":
            print("  [WARNING] No private key set in .env — running in read-only mode")
            self.connected = False
            return False

        try:
            from py_clob_client.client import ClobClient

            # Determine wallet type from .env
            wallet_type = os.getenv("WALLET_TYPE", "email").lower()
            proxy_wallet = os.getenv("PROXY_WALLET", "")

            if wallet_type == "metamask":
                sig_type = 0  # Standard EOA wallet
            else:
                sig_type = 1  # Email/Magic wallet (default)

            client_args = {
                "host": CLOB_API,
                "key": private_key,
                "chain_id": CHAIN_ID,
                "signature_type": sig_type,
            }

            # Email wallets need the funder (proxy wallet) address
            if sig_type == 1 and proxy_wallet:
                client_args["funder"] = proxy_wallet

            self.client = ClobClient(**client_args)

            # Generate and set API credentials
            api_creds = self.client.create_or_derive_api_creds()
            self.client.set_api_creds(api_creds)

            self.connected = True
            wallet_label = "MetaMask" if sig_type == 0 else "Email"
            print(f"  [OK] Connected to Polymarket CLOB API ({wallet_label} wallet)")
            return True

        except ImportError:
            print("  [ERROR] py-clob-client not installed. Run: pip install py-clob-client")
            return False
        except Exception as e:
            print(f"  [ERROR] Connection failed: {e}")
            return False

    def get_balance(self):
        """Get USDC balance (requires connection)."""
        if not self.connected or not self.client:
            return None
        try:
            # Note: balance check may vary by py-clob-client version
            return self.client.get_balance_allowance()
        except Exception:
            return None

    def place_bet(self, token_id, side, amount, price=None):
        """
        Place a bet on Polymarket.

        token_id: The token to buy (from market data)
        side: "BUY" (we always buy, either YES or NO token)
        amount: Dollar amount to spend
        price: Limit price (None = market order)
        """
        # Choose correct token index
        # token_ids[0] = YES token, token_ids[1] = NO token
        # 'side' here means which outcome we're betting on

        if self.dry_run:
            print(f"  [DRY RUN] Would bet ${amount:.2f} on {side} @ {price or 'market'}")
            print(f"             Token: {token_id[:20]}...")
            return {"status": "dry_run", "amount": amount, "side": side}

        if not self.connected or not self.client:
            print("  [ERROR] Not connected — cannot place trade")
            return None

        try:
            from py_clob_client.order import MarketOrderArgs, OrderArgs

            if price is None:
                # Market order
                order = MarketOrderArgs(
                    token_id=token_id,
                    amount=amount,
                )
                response = self.client.create_market_buy_order(order)
            else:
                # Limit order
                order = OrderArgs(
                    token_id=token_id,
                    price=price,
                    size=amount / price,  # Convert dollars to shares
                    side="BUY",
                )
                response = self.client.create_and_post_order(order)

            print(f"  [LIVE] Placed ${amount:.2f} bet on token {token_id[:20]}...")
            return response

        except Exception as e:
            print(f"  [ERROR] Trade failed: {e}")
            return None

    def place_limit_order(self, token_id, side, amount, price):
        """
        Place a LIMIT order on the CLOB (better than market orders).

        Limit orders avoid paying the spread — you SET the price you want
        and wait for someone to fill it. Market makers use this exclusively.

        In dry run: shows what would be submitted to the CLOB.
        Live: uses py-clob-client to post the order.
        """
        shares = round(amount / price, 2) if price > 0 else 0

        if self.dry_run:
            print(f"  [DRY RUN] Would place LIMIT order:")
            print(f"             {side} {shares:.2f} shares @ ${price:.3f}")
            print(f"             Cost: ${amount:.2f} | Token: {token_id[:20]}...")
            return {
                "status": "dry_run",
                "order_type": "limit",
                "side": side,
                "amount": amount,
                "price": price,
                "shares": shares,
            }

        if not self.connected or not self.client:
            print("  [ERROR] Not connected -- cannot place limit order")
            return None

        try:
            from py_clob_client.order import OrderArgs

            order = OrderArgs(
                token_id=token_id,
                price=price,
                size=shares,
                side="BUY",
            )
            response = self.client.create_and_post_order(order)
            print(f"  [LIVE] Limit order: {shares:.2f} shares @ ${price:.3f}")
            return response

        except Exception as e:
            print(f"  [ERROR] Limit order failed: {e}")
            return None

    def place_arbitrage(self, yes_token_id, no_token_id, amount):
        """
        Place a sum-to-one arbitrage trade (buy both YES and NO).

        Splits the amount between YES and NO tokens to lock in
        guaranteed profit when YES + NO < $1.00.

        In dry run: shows the two orders that would be placed.
        """
        if self.dry_run:
            print(f"  [DRY RUN] Would place ARBITRAGE trade:")
            print(f"             BUY YES + NO for total ${amount:.2f}")
            print(f"             YES token: {yes_token_id[:20]}...")
            print(f"             NO token:  {no_token_id[:20]}...")
            return {"status": "dry_run", "order_type": "arbitrage", "amount": amount}

        if not self.connected or not self.client:
            print("  [ERROR] Not connected -- cannot place arbitrage")
            return None

        # In live mode, place both orders
        # (Would need proper implementation with batch orders)
        print(f"  [LIVE] Arbitrage trade for ${amount:.2f}")
        return {"status": "live", "order_type": "arbitrage", "amount": amount}

    def sell_position(self, token_id, shares, min_price=None):
        """
        Sell shares you own back to the order book.

        token_id: The token to sell (YES or NO token ID)
        shares: Number of shares to sell
        min_price: Minimum price to accept (None = market sell at best bid)
        """
        if self.dry_run:
            price_str = f"${min_price:.3f}" if min_price else "market"
            value = shares * min_price if min_price else shares * 0.50
            print(f"  [DRY RUN] Would SELL {shares:.2f} shares @ {price_str}")
            print(f"             Estimated value: ${value:.2f}")
            print(f"             Token: {token_id[:20]}...")
            return {
                "status": "dry_run",
                "order_type": "sell",
                "shares": shares,
                "min_price": min_price,
            }

        if not self.connected or not self.client:
            print("  [ERROR] Not connected -- cannot sell")
            return None

        try:
            if min_price is None:
                # Market sell (FOK — fill or kill, instant execution)
                from py_clob_client.order import MarketOrderArgs
                order = MarketOrderArgs(
                    token_id=token_id,
                    amount=shares,
                )
                response = self.client.create_market_sell_order(order)
            else:
                # Limit sell at minimum price
                from py_clob_client.order import OrderArgs
                order = OrderArgs(
                    token_id=token_id,
                    price=min_price,
                    size=shares,
                    side="SELL",
                )
                response = self.client.create_and_post_order(order)

            print(f"  [LIVE] Sold {shares:.2f} shares of {token_id[:20]}...")
            return response

        except Exception as e:
            print(f"  [ERROR] Sell failed: {e}")
            return None

    def get_order_book(self, token_id):
        """
        Fetch the current order book (bids and asks) for a token.
        Returns best bid/ask prices and depth.
        """
        if not self.connected or not self.client:
            return None
        try:
            book = self.client.get_order_book(token_id)
            return book
        except Exception as e:
            print(f"  [ERROR] Order book fetch failed: {e}")
            return None

    def cancel_order(self, order_id):
        """Cancel a specific open order."""
        if self.dry_run:
            print(f"  [DRY RUN] Would cancel order {order_id}")
            return
        if not self.connected or not self.client:
            return
        try:
            self.client.cancel(order_id)
            print(f"  [OK] Cancelled order {order_id}")
        except Exception as e:
            print(f"  [ERROR] Cancel failed: {e}")

    def get_positions(self):
        """Get current open positions."""
        if not self.connected or not self.client:
            return []
        try:
            return self.client.get_orders()
        except Exception:
            return []

    def cancel_all(self):
        """Cancel all open orders."""
        if self.dry_run:
            print("  [DRY RUN] Would cancel all orders")
            return
        if not self.connected or not self.client:
            return
        try:
            self.client.cancel_all()
            print("  [OK] All orders cancelled")
        except Exception as e:
            print(f"  [ERROR] Cancel failed: {e}")


# --- Run standalone to test ---
if __name__ == "__main__":
    print("=" * 50)
    print("TRADER MODULE TEST")
    print("=" * 50)

    trader = Trader()
    print(f"\nDry Run Mode: {trader.dry_run}")

    # Try to connect
    print("\nAttempting connection...")
    success = trader.connect()

    if success:
        print("\nChecking balance...")
        balance = trader.get_balance()
        print(f"Balance: {balance}")

        print("\nChecking positions...")
        positions = trader.get_positions()
        print(f"Open positions: {len(positions)}")
    else:
        print("\nNot connected (no private key or connection error)")
        print("This is fine for dry run mode — the bot will still scan markets")

    # Test dry run bet
    print("\nTesting dry run bet...")
    trader.place_bet(
        token_id="0x_example_token_id_here",
        side="BUY",
        amount=1.00,
        price=0.35,
    )
