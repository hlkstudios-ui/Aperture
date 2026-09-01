from scripts import maintenance


def test_maintenance_synchronizes_catalog_and_bounds_retention_work(monkeypatch) -> None:
    calls = {
        "sync": 0,
        "rental_reconcile": 0,
        "verification_reconcile": 0,
        "commit": 0,
    }
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
        "get_settings",
        lambda: type("Settings", (), {"platform_control_plane_enabled": True})(),
    )
    monkeypatch.setattr(
        maintenance,
        "synchronize_due_schedules",
        lambda _: calls.__setitem__("sync", calls["sync"] + 1),
    )

    def reconcile(_, *, limit: int) -> int:
        assert limit == 100
        calls["rental_reconcile"] += 1
        return 4

    monkeypatch.setattr(maintenance, "reconcile_expired_rental_intents", reconcile)

    def reconcile_verification_deliveries(_, *, limit: int) -> int:
        assert limit == 100
        calls["verification_reconcile"] += 1
        return 2

    monkeypatch.setattr(
        maintenance,
        "reconcile_stale_platform_verification_deliveries",
        reconcile_verification_deliveries,
    )
    monkeypatch.setattr(maintenance, "purge_expired_events", lambda _: next(removals))

    result = maintenance.run_maintenance(max_cleanup_batches=3)

    assert result == {
        "catalog_schedule_syncs": 1,
        "platform_rental_intents_expired": 4,
        "platform_verification_deliveries_failed": 2,
        "analytics_events_purged": 1007,
        "batches": 3,
    }
    assert calls == {
        "sync": 1,
        "rental_reconcile": 1,
        "verification_reconcile": 1,
        "commit": 4,
    }


def test_maintenance_skips_platform_reconciliation_when_control_plane_disabled(
    monkeypatch,
) -> None:
    calls = {"sync": 0, "commit": 0}

    class Db:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def commit(self):
            calls["commit"] += 1

    def unexpected_reconciliation(*_, **__) -> int:
        raise AssertionError("rental reconciliation must be disabled")

    monkeypatch.setattr(maintenance, "SessionLocal", Db)
    monkeypatch.setattr(
        maintenance,
        "get_settings",
        lambda: type("Settings", (), {"platform_control_plane_enabled": False})(),
    )
    monkeypatch.setattr(
        maintenance,
        "synchronize_due_schedules",
        lambda _: calls.__setitem__("sync", calls["sync"] + 1),
    )
    monkeypatch.setattr(
        maintenance,
        "reconcile_expired_rental_intents",
        unexpected_reconciliation,
    )
    monkeypatch.setattr(
        maintenance,
        "reconcile_stale_platform_verification_deliveries",
        unexpected_reconciliation,
    )
    monkeypatch.setattr(maintenance, "purge_expired_events", lambda _: 0)

    result = maintenance.run_maintenance(max_cleanup_batches=1)

    assert result == {
        "catalog_schedule_syncs": 1,
        "platform_rental_intents_expired": 0,
        "platform_verification_deliveries_failed": 0,
        "analytics_events_purged": 0,
        "batches": 1,
    }
    assert calls == {"sync": 1, "commit": 1}
