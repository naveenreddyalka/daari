"""Decision trace store (issue #20)."""

from __future__ import annotations

from daari.observability.trace import RequestTrace, TraceStore


def test_trace_accumulates_ordered_steps():
    trace = RequestTrace()
    trace.add("profile", category="chat", complexity="trivial")
    trace.add("l0_lookup", hit=False)
    trace.add("served", tier="L3")

    steps = trace.steps
    assert [s["step"] for s in steps] == ["profile", "l0_lookup", "served"]
    assert steps[0]["detail"] == {"category": "chat", "complexity": "trivial"}
    assert all(s["elapsed_ms"] >= 0 for s in steps)


def test_store_save_get_roundtrip(tmp_path):
    store = TraceStore(path=tmp_path / "traces.sqlite3")
    trace = RequestTrace()
    trace.add("profile", category="doc_qa")
    trace.add("served", tier="L3")
    store.save(trace, tier="L3", category="doc_qa")

    loaded = store.get(trace.trace_id)
    assert loaded is not None
    assert loaded["trace_id"] == trace.trace_id
    assert loaded["tier"] == "L3"
    assert loaded["category"] == "doc_qa"
    assert [s["step"] for s in loaded["steps"]] == ["profile", "served"]


def test_store_list_newest_first(tmp_path):
    store = TraceStore(path=tmp_path / "traces.sqlite3")
    ids = []
    for index in range(3):
        trace = RequestTrace()
        trace.add("served", tier="L3")
        store.save(trace, tier="L3", category=f"cat{index}")
        ids.append(trace.trace_id)

    summaries = store.list(limit=2)
    assert len(summaries) == 2
    assert summaries[0]["trace_id"] == ids[-1]
    assert summaries[0]["category"] == "cat2"
    assert "steps" not in summaries[0]


def test_store_prunes_to_max_entries(tmp_path):
    store = TraceStore(path=tmp_path / "traces.sqlite3", max_entries=5)
    for _ in range(12):
        trace = RequestTrace()
        trace.add("served", tier="L3")
        store.save(trace, tier="L3", category="chat")

    assert len(store.list(limit=100)) == 5


def test_disabled_store_is_noop(tmp_path):
    store = TraceStore(path=tmp_path / "traces.sqlite3", enabled=False)
    trace = RequestTrace()
    trace.add("served", tier="L3")
    store.save(trace, tier="L3", category="chat")

    assert store.get(trace.trace_id) is None
    assert store.list(limit=10) == []
    assert not (tmp_path / "traces.sqlite3").exists()


def test_store_never_raises_on_bad_path():
    store = TraceStore(path="/dev/null/impossible/traces.sqlite3")
    trace = RequestTrace()
    trace.add("served", tier="L3")
    store.save(trace, tier="L3", category="chat")
    assert store.get(trace.trace_id) is None
