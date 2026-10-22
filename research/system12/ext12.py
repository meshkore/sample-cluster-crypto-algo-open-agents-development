"""System 12 - extra inputs for the task list (TODO.md, tasks 4-6). Everything lands in ext/ and is read by hypotheses12.py.

    ext/mvrv.npy, ext/dvol.npy     daily series on the crypto calendar, lagged one day (known the next morning):
                                   MVRV from CoinMetrics community (2016-), DVOL from Deribit (2021-04-)
    ext/ens_<name>.npy             4h weights: equal average of the catalogue's A/B strategies' walk-forward weights
                                   (all / trend+momentum+volatility / mean reversion / macro+crypto+calendar)
    ext/coins_<n>.npy              4h weights: breakout trend on every coin of the point-in-time top 14 (long above the
                                   n-day highest close, out below the channel midpoint; Zarattini et al. 2025), each coin
                                   volatility-targeted to 40%/14, perps only where they existed

    python research/system12/ext12.py
"""

from __future__ import annotations

import json
import time
import urllib.request

import numpy as np
import pandas as pd

import catalog12 as C

HERE = C.HERE
OUT = HERE / "ext"
UA = {"User-Agent": "quantlab-research/1.0"}


def _get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        return json.load(r)


def mvrv() -> dict:
    out, url = {}, ("https://community-api.coinmetrics.io/v4/timeseries/asset-metrics?assets=btc&metrics=CapMVRVCur"
                    "&frequency=1d&start_time=2015-01-01&page_size=10000&paging_from=start")
    while url:
        d = _get(url)
        for r in d.get("data", []):
            out[r["time"][:10]] = float(r["CapMVRVCur"])
        url = d.get("next_page_url")
    return out


def dvol() -> dict:
    out = {}
    t0 = int(pd.Timestamp("2021-03-01").timestamp() * 1000)
    end = int(time.time() * 1000)
    while t0 < end:
        t1 = min(end, t0 + 900 * 86_400_000)
        d = _get(f"https://www.deribit.com/api/v2/public/get_volatility_index_data?currency=BTC&start_timestamp={t0}"
                 f"&end_timestamp={t1}&resolution=1D")
        for ts, o, h, l, c in d["result"]["data"]:
            out[str(pd.Timestamp(ts, unit="ms").date())] = float(c)
        t0 = t1 + 1
    return out


def daily(book, series: dict) -> np.ndarray:
    """Onto the crypto calendar, forward-filled, lagged one day."""
    s = pd.Series({pd.Timestamp(k): v for k, v in series.items()}).sort_index()
    days = pd.to_datetime(book.days.astype(str))
    return s.reindex(days, method="ffill").shift(1).values.astype(float)


def ensembles(book) -> dict:
    res = [json.loads(x) for x in C.RES.read_text(encoding="utf-8").splitlines() if x.strip()]
    st = {s["id"]: s for s in C.load_raw()}
    fam = {"all": None, "trend": ("trend", "momentum", "volatility"), "mr": ("meanrev",), "other": ("macro", "crypto", "calendar")}
    out = {}
    for name, f in fam.items():
        ids = [r["id"] for r in res if r.get("tier") in ("A", "B") and (C.CAT / "wf" / f"{r['id']}.npy").exists()
               and (f is None or st.get(r["id"], {}).get("family") in f)]
        if ids:
            out[name] = (sum(np.load(C.CAT / "wf" / f"{i}.npy").astype(float) for i in ids) / len(ids), len(ids))
    return out


def coins_trend(book, n: int) -> np.ndarray:
    ctx, eng, P = book.ctx, book.eng, book.P
    c = pd.DataFrame(P["close"])
    hi = c.shift(1).rolling(n, min_periods=n).max()
    lo = c.shift(1).rolling(n, min_periods=n).min()
    mid = (hi + lo) / 2
    vol = np.log(c).diff().rolling(30, min_periods=20).std() * np.sqrt(365)
    mem = np.asarray(P["member"], dtype=bool)
    W = np.zeros((ctx.nD, c.shape[1]))
    for j in range(c.shape[1]):
        on, st = c[j].values > hi[j].values, 0.0
        off = c[j].values < mid[j].values
        pos = np.zeros(ctx.nD)
        for t in range(ctx.nD):
            st = 1.0 if on[t] else (0.0 if off[t] else st)
            pos[t] = st if mem[t, j] else 0.0
        W[:, j] = pos * np.nan_to_num(np.clip(0.4 / vol[j].values, 0, 1)) / 14
    W4 = np.column_stack([eng.to4(W[:, j]) for j in range(W.shape[1])])
    return np.where(eng.can, W4, 0.0)


def main() -> int:
    OUT.mkdir(exist_ok=True)
    book = C.Book()
    for name, fn in (("mvrv", mvrv), ("dvol", dvol)):
        try:
            raw = fn()
            (OUT / f"{name}.json").write_text(json.dumps(raw), encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            print(f"{name}: download failed ({exc}); keeping the cached copy")
            raw = json.loads((OUT / f"{name}.json").read_text(encoding="utf-8"))
        np.save(OUT / f"{name}.npy", daily(book, raw).astype(np.float32))
        print(name, len(raw), "days")
    for name, (W, k) in ensembles(book).items():
        np.save(OUT / f"ens_{name}.npy", W.astype(np.float32))
        print(f"ens_{name}: {k} strategies")
    for n in (10, 20, 40):
        np.save(OUT / f"coins_{n}.npy", coins_trend(book, n).astype(np.float32))
    np.save(OUT / "days.npy", book.days.astype("datetime64[D]").astype(np.int64))
    print("coins trend: done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
