import sqlite3
import unittest

from quantlab.autonomous import DashboardData
from quantlab.models import ENGINE_VERSION
from quantlab.public_state import compact_public_snapshot


def _db() -> sqlite3.Connection:
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript("""
        CREATE TABLE portfolio_backtest_runs (
          strategy_number INTEGER PRIMARY KEY, status TEXT, final_equity REAL,
          initial_capital REAL, return_pct REAL, max_drawdown REAL, trades INTEGER,
          assets_traded INTEGER, average_exposure REAL, time_in_market REAL,
          engine_version INTEGER,
          -- QUANT17: the leader query is mandate-aware, so the fixture has to
          -- carry the basis columns too. A hand-built fixture schema drifting
          -- from the real one is how this test started failing for a reason
          -- that had nothing to do with what it checks.
          capital_drawdown REAL, drawdown_basis TEXT);
        CREATE TABLE forward_portfolio_runs (
          run_id TEXT PRIMARY KEY, strategy_number INTEGER, status TEXT,
          return_pct REAL, as_of TEXT);
    """)
    return db


def _run(
    db,
    number,
    return_pct,
    engine_version,
    drawdown=0.10,
    exposure=None,
    capital_drawdown=None,
    drawdown_basis=None,
):
    db.execute(
        "INSERT INTO portfolio_backtest_runs VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            number,
            "COMPLETE",
            100_000 * (1 + return_pct),
            100_000.0,
            return_pct,
            drawdown,
            500,
            5,
            exposure,
            0.5 if exposure is not None else None,
            engine_version,
            capital_drawdown,
            drawdown_basis,
        ),
    )


class Phase1LeaderTest(unittest.TestCase):
    """The research high-water mark has to be correct and it has to be visible.
    It was computed, then dropped by both the page renderer and the public
    mirror, so the best backtest the laboratory had produced reached no surface
    at all -- while the champion, ranked on forward evidence, correctly never
    moved.
    """

    def test_a_pre_fix_engine_result_can_never_be_the_leader(self):
        # Engine 1 runs are inflated by the sizing lookahead QUANT8 removed.
        # Without the filter the leader was S00212 at +4363%, a number this
        # laboratory already knows is an artifact, shown as its best result.
        db = _db()
        _run(db, 212, 43.63, engine_version=1)
        _run(db, 848, 3.50, engine_version=ENGINE_VERSION)
        leader = DashboardData._best_phase1(db)
        self.assertEqual(leader["label"], "S00848")

    def test_with_only_pre_fix_results_there_is_no_leader_at_all(self):
        # Reporting nothing is correct here; reporting the inflated run is not.
        db = _db()
        _run(db, 212, 43.63, engine_version=1)
        self.assertIsNone(DashboardData._best_phase1(db))

    def test_the_leader_is_ranked_on_return_minus_drawdown(self):
        db = _db()
        _run(db, 1, 0.50, ENGINE_VERSION, drawdown=0.05)
        _run(db, 2, 0.60, ENGINE_VERSION, drawdown=0.24)
        leader = DashboardData._best_phase1(db)
        self.assertEqual(leader["label"], "S00001")

    def test_several_forward_runs_do_not_duplicate_or_scramble_the_row(self):
        # A LEFT JOIN multiplied rows here, so LIMIT 1 picked arbitrarily among
        # the duplicates and the forward status shown was whichever came first.
        db = _db()
        _run(db, 848, 3.50, ENGINE_VERSION)
        db.execute(
            "INSERT INTO forward_portfolio_runs VALUES(?,?,?,?,?)",
            ("FWD2-S00848-A", 848, "FORWARD_ABORTED_DRAWDOWN", -0.30, "2026-01-01"),
        )
        db.execute(
            "INSERT INTO forward_portfolio_runs VALUES(?,?,?,?,?)",
            ("FWD2-S00848-B", 848, "FORWARD_2026", -0.0733, "2026-08-04"),
        )
        leader = DashboardData._best_phase1(db)
        self.assertEqual(leader["label"], "S00848")
        # The most recent forward run is the current fact about the strategy.
        self.assertEqual(leader["forward_status"], "FORWARD_2026")
        self.assertAlmostEqual(leader["forward_return"], -0.0733)

    def test_exposure_is_none_rather_than_zero_when_it_was_not_measured(self):
        db = _db()
        _run(db, 848, 3.50, ENGINE_VERSION, exposure=None)
        leader = DashboardData._best_phase1(db)
        self.assertIsNone(leader["average_exposure"])
        self.assertIsNone(leader["time_in_market"])

    def test_measured_exposure_is_carried_through(self):
        db = _db()
        _run(db, 848, 3.50, ENGINE_VERSION, exposure=0.114)
        leader = DashboardData._best_phase1(db)
        self.assertAlmostEqual(leader["average_exposure"], 0.114)

    def test_the_eligible_count_only_counts_current_engine_runs(self):
        db = _db()
        _run(db, 1, 0.10, engine_version=1)
        _run(db, 2, 0.20, engine_version=1)
        _run(db, 3, 0.30, engine_version=ENGINE_VERSION)
        self.assertEqual(DashboardData._best_phase1(db)["eligible_count"], 1)


