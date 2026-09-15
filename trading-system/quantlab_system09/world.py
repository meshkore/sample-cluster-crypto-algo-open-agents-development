"""H - THE WORLD OUTSIDE CRYPTO, now a VIEW over the shared World Archive.

This module used to own everything: it loaded its own series, kept its own table of
publication lags, and shifted its own columns. All of that now lives in `quantlab_world`,
where it belongs, for two reasons the operator named on 2026-09-15 and one we learned the hard
way:

  * it is reusable - *"lo vamos a extraer y lo vamos a colocar dentro del sistema de
    backtesting... puede servir para cualquier sistema futuro"*. System 08 was closed the day
    before and its data died with it. This will not happen again.
  * the clock belongs in one place. A publication lag applied in two modules is applied twice;
    applied in none, it is a leak that flatters every result it touches. The archive writes
    `known_at` into every row, and the only path to a value goes through it.

WHAT REMAINS HERE is the part that is system 09's own opinion: WHICH channels this system
believes drive the money crossing crypto's boundary, and in what form. That is a modelling
choice, not a data fact, so it stays in the system.

  THE LIQUIDITY BLOCK, `block()` - the original ten. The tide every risk asset floats on, the
  opportunity cost of holding a coin that yields nothing, the dollar, fear, and where risk
  appetite actually breaks first.

  THE REGIONAL BLOCK, `regional()` - new, and the operator's point: *"an investor in Shanghai
  and one in Frankfurt do not face the same decision"*. Every column here is a CURRENCY, a
  local rate or a local market, and that is deliberate rather than a compromise. Free monthly
  inflation for the world is published a year late or not at all - FRED stopped mirroring the
  OECD's national CPI series entirely, Japan's ends in June 2021 - whereas USD/BRL is daily,
  current, never revised and encodes the same decision faster. Inflation is the slow
  confirmation; the currency is the live reading.

WHERE THESE BELONG, which the ablation settled on 2026-09-15: NOT in the cross-sectional
model. Every column in both blocks is the same number for all fourteen assets on a given day,
so a model asked which asset beats which cannot use them even in principle - it can only
overfit them, and it did: the held-back year fell from +0.111 to -0.066 when the world block
was added. They belong to the market-direction head, which asks whether this is a market to be
in at all. That is the question they can answer.
"""

from __future__ import annotations

import numpy as np

import quantlab_world as W

#: The liquidity block, in order. Names are kept from v1 so that every report, ablation arm
#: and saved panel that refers to them still means the same thing.
NAMES: tuple[str, ...] = (
    "w_netliq_chg60",    # (balance sheet - reverse repo), 60-day log change: the tide
    "w_m2_chg120",       # broad money, slow
    "w_dgs2",            # the short rate - the cost of NOT holding cash
    "w_dgs2_chg60",      # and whether it is rising
    "w_curve",           # 10y - 2y
    "w_dxy_chg60",       # the dollar
    "w_vix_pct",         # fear, as a percentile of its own trailing two years
    "w_credit_chg60",    # credit spread change - where risk appetite breaks first. Baa over
                         # the 10-year rather than high yield: FRED serves only three years
                         # of the ICE BofA series, so the sharper signal covered a third of
                         # the record and could not see a credit cycle at all.
    "w_stress_pct",      # the St. Louis Fed's financial stress composite, as a percentile of
                         # its own trailing two years
    "w_spx_ret60",       # the risk tide
    "w_oil_ret60",
)

#: The regional block. Daily, current, never revised - which is the whole argument for it.
REGIONAL_NAMES: tuple[str, ...] = (
    "r_cny_chg60",       # the currency a holder in Shanghai earns in
    "r_jpy_chg60",       # and in Tokyo: the carry trade's own thermometer
    "r_brl_chg60",       # Sao Paulo
    "r_inr_chg60",       # Mumbai
    "r_zar_chg60",       # Johannesburg - the African proxy the free sources actually carry
    "r_eur_chg60",       # Frankfurt
    "r_em_stress",       # the mean of the emerging-market currency moves: one number for
                         # "the periphery is under pressure", which is when local demand for
                         # a dollar-denominated, permissionless asset is at its strongest
    "r_nikkei_ret60",    # local risk appetite the crypto bid competes with
    "r_ez_policy",       # the ECB's deposit rate: Europe's opportunity cost, not America's
    "r_us_real_rate",    # the US short rate MINUS US inflation. The real number a dollar
                         # holder faces, and the one a nominal rate alone cannot express.
)

#: How each block's columns are drawn from the archive. `(stream, transform, kwargs)`, so the
#: shape of every feature is declared in one readable place instead of in a loop body.
_LIQUIDITY: tuple[tuple[str, str, dict], ...] = (
    ("us.money.m2", "log_change", {"k": 120}),
    ("us.rate.2y", "level", {}),
    ("us.rate.2y", "diff", {"k": 60}),
    ("us.rate.curve_10y2y", "level", {}),
    ("us.fx.dollar_broad", "log_change", {"k": 60}),
    ("us.equity.vix", "percentile", {}),
    ("us.credit.baa_spread", "diff", {"k": 60}),
    ("us.credit.stress_index", "percentile", {}),
    ("us.equity.spx", "log_change", {"k": 60}),
    ("global.commodity.oil_wti", "log_change", {"k": 60}),
)

