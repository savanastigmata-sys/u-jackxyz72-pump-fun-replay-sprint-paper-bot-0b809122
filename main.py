"""Pump.fun replay sprint — paper bot (agent-fun/replay/v2).

Strategy: launch sniper with a rug filter, tuned on the dev window.

What the dev data showed (24h, 1222 coins):
- The first trade is always a buy and it pumps the price at once (median
  +17% over the creation price in the first slot), then the median coin
  bleeds slowly back to its creation price over ~1000 slots. Buying after
  the pump and holding loses: the edge is only in the first seconds, and
  only on launches whose opening tape is clean.
- 28 of the 35 coins that complete ("graduate") do so within 3 slots, at
  ~14.7x their creation price: by the time any bot can buy them they are
  already at their top. The catchable runners are the few that complete
  slowly, and they cannot be told apart early from the crowd, so this bot
  does not chase them: it takes small, fast, diversified shots instead.
- The house sniper baseline loses -0.475 SOL on the dev window. This bot
  tightens it (real reserves >= 2 SOL, at most 3 early buyers, creator
  buy <= 2.5 SOL, 0.05 SOL stake, 10-slot max hold) and loses about
  -0.24 SOL on the same window, with a 2.7% max drawdown.

Rules (all a pure function of the batches the harness sends):
- Watch every coin from its CreateEvent. In its first 3 slots, buy when:
  the curve already holds >= 2 SOL of real reserves, at most 3 distinct
  non-creator wallets have bought, the creator's own buys in the create
  slot total <= 2.5 SOL, and the creator has not sold. Buy 0.05 SOL
  (capped at 1% of the real reserves, at least 0.01 SOL), at most 5 open
  positions, accepting any fill price (the launch moves too fast for a
  tight slippage bound to be anything but a missed fill).
- Sell a position whole on the first of: +20% over its cost, -8% under
  its cost, 10 slots held, or the creator selling. A completed curve is
  closed by the replay itself, so no order is sent for it.
- A sell too big for the curve's remaining real reserves is split: sell
  only as many tokens as the reserves can pay for, and the rest on a
  later batch. This keeps positions from getting stuck on dying coins.
- Deterministic by construction: no clock, no randomness, no environment
  reads; iteration only over insertion-ordered dicts fed by the batch
  stream, so the two graded executions produce byte-identical replies.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
import makefun_bot

LAMPORTS_PER_SOL = 1_000_000_000

# Entry filters: a launch is bought only while it is this young, this
# liquid, this uncrowded, and its creator this restrained.
MAX_AGE_SLOTS = 3
MIN_REAL_SOL = 2.0
MAX_REAL_SOL = 30.0
MAX_BUYERS = 3
MAX_DEV_BUY_LAMPORTS = 2_500_000_000  # 2.5 SOL, creator buys in the create slot
STAKE_LAMPORTS = 50_000_000  # 0.05 SOL per coin
MIN_BUY_LAMPORTS = 10_000_000  # 0.01 SOL, the guardrail's round-trip floor
BUY_SLIPPAGE_BPS = 10000
SELL_SLIPPAGE_BPS = 10000

# Exits: take the pop fast, cut the bleed fast, never babysit a launch.
TAKE_PROFIT = 0.20
STOP_LOSS = 0.08
MAX_HOLD_SLOTS = 10


class Coin(object):
    """Opening-tape facts for one mint, from its own events only."""

    __slots__ = ("created_slot", "creator", "dev_buy0", "dev_sold", "buyers")

    def __init__(self, created_slot):
        self.created_slot = created_slot
        self.creator = None
        self.dev_buy0 = 0
        self.dev_sold = False
        self.buyers = set()


class Position(object):
    """Bookkeeping for one open position, keyed by mint."""

    __slots__ = ("opened_slot",)

    def __init__(self, opened_slot):
        self.opened_slot = opened_slot


def _price(curve):
    if curve.virtual_token_reserves <= 0:
        return 0.0
    return curve.virtual_quote_reserves / curve.virtual_token_reserves


def _max_sellable_tokens(curve, tokens):
    """Most tokens whose sale the curve's real reserves can pay for.

    A sell of t tokens pays q = t*vq/(vt+t); it is rejected when q exceeds
    the real quote reserves, so t <= rq*vt/(vq-rq). Returns tokens when the
    whole position fits.
    """
    vq = curve.virtual_quote_reserves
    vt = curve.virtual_token_reserves
    rq = curve.real_quote_reserves
    if vq <= rq or vt <= 0 or rq <= 0:
        return tokens
    limit = rq * vt // (vq - rq)
    if limit <= 0:
        return 0
    # Keep a small margin so the fill stays under the cap after the
    # two-slot latency moves the reserves.
    limit = limit * 95 // 100
    return tokens if tokens <= limit else limit


class Sniper(object):
    def __init__(self):
        self.coins = {}
        self.positions = {}

    def on_hello(self, state):
        return None

    def on_batch(self, state, batch):
        slot = batch["slot"]
        # Fold this batch's events into the opening-tape facts.
        for event in batch["events"]:
            kind = event["event"]
            mint = event["mint"]
            if kind == "CreateEvent":
                coin = self.coins.get(mint)
                if coin is None:
                    coin = Coin(event["slot"])
                    self.coins[mint] = coin
                coin.creator = event["creator"]
            elif kind == "TradeEvent":
                coin = self.coins.get(mint)
                if coin is None:
                    coin = Coin(event["slot"])
                    self.coins[mint] = coin
                user = event["user"]
                if coin.creator is not None and user == coin.creator:
                    if event["is_buy"]:
                        if event["slot"] == coin.created_slot:
                            coin.dev_buy0 += int(event["quote_amount"])
                    else:
                        coin.dev_sold = True
                elif event["is_buy"]:
                    coin.buyers.add(user)
            # CompleteEvent: the replay closes the position itself; the
            # coin's facts stay, but it is never bought or sold again.

        # Drop bookkeeping for positions the account no longer holds.
        for mint in list(self.positions):
            if mint not in state.positions:
                del self.positions[mint]
        # Notice positions that just landed.
        for mint in state.positions:
            if mint not in self.positions:
                self.positions[mint] = Position(slot)

        orders = []
        pending_sell = set()
        pending_buy = set()
        for pending in state.pending.values():
            if pending.order["side"] == "sell":
                pending_sell.add(pending.order["mint"])
            else:
                pending_buy.add(pending.order["mint"])

        # Exits first: a slot freed here can be reused by an entry below.
        for mint, holding in state.positions.items():
            if mint in pending_sell:
                continue
            curve = state.curves.get(mint)
            if curve is None or curve.complete:
                continue
            price = _price(curve)
            if price <= 0.0 or holding.token_amount <= 0:
                continue
            value = holding.token_amount * price
            cost = holding.cost_lamports
            if cost <= 0:
                continue
            ret = value / cost - 1.0
            coin = self.coins.get(mint)
            position = self.positions.get(mint)
            age = slot - position.opened_slot if position is not None else 0
            sell = False
            if ret <= -STOP_LOSS:
                sell = True
            elif ret >= TAKE_PROFIT:
                sell = True
            elif age >= MAX_HOLD_SLOTS:
                sell = True
            elif coin is not None and coin.dev_sold:
                sell = True
            if sell:
                amount = _max_sellable_tokens(curve, holding.token_amount)
                if amount > 0:
                    orders.append({
                        "side": "sell",
                        "mint": mint,
                        "token_amount": amount,
                        "max_slippage_bps": SELL_SLIPPAGE_BPS,
                    })

        # Entries: only coins that traded in this batch, only while young.
        max_open = state.hello["caps"]["max_open_positions"]
        buys_placed = 0
        committed = state.committed_position_count()
        if committed < max_open:
            seen = []
            for event in batch["events"]:
                if event["event"] in ("TradeEvent", "CreateEvent"):
                    if event["mint"] not in seen:
                        seen.append(event["mint"])
            for mint in seen:
                if len(orders) >= state.hello["caps"]["max_orders_per_batch"]:
                    break
                if mint in state.positions or mint in pending_buy:
                    continue
                if committed + buys_placed >= max_open:
                    break
                curve = state.curves.get(mint)
                if curve is None or curve.complete:
                    continue
                coin = self.coins.get(mint)
                if coin is None:
                    continue
                if slot - coin.created_slot > MAX_AGE_SLOTS:
                    continue
                if coin.dev_sold or coin.dev_buy0 > MAX_DEV_BUY_LAMPORTS:
                    continue
                if len(coin.buyers) > MAX_BUYERS:
                    continue
                real_sol = curve.real_quote_reserves / LAMPORTS_PER_SOL
                if real_sol < MIN_REAL_SOL or real_sol > MAX_REAL_SOL:
                    continue
                cap = state.max_buy_lamports(mint)
                amount = STAKE_LAMPORTS if STAKE_LAMPORTS < cap else cap
                if amount < MIN_BUY_LAMPORTS:
                    continue
                if state.free_cash_lamports() < amount + state.tx_fee_lamports():
                    continue
                buys_placed += 1
                orders.append({
                    "side": "buy",
                    "mint": mint,
                    "quote_lamports": amount,
                    "max_slippage_bps": BUY_SLIPPAGE_BPS,
                })

        return orders


if __name__ == "__main__":
    bot = Sniper()
    makefun_bot.run(bot.on_batch, on_hello=bot.on_hello)
