# The World Archive

*A chronological, point-in-time record of the world outside our own trades.*

Operator, 2026-09-15: *"Este modelo de comportamiento de la economía a nivel mundial quiero
que lo estructures de forma excelente. No solo va a formar parte ya de este sistema de
trading, sino que probablemente lo vamos a extraer y lo vamos a colocar dentro del sistema de
backtesting. Porque igualmente puede servir para cualquier sistema futuro. Piensa que al final
es un almacén de datos de todas las noticias del pasado ordenadas por orden cronológico. El
valor de todos los assets, de todos los indicadores. Entonces, una vez tengamos todo eso, lo
podremos aprovechar mil y una veces."*

---

## 1. What this is, in one paragraph

Every number this laboratory has ever downloaded describes a moment in the past. Almost none
of it records **when we could first have known it**, and that single missing column is the
difference between a macro layer and a leak. The World Archive stores both: what a figure
*refers to*, and when it *became knowable*. On top of that it keeps the thing we have never
had at all — a chronological event and news record — in the same shape, under the same clock.
It is a library, not a strategy. It answers exactly one question, and answers it the same way
for every system that will ever ask: **what did the world look like on day D, to someone
standing on day D?**

## 2. Why it is a separate package

1. **It outlives systems.** System 08 was closed on 2026-09-14. Its data should not have been
   inside it. Every series this lab paid for belongs somewhere that survives the strategy that
   happened to need it first.
2. **It is where "no peeking" can be made structural.** A convention that each consumer must
   remember to shift a series by its publication lag will be forgotten, and has been. Here the
   lag is not optional: the reader cannot return an observation stamped later than the day
   being asked about.
3. **It is the expensive half.** Downloading, de-duplicating, aligning calendars, measuring
   release delays, reconciling sources that disagree — that work is worth doing once, and is
   worth nothing if it has to be redone per system.

The package depends on the standard library, `numpy`, and (only for adoption of legacy files)
`quantlab_catalog`. It has no idea that a trading system exists. Extracting it into the
backtester is a directory move and an import rename, deliberately.

## 3. The two record shapes, and nothing else

Everything in the archive is one of exactly two things.

**An observation** — a number about a moment:

| field | meaning |
|---|---|
| `stream_id` | which series, e.g. `us.cpi.headline`, `crypto.btc.price` |
| `ref_date` | the date the number *describes* (the CPI reading *for* March) |
| `known_at` | the date it *became knowable* (the March CPI *released* on 10 April) |
| `value` | the number |
| `vintage` | `observed` if the source gave a real release date, `estimated` if we derived it from the declared lag, `assumed` if the stream is same-day by nature (a closing price) |

**An event** — a fact about a moment, in words:

| field | meaning |
|---|---|
| `event_id` | stable hash of source + timestamp + headline |
| `ref_ts` | when the thing happened |
| `known_at` | when it was published — for news, and only for news, these are the same and both are exact |
| `category` | see the taxonomy below |
| `jurisdiction` | `US`, `CN`, `EZ`, … or `global` |
| `entities` | `["BTC", "SEC", "Binance"]` |
| `headline`, `body`, `url`, `source` | the text and its provenance |
| `weight` | how much the archive believes it mattered, 0-1; hand-set for the curated timeline, source-derived for feeds |

A derived series computed *from* events (daily tone for China, count of US enforcement actions
in the last 30 days) is an **observation stream** like any other, with its own id and its own
clock. That is the rule that keeps text out of the hot path: a model consumes streams; only
the archive consumes text.

## 4. The four pillars

```
quantlab_world/
    streams.py      THE REGISTRY   what exists, where it comes from, how late it arrives
    clock.py        THE CLOCK      known_at resolution; the as-of rule, enforced
    store.py        THE STORE      append-only bitemporal storage + manifest, never in git
    panel.py        THE PANEL      (days x streams) matrices, lagged and made stationary
    events.py       THE CHRONICLE  the event/news record and the streams derived from it
    transform.py                   level -> stationary, one named function per transform
    inventory.py                   what is here, what is missing, coverage by region
    ingest/                        deliberate downloaders, one per source, never at read time
```

