"""Live integration test for capital change events.

Default skip; run with `pytest tests/manual/test_capital_change_events_live.py --live -v`.

Exercises:
- Real akshare fetch for 000423
- Real DuckDB writes via CapitalChangeEventRepository
- dividend_stock_agent reading from DB
- Field completeness checks
"""
import pytest

STOCK_CODE = "000423"


def _build_repo():
    """Lazy import + DB init — keeps skip mode free of side effects."""
    from src.db.db_connector import get_db
    from src.db.repository.capital_change_events import CapitalChangeEventRepository

    return CapitalChangeEventRepository(get_db())


def _fetch_events_live(stock_code: str):
    """Lazy akshare import — only triggers network when --live."""
    from src.tools.capital_change_fetcher import fetch_capital_change_events

    return fetch_capital_change_events(stock_code)


def _scrub_nan_dates(events):
    """Mirror refresh_capital_changes.py cleanup: drop NaT strings before insert."""
    date_fields = (
        "event_date", "ex_date", "record_date", "payment_date", "listing_date",
    )
    cleaned = []
    for ev in events:
        if not ev.get("event_date") or str(ev["event_date"]) == "NaT":
            continue
        for f in date_fields:
            if str(ev.get(f) or "") == "NaT":
                ev[f] = None
        cleaned.append(ev)
    return cleaned


def test_fetcher_returns_cash_dividend_events():
    """akshare must return >0 events and at least one cash_dividend for 000423."""
    events = _fetch_events_live(STOCK_CODE)
    events = _scrub_nan_dates(events)
    assert len(events) > 0, "fetcher returned no events for 000423"
    types = {e.get("event_type") for e in events}
    assert "cash_dividend" in types, (
        f"expected cash_dividend in event types; got {types}"
    )


def test_upsert_many_round_trip():
    """Write via repo, count via repo, assert round-trip."""
    repo = _build_repo()
    from src.db.repository.keys import ReportKey

    key = ReportKey(stock_code=STOCK_CODE)

    # Snapshot baseline; the cleanup test below restores it
    baseline = repo.count_events(key)
    assert baseline > 0, (
        "expected pre-existing 000423 events from refresh_capital_changes.py "
        "(run it first if missing); got 0"
    )

    # Idempotent re-upsert of all currently-known events — count must stay flat
    events = repo.list_events(key)
    written = repo.upsert_many(events)
    assert written == len(events)
    assert repo.count_events(key) == baseline


def test_upsert_many_idempotent():
    """Second upsert of the same events must not produce duplicates."""
    repo = _build_repo()
    from src.db.repository.keys import ReportKey

    key = ReportKey(stock_code=STOCK_CODE)

    before = repo.count_events(key)
    events = repo.list_events(key)
    # Re-upsert — proves update path runs (no UNIQUE error)
    repo.upsert_many(events)
    after = repo.count_events(key)
    assert after == before, (
        f"upsert must be idempotent on (stock_code, event_date, event_type); "
        f"before={before} after={after}"
    )


def test_list_events_sorted_desc():
    """list_events must return rows sorted by event_date DESC."""
    repo = _build_repo()
    from src.db.repository.keys import ReportKey

    key = ReportKey(stock_code=STOCK_CODE)
    rows = repo.list_events(key)
    assert len(rows) == repo.count_events(key)
    dates = [r.get("event_date") for r in rows]
    assert dates == sorted(dates, reverse=True), (
        f"event_date not sorted DESC; first={dates[:3]} last={dates[-3:]}"
    )


def test_dividend_agent_reads_from_db():
    """_get_dividend_stats_with_fallback should hit DB (source='db') and return stats."""
    # Pre-import src.graph to break the circular import chain
    # (dividend skill imports src.graph.state which loads src.graph.__init__,
    # which imports graph.py which imports src.agents.analysis back).
    import src.graph  # noqa: F401
    from src.skills.dividend.tools import (
        get_dividend_stats_with_fallback,
    )

    stats = get_dividend_stats_with_fallback(STOCK_CODE, years=5)
    assert stats.get("source") == "db", (
        f"expected stats from db; got source={stats.get('source')}"
    )
    assert stats.get("event_count", 0) > 0, (
        f"expected event_count > 0; got {stats.get('event_count')}"
    )
    last_cash = stats.get("last_cash_per_10_shares")
    assert isinstance(last_cash, float), (
        f"last_cash_per_10_shares should be float; got {type(last_cash).__name__} "
        f"value={last_cash}"
    )


def test_merge_coverage_both_sources_present():
    """Both 'eastmoney' and 'merged' sources must appear — proves left-join fired."""
    repo = _build_repo()
    from src.db.repository.keys import ReportKey

    rows = repo.list_events(ReportKey(stock_code=STOCK_CODE))
    sources = {r.get("source") for r in rows}
    assert "eastmoney" in sources, (
        f"expected at least one 'eastmoney'-only event; got {sources}"
    )
    assert "merged" in sources, (
        f"expected at least one 'merged' event (cninfo left-join hit); got {sources}"
    )


def test_field_completeness_for_known_types():
    """cash_dividend must have cash_per_10_shares; bonus_share must have bonus_shares_per_10."""
    repo = _build_repo()
    from src.db.repository.keys import ReportKey

    rows = repo.list_events(ReportKey(stock_code=STOCK_CODE))

    cash_rows = [r for r in rows if r.get("event_type") == "cash_dividend"]
    assert cash_rows, "no cash_dividend events to verify"
    for r in cash_rows:
        assert r.get("cash_per_10_shares") is not None, (
            f"cash_dividend missing cash_per_10_shares: {r.get('event_date')}"
        )

    bonus_rows = [r for r in rows if r.get("event_type") == "bonus_share"]
    for r in bonus_rows:
        assert r.get("bonus_shares_per_10") is not None, (
            f"bonus_share missing bonus_shares_per_10: {r.get('event_date')}"
        )


def test_cleanup_restores_baseline():
    """Drop all rows for stock_code, restore via upsert — proves cleanup path."""
    from src.db.db_connector import get_db
    from src.db.repository.keys import ReportKey

    db = get_db()
    repo = _build_repo()

    key = ReportKey(stock_code=STOCK_CODE)
    baseline_rows = repo.list_events(key)
    baseline_count = len(baseline_rows)
    assert baseline_count > 0, "baseline empty — earlier tests should have populated"

    # Delete all events for this stock_code
    deleted = db.delete_records(
        "capital_change_events", stock_code=STOCK_CODE,
    )
    assert deleted == baseline_count, (
        f"delete_records returned {deleted}, expected {baseline_count}"
    )
    assert repo.count_events(key) == 0

    # Re-insert to restore original state for future runs
    written = repo.upsert_many(baseline_rows)
    assert written == baseline_count, (
        f"restore upsert wrote {written}, expected {baseline_count}"
    )
    assert repo.count_events(key) == baseline_count