class PublicMirrorCarriesPhase1Test(unittest.TestCase):
    def test_the_public_snapshot_forwards_the_phase1_leader(self):
        leader = {"label": "S00848", "return_pct": 3.5, "max_drawdown": 0.2038}
        public = compact_public_snapshot({"best_phase1": leader})
        self.assertEqual(public["best_phase1"]["label"], "S00848")

    def test_a_snapshot_without_a_leader_stays_absent_not_invented(self):
        public = compact_public_snapshot({})
        self.assertIsNone(public["best_phase1"])


if __name__ == "__main__":
    unittest.main()


class MandateAwareLeaderTest(unittest.TestCase):
    """The leader query must apply the mandate each run was measured under.

    A run held to "never lose more than 25% of the deposit" can legitimately
    show a 51% PEAK drawdown after compounding 28x -- the giveback is of profit,
    not of capital. Gating that run out with a hardcoded `max_drawdown < 0.25`
    silently hid the best Phase-1 result this laboratory has produced, and
    ranking by `return - peak_drawdown` penalised it for a giveback its own
    mandate permits.
    """

    def test_a_deep_peak_giveback_is_eligible_under_the_initial_basis(self):
        db = _db()
        _run(
            db,
            1,
            28.36,
            ENGINE_VERSION,
            drawdown=0.5124,
            capital_drawdown=0.0296,
            drawdown_basis="initial",
        )
        leader = DashboardData._best_phase1(db)
        self.assertIsNotNone(
            leader, "a legal initial-basis run must not be filtered out"
        )
        self.assertEqual(leader["label"], "S00001")
        self.assertAlmostEqual(leader["capital_drawdown"], 0.0296)
        self.assertEqual(leader["drawdown_basis"], "initial")

    def test_a_run_that_breached_its_mandate_is_filtered_by_its_status(self):
        """The abort IS the mandate check, so the status carries it.

        A `COMPLETE` row that breached its own mandate cannot be produced -- the
        engine aborts the moment the limit is crossed and writes
        `ABORTED_DRAWDOWN`. Re-testing a completed run against a peak-drawdown
        rule here disqualified it a second time under a rule it was never run
        under, which is how the best Phase-1 result got hidden twice: once when
        the gate enumerated only "initial", and again when "ratchet" appeared.
        """
        db = _db()
        db.execute(
            "INSERT INTO portfolio_backtest_runs VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                1,
                "ABORTED_DRAWDOWN",
                69_000.0,
                100_000.0,
                -0.31,
                0.60,
                500,
                5,
                None,
                None,
                ENGINE_VERSION,
                0.31,
                "initial",
            ),
        )
        self.assertIsNone(DashboardData._best_phase1(db))

    def test_a_legacy_row_without_a_basis_keeps_the_peak_rule(self):
        db = _db()
        _run(db, 1, 2.0, ENGINE_VERSION, drawdown=0.40)
        self.assertIsNone(DashboardData._best_phase1(db))
        _run(db, 2, 1.0, ENGINE_VERSION, drawdown=0.10)
        self.assertEqual(DashboardData._best_phase1(db)["label"], "S00002")
