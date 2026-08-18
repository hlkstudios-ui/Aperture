from scripts import maintenance


def test_maintenance_synchronizes_catalog_and_bounds_retention_work(monkeypatch) -> None:
    calls = {"sync": 0, "commit": 0}
    removals = iter((500, 500, 7))

    class Db:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def commit(self):
            calls["commit"] += 1

    monkeypatch.setattr(maintenance, "SessionLocal", Db)
    monkeypatch.setattr(
        maintenance,
        "synchronize_due_schedules",
        lambda _: calls.__setitem__("sync", calls["sync"] + 1),
    )
    monkeypatch.setattr(maintenance, "purge_expired_events", lambda _: next(removals))

    result = maintenance.run_maintenance(max_cleanup_batches=3)

    assert result == {
        "catalog_schedule_syncs": 1,
        "analytics_events_purged": 1007,
        "batches": 3,
    }
    assert calls == {"sync": 1, "commit": 3}