### 4.1 The registry is code; the data is not

`streams.py` declares every stream in Python — id, title, category, region, unit, frequency,
publication lag, source, default transform, and the adapter that reads it. That file is
committed and reviewable: a disagreement about whether the Fed's balance sheet is nine days
late is a diff, not an argument. The **observations are never committed** — they live under
`backtester/data/world/`, gitignored and re-downloadable, like every other store in this lab.

### 4.2 The clock is the product

Three lag regimes, named rather than blurred:

- **`observed`** — the source publishes a release timestamp (news; FRED/ALFRED vintages; ETF
  flow reports). Use it verbatim. This is the only regime with no modelling in it.
- **`estimated`** — the source gives only the latest revision, so `known_at = ref_date + lag`,
  with the lag taken from the measured table where system 06 measured one and set to *at least
  the release cadence* where it did not. Conservative by construction: it is better to be a
  week late than one day early.
- **`assumed`** — the observation is knowable at its own timestamp because it *is* the event
  (a closing price, an on-chain block, a funding rate). Lag zero, declared explicitly so that
  "zero" is a decision rather than a default.

A stream with no lag declaration is a **hard error at registry load**, not a silent zero.

Revisions are a separate axis and the archive is honest about them: with free sources we
almost always hold *the latest revision only*, which means a backtest reading GDP for 2021 is
reading a number that was revised twice since. Where vintages are available (ALFRED) the store
keeps them; where they are not, the stream is flagged `revised: true` and `inventory` prints
the flag, so a system that cares can exclude them.

### 4.3 The store: append-only, one file per stream

```
backtester/data/world/
    manifest.json               every stream: rows, first, last, sha256, fetched_at
    series/<stream_id>.json     {"id":…, "meta":{…}, "obs":[[ref_date, value, known_at], …]}
    events/<YYYY>.jsonl         one event per line, sorted by ref_ts
    vintages/<stream_id>.json   only where the source gives real vintages
```

JSON, deliberately: `pyarrow` is not installed on this machine, every other store in the lab
is JSON, and the whole series archive is small (tens of MB). The **events** store is JSONL
because it grows without bound and must be appendable and streamable. If the news feed makes
the store large enough to matter, the format changes behind `store.py` and no consumer notices
— which is the point of having a `store.py` at all.

### 4.4 The panel is the only thing a model sees

```python
import quantlab_world as W

W.asof("2023-06-14")                      # dict: every stream knowable that day
W.panel(days, streams=W.CATEGORY["inflation"])   # (len(days), n) float32, aligned + lagged
W.events(since="2023-06-01", until="2023-06-14", category="regulation")
W.coverage()                              # what exists, per region and per decade
```

Panels are **stationary by default**: rates of change, differences, percentile ranks of a
stream against its own trailing window. Levels are available but must be asked for by name,
because a model given the level of the balance sheet learns the calendar.

## 5. Taxonomy — the axes that make it reusable

**Category** `rates · inflation · money · credit · fx · equity · commodity · activity ·
housing · trade · crypto_price · crypto_supply · crypto_onchain · crypto_flow · crypto_deriv ·
sentiment · policy · regulation · security_incident · adoption`

**Region** `US · EZ · DE · UK · JP · CN · IN · BR · KR · TR · AR · ZA · CA · AU · CH ·
global · offshore`

**Frequency** `D · B (business days) · W · M · Q · A · irregular`

**Transform** `level · diff · log_change · pct_change · percentile · zscore · ratio ·
real_rate · spread · yoy`

The regional axis is the operator's own point and the one a single global CPI cannot express:
*"an investor in Shanghai and one in Frankfurt do not face the same decision"*. A stream
carries its region so that "real rate, by region" is a query rather than a project.

## 6. The news layer, built in three tiers

This is the part that does not exist yet anywhere on this machine, and the part most likely to
be over-promised. It is therefore specified as three tiers that can be delivered and used
independently, cheapest and most reliable first.

