"""The MWModel viewer server. `python server/app.py` and open http://127.0.0.1:8800

    *"El visor es muy importante, porque es la parte bonita de esta historia. Sobre todo el
    estado actual y las proyecciones, que es lo más importante."*

A world runs in a background thread, one simulated day every few seconds, and the page reads
it. Three things are on the screen and the third is the reason for the other two:

    WHERE THE WORLD IS     the map, the valves, the prices, who is hurting
    HOW IT GOT THERE       the journal - every decision with the reason the agent gave
    WHERE IT IS GOING      the fan charts, the scenario probabilities, and the causal chain

The valves are interactive on purpose. Closing Hormuz from the page and watching the
projection change is the fastest way to see whether the model is describing a world or
generating a number, and it should be possible in one click rather than in a script.

NOTHING HERE IS A TRADING SYSTEM. It reads the world, it does not act on anything, and there
is no path from this process to an exchange, a wallet or a key.
"""

from __future__ import annotations

import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from mwmodel import engine, project                     # noqa: E402
from mwmodel.network import chokepoints as CP           # noqa: E402
from mwmodel.seed import facts                          # noqa: E402
from mwmodel.seed.build import build                    # noqa: E402

PORT = 8800
SECONDS_PER_TICK = 4.0          # one simulated day every four seconds while watching

_lock = threading.Lock()
_world, _agents = build()
_last: engine.TickReport | None = None
_history: list[dict] = []
_projection: dict | None = None
_running = True
#: The world starts in the condition the operator described on 2026-09-15: Hormuz and Bab
#: el-Mandeb constrained rather than closed. It is a starting assumption, set here where it
#: can be seen and changed, not buried in the model.
_valve_states: dict[str, str] = {k: "open" for k in CP.CHOKEPOINTS}
_valve_states["hormuz"] = "harassed"
_valve_states["bab_el_mandeb"] = "harassed"


for _k, _st in _valve_states.items():
    if _st != "open":
        CP.constrain(_world, _k, project.VALVE_STATES[_st], why="initial world condition")


def _tick_forever() -> None:
    """The world turns whether or not anybody is looking at it."""
    global _last, _projection
    while _running:
        with _lock:
            try:
                _last = engine.step(_world, _agents, [])
                _history.append({"day": _last.day, "crude": _last.prices["crude"],
                                 "supply": _last.supply, "demand": _last.demand,
                                 "cover": _last.cover_days, "stranded": _last.stranded})
                del _history[:-400]
                # The projection is refreshed every few days rather than every tick: it is
                # the expensive call and it does not change much in one simulated day.
                if _last.tick % 5 == 1 or _projection is None:
                    # Ninety days rather than sixty, so that the three-month mark the operator
                    # asked for is a projection rather than an extrapolation of one.
                    _projection = project.project(
                        _world, _agents, horizon=90, runs=32,
                        start_state=_valve_states.get("hormuz", "open"))
            except Exception as exc:                      # a broken world must be visible
                _history.append({"day": _world.day, "error": f"{type(exc).__name__}: {exc}"})
        time.sleep(SECONDS_PER_TICK)


