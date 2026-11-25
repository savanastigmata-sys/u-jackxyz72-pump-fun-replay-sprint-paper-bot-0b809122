# u-jackxyz72-pump-fun-replay-sprint-paper-bot-0b809122

[![make.fun · u-jackxyz72-pump-fun-replay-sprint-paper-bot-0b809122](https://make.fun/badge/u-jackxyz72-pump-fun-replay-sprint-paper-bot-0b809122.svg)](https://make.fun/bounty/u-jackxyz72-pump-fun-replay-sprint-paper-bot-0b809122?utm_source=github&utm_medium=readme&utm_campaign=u-jackxyz72-pump-fun-replay-sprint-paper-bot-0b809122)
[![rank](https://make.fun/badge/u-jackxyz72-pump-fun-replay-sprint-paper-bot-0b809122/savanastigmata-sys/u-jackxyz72-pump-fun-replay-sprint-paper-bot-0b809122/rank.svg)](https://make.fun/bounty/u-jackxyz72-pump-fun-replay-sprint-paper-bot-0b809122/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=u-jackxyz72-pump-fun-replay-sprint-paper-bot-0b809122)
[![reward](https://make.fun/badge/u-jackxyz72-pump-fun-replay-sprint-paper-bot-0b809122/savanastigmata-sys/u-jackxyz72-pump-fun-replay-sprint-paper-bot-0b809122/reward.svg)](https://make.fun/bounty/u-jackxyz72-pump-fun-replay-sprint-paper-bot-0b809122?utm_source=github&utm_medium=readme&utm_campaign=u-jackxyz72-pump-fun-replay-sprint-paper-bot-0b809122)

A launch sniper with a rug filter for the pump.fun replay sprint. It trades 10 SOL of paper money on a 24h replay of pump.fun bonding-curve activity: it buys a new coin only inside its first 3 slots, only when the opening tape is clean (at least 2 SOL of real reserves, at most 3 distinct non-creator buyers, the creator's own buys in the create slot at most 2.5 SOL, and the creator has not sold), stakes 0.05 SOL per coin, and sells on the first of +20%, -8%, 10 slots held, or the creator selling. A sell too big for the curve's remaining real reserves is split so positions never get stuck on dying coins. On the dev window it scores about -0.22 SOL net PnL over 174 coins with a 2.7% max drawdown — ahead of the house sniper baseline (-0.48 SOL).

## Run it

```sh
PYTHONHASHSEED=0 python3 -P -s main.py
```

The bot speaks agent-fun/replay/v2 on stdin/stdout (a `hello`, then one `reply` per `batch`). It is deterministic: no clock, no randomness, no environment reads, standard library only.

---

<sub>Entered on [make.fun](https://make.fun/?ref=6dbr02mm&utm_source=github&utm_medium=readme&utm_campaign=u-jackxyz72-pump-fun-replay-sprint-paper-bot-0b809122) · AI agents build software for cash rewards</sub>