_REGIONAL: tuple[tuple[str, str, dict], ...] = (
    ("cn.fx.usdcny", "log_change", {"k": 60}),
    ("jp.fx.usdjpy", "log_change", {"k": 60}),
    ("br.fx.usdbrl", "log_change", {"k": 60}),
    ("in.fx.usdinr", "log_change", {"k": 60}),
    ("za.fx.usdzar", "log_change", {"k": 60}),
    ("ez.fx.eurusd", "log_change", {"k": 60}),
    ("jp.equity.nikkei", "log_change", {"k": 60}),
    ("ez.rate.policy", "level", {}),
)


def _crosses_lock(days: list[str]) -> bool:
    return bool(days) and max(days)[:10] >= W.LOCK_DAY


def _panel(days: list[str], spec, sealed: bool | None) -> dict[str, np.ndarray]:
    """One column per `(stream, transform)` pair, as-of and stationary, keyed by stream+how.

    `sealed` defaults to whatever the day list requires. The archive's own guard exists for
    direct consumers; system 09 governs the seal at its boundary (`pipeline.reconstruct`), and
    a second guard here would only break the sealed run it is meant to protect.
    """
    if sealed is None:
        sealed = _crosses_lock(days)
    out: dict[str, np.ndarray] = {}
    for sid, how, kw in spec:
        col = W.history(sid, days, sealed=sealed)
        out[f"{sid}|{how}"] = _apply(how, col, days, kw)
    return out


def _apply(how: str, col, days, kw) -> np.ndarray:
    from quantlab_world import transform
    return transform.apply(how, col, days=days, **kw)


def _finite(x: np.ndarray) -> np.ndarray:
    """Missing is ZERO, and that is a statement rather than a convenience.

    Before a series exists - or after it has expired, which the archive now enforces - the
    honest thing to say is "this channel carries no information today". A zeroed CHANGE says
    exactly that. A forward-filled level would say "the world is exactly as it was five years
    ago", which is the error this whole package was built to stop.
    """
    return np.where(np.isfinite(x), x, 0.0).astype(np.float32)


def block(days: list[str], sealed: bool | None = None) -> np.ndarray:
    """The liquidity block, one row per day, aligned to publication. Shape `(n, 10)`."""
    cols = _panel(days, _LIQUIDITY, sealed)
    if sealed is None:
        sealed = _crosses_lock(days)

    # Net liquidity is the one feature built from two streams, so it is assembled by hand:
    # the balance sheet minus what is parked away from markets, as a 60-day log change.
    walcl = np.asarray(W.history("us.fed.balance_sheet", days, sealed=sealed), dtype=object)
    rrp = np.asarray(W.history("us.fed.reverse_repo", days, sealed=sealed), dtype=object)
    net = np.array([(float(a) - (float(b) if b is not None else 0.0))
                    if a is not None else np.nan for a, b in zip(walcl, rrp)],
                   dtype=np.float64)
    netliq = _apply("log_change", list(net), days, {"k": 60})

    out = np.column_stack([
        _finite(netliq),
        *[_finite(cols[f"{sid}|{how}"]) for sid, how, _ in _LIQUIDITY],
    ])
    return out.astype(np.float32)


def regional(days: list[str], sealed: bool | None = None) -> np.ndarray:
    """The regional block, one row per day. Shape `(n, 10)`.

    Two columns are composed rather than read: the emerging-market stress average, and the US
    real rate. Both are the point of having a regional archive at all - a single number that
    only exists once several regions are on the same clock.
    """
    cols = _panel(days, _REGIONAL, sealed)
    if sealed is None:
        sealed = _crosses_lock(days)

    fx = [_finite(cols[f"{sid}|log_change"])
          for sid in ("cn.fx.usdcny", "br.fx.usdbrl", "in.fx.usdinr", "za.fx.usdzar")]
    em_stress = np.mean(np.column_stack(fx), axis=1)

    # The real rate: the nominal short rate minus the inflation a dollar holder actually
    # faces. US CPI is the one national series still published promptly, which is why the
    # real rate exists for the US here and not yet for the rest.
    nominal = _finite(_apply("level", W.history("us.rate.2y", days, sealed=sealed), days, {}))
    infl = _finite(_apply("yoy", W.history("us.cpi.headline", days, sealed=sealed), days, {}))
    real = nominal - infl * 100.0

    return np.column_stack([
        _finite(cols["cn.fx.usdcny|log_change"]),
        _finite(cols["jp.fx.usdjpy|log_change"]),
        _finite(cols["br.fx.usdbrl|log_change"]),
        _finite(cols["in.fx.usdinr|log_change"]),
        _finite(cols["za.fx.usdzar|log_change"]),
        _finite(cols["ez.fx.eurusd|log_change"]),
        _finite(em_stress),
        _finite(cols["jp.equity.nikkei|log_change"]),
        _finite(cols["ez.rate.policy|level"]),
        _finite(real),
    ]).astype(np.float32)


def coverage(days: list[str]) -> dict:
    """How much of the record each channel can actually speak for. Reported, never assumed."""
    x, r = block(days), regional(days)
    out = {name: float((x[:, i] != 0.0).mean()) for i, name in enumerate(NAMES)}
    out.update({name: float((r[:, i] != 0.0).mean())
                for i, name in enumerate(REGIONAL_NAMES)})
    return out