def _state() -> dict:
    w = _world
    countries = []
    for code, f in facts.COUNTRIES.items():
        ident = f"country.{code}"
        lon, lat = facts.COORDS.get(code, (0.0, 0.0))
        countries.append({
            "code": code, "name": f["name"], "lon": lon, "lat": lat,
            "region": f.get("region", ""),
            "demand": f.get("oil_demand", 0.0), "capacity": f.get("oil_capacity", 0.0),
            "production": w.var(ident, "oil_prod", 0.0),
            "cpi": w.var(ident, "cpi_yoy", 0.0),
            "cpi_seen": w.var(ident, "cpi_lagged", 0.0),
            "energy_contrib": w.var(ident, "energy_contrib", 0.0),
            "utilisation": w.var(ident, "utilisation", 0.0),
            "breakeven": f.get("breakeven", 0.0),
            "rate": w.var(f"cb.{code}", "policy_rate", 0.0) if f.get("cb") else None,
        })
    valves = []
    for v in CP.status(w):
        lon, lat = facts.CHOKE_COORDS.get(v["key"], (0.0, 0.0))
        v.update(lon=lon, lat=lat, state=_valve_states.get(v["key"], "open"))
        valves.append(v)
    journal = [j for j in w.journal if j.get("what") in ("clear", "capacity", "set")][-40:]

    # The sectors between the well and the shelf, and the channels they speak on. This is the
    # part of the screen that shows the model is a network rather than an equation: the
    # cascade below is what actually travelled on this tick, in order, with its causal chain.
    ref = "refiner.global"
    products = {k: w.var(ref, f"price.{k}", 0.0)
                for k in ("diesel", "gasoline", "jet", "bunker")}
    cracks = {k: w.var(ref, f"crack.{k}", 0.0)
              for k in ("diesel", "gasoline", "jet", "bunker")}
    freight = []
    for seg in ("container", "tanker", "bulk"):
        cid = f"carrier.{seg}"
        for name, value in sorted(w.vars.get(cid, {}).items()):
            if name.startswith("rate."):
                lane = name.split(".", 1)[1]
                freight.append({"segment": seg, "lane": lane, "rate": value,
                                "detour": w.var(cid, f"detour_days.{lane}", 0.0)})
    cascade = [{"topic": t["topic"], "value": t["value"], "source": t["source"],
                "wave": t["wave"], "chain": t["chain"], "why": t["why"],
                "heard_by": t["heard_by"]}
               for t in w.bus.trace][-60:]

    # THE TRAFFIC. Cumulative meters rather than this tick's activity: the operator asked to
    # watch the counters go up, and a counter is the only thing that distinguishes a channel
    # that fires twice a year from one that has never fired at all. Both look identical on any
    # single tick, and only one of them is a bug.
    channels = w.bus.channels()
    talkers = w.bus.talkers()
    latest = {}
    for c in channels:
        if c["source"] and c["source"] not in latest:
            latest[c["source"]] = {"topic": c["topic"], "value": c["value"],
                                   "unit": c["unit"]}
    for t in talkers:
        t.update(latest.get(t["who"], {}))
        t["kind"] = t["who"].split(".", 1)[0]
    return {
        "day": w.day, "tick": w.tick,
        "crude": w.price("crude"),
        "inventory": w.markets["crude"].inventory,
        "supply": _last.supply if _last else 0.0,
        "demand": _last.demand if _last else 0.0,
        "stranded": _last.stranded if _last else 0.0,
        "cover_days": _last.cover_days if _last else 0.0,
        "cost_push": _last.cost_push if _last else 0.0,
        "notes": _last.notes if _last else [],
        "countries": countries, "valves": valves,
        "products": products, "cracks": cracks, "freight": freight,
        "bus": w.bus.summary(), "cascade": cascade,
        "dropped": w.bus.dropped[-10:],
        "channels": channels, "talkers": talkers,
        "links": w.bus.links(26), "per_tick": w.bus.per_tick[-120:],
        "history": _history[-240:], "journal": journal,
        "agents": len(_agents),
        "seconds_per_tick": SECONDS_PER_TICK,
    }


class Handler(BaseHTTPRequestHandler):
    def _send(self, body: bytes, ctype: str, code: int = 200) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:                             # noqa: N802
        url = urlparse(self.path)
        if url.path in ("/", "/index.html"):
            self._send((HERE / "viewer.html").read_bytes(), "text/html; charset=utf-8")
            return
        if url.path == "/api/state":
            with _lock:
                body = json.dumps(_state()).encode()
            self._send(body, "application/json")
            return
        if url.path == "/api/score":
            # The scorecard is the honest counterweight to the fan chart: a projection with no
            # published track record beside it is decoration.
            import pathlib as _pl
            f = _pl.Path(__file__).resolve().parent.parent / "data" / "score_report.json"
            self._send(f.read_bytes() if f.is_file() else b"{}", "application/json")
            return
        if url.path == "/api/projection":
            with _lock:
                body = json.dumps(_projection or {}).encode()
            self._send(body, "application/json")
            return
        if url.path == "/api/valve":
            q = parse_qs(url.query)
            key = (q.get("key") or [""])[0]
            state = (q.get("state") or ["open"])[0]
            with _lock:
                if key in CP.CHOKEPOINTS and state in project.VALVE_STATES:
                    _valve_states[key] = state
                    CP.constrain(_world, key, project.VALVE_STATES[state],
                                 why=f"set from the viewer: {state}")
                    ok = True
                else:
                    ok = False
            self._send(json.dumps({"ok": ok, "key": key, "state": state}).encode(),
                       "application/json")
            return
        self._send(b"not found", "text/plain", 404)

    def log_message(self, *args) -> None:                 # quiet
        pass


def main() -> int:
    threading.Thread(target=_tick_forever, daemon=True).start()
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"MWModel viewer on http://127.0.0.1:{PORT}")
    print(f"  {len(_agents)} agents, {len(CP.CHOKEPOINTS)} valves, "
          f"one simulated day every {SECONDS_PER_TICK:.0f}s")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