**Tier 1 — the curated chronicle (small, exact, immediately useful).** A hand-written,
source-linked timeline of the events that actually moved this market: Mt. Gox, the 2017 ICO
ban, the 2021 China mining ban, Terra/Luna, 3AC, FTX, the ETF approvals, each halving, every
major exchange hack, every significant enforcement action. A few hundred rows. High precision,
zero licensing risk, and enough on its own to answer "was this drawdown a regime break or a
Tuesday". Written in `events.py` as data, versioned in git because it is *editorial*, not
downloaded.

**Tier 2 — machine event feeds.** GDELT 2.0 is free, covers 2015 onward, and gives event
counts and tone by country and theme at 15-minute granularity; Wikipedia pageview counts are
free and are a usable proxy for public attention by topic and language. Neither is news text
we have to relicense, and both reduce to *streams* — `cn.news.tone.finance`,
`global.attention.bitcoin` — which is the form the models want anyway.

**Tier 3 — full text.** Only if tiers 1 and 2 prove insufficient, and only from sources whose
terms allow storage. The design admits it (the event record has `body` and `url`); nothing
depends on it.

Tier 1 is committed with the code. Tiers 2 and 3 land in `events/<year>.jsonl` and never in git.

## 7. Invariants, stated once and enforced in code

1. **Nothing here downloads at read time.** Fetching is `python -m quantlab_world.ingest.<src>`
   and nothing else. A backtest that reaches the internet halfway through is not a backtest.
2. **`asof(D)` never returns an observation with `known_at > D`.** Not by convention — the
   reader filters, and the filter is the only path to a value.
3. **A stream without a declared publication lag cannot be registered.**
4. **The 2026 lock applies here too.** The archive knows the sealed boundary and refuses to
   hand a research reader anything on the far side of it.
5. **No data file is ever committed.** Registry, chronicle and code are; observations are not.
6. **Sources that disagree are recorded as disagreeing.** The supply calibration in system 09
   already taught us this: XRP's float is 60.7bn or 100.0bn depending on whom you ask, and a
   store that silently picks one is lying. Multi-source streams keep every reading and expose
   the spread.

## 8. Migration: adoption, not copying

On day one the archive holds no new downloads. Every series the catalogue already has is
*adopted* — declared in the registry with an adapter that reads the existing file through
`quantlab_catalog`:

| already on disk | streams |
|---|---|
| `reference_markets.json` | 39 FRED series: US/EZ/CN/JP/IN/BR/UK/TR/ZA inflation, rates, curve, dollar, six FX pairs, VIX, HY spread, SPX, Nasdaq, Nikkei, oil, WALCL, RRP, M2 |
| `funding_*.json` | 14 perpetual funding streams |
| `feargreed.json` | crowd sentiment, daily from 2018-02 |
| `chain_*.json` | 5 Bitcoin on-chain series |
| `market_cap_full.json`, `circulating_supply.json`, `global_market_cap.json` | 14 asset caps + supply + the global cap |
| `stablecoin_supply.json`, `etf_flow_btc.json`, `oi_*.json` | the flow channel |
| Binance candles via `quantlab_catalog.candles` | 27 pairs, 15m, as daily closes in the archive |

That is ~100 streams before a single new request. The new downloads are then a *list*, not a
rewrite: regional equity and rates beyond the G7, commodity complex, GDELT tone, Wikipedia
attention, ALFRED vintages for the series that are heavily revised.

## 9. What this buys, concretely

- System 09's `world.py` becomes a *view* over the archive instead of its own private loader.
- The market-direction head gets inflation, real rates and attention **by region**, which is
  what it was missing when it scored −0.23% across the selection years.
- Any future system starts with a world, on a clock, for free.
- And the one question we could never answer — *was the model wrong, or was the world
  surprising?* — becomes answerable, because the surprises are on file in chronological order.

---

*Status: design fixed 2026-09-15. Build order in `.meshkore/modules/trading-system/tasks/`
task `WORLD-1`.*
