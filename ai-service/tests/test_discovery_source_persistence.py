from __future__ import annotations

from services import discovery_source_persistence as persistence


class _FakeCursor:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.queries: list[tuple[str, tuple | None]] = []

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _tb):
        return False

    def execute(self, query, params=None):
        self.queries.append((query, params))

    def fetchall(self):
        return self.rows.pop(0) if self.rows else []


class _FakeConnection:
    def __init__(self, cursor):
        self.cursor_obj = cursor
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _tb):
        return False

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.committed = True


def test_get_registry_reads_discovery_source_tables(monkeypatch):
    persistence.clear_registry_cache()
    cursor = _FakeCursor(rows=[
        [("TST", "Testland", '["en"]')],
        [
            (
                "TST",
                "Test Statutes",
                "https://laws.example",
                '["laws.example"]',
                "primary",
                "search_engine",
                "statute_portal",
                '["en"]',
                "[6]",
                '["6.4"]',
                "[]",
                "[]",
                "[]",
                100,
                "Official source",
            )
        ],
    ])
    connection = _FakeConnection(cursor)
    monkeypatch.setattr(persistence, "_db_connect", lambda: connection)

    registry = persistence.get_registry()

    assert registry["TST"]["label"] == "Testland"
    assert registry["TST"]["sources"][0]["domains"] == ["laws.example"]
    assert registry["TST"]["sources"][0]["pillars"] == [6]
    assert any("FROM discovery_countries" in query for query, _params in cursor.queries)
    assert any("FROM discovery_sources" in query for query, _params in cursor.queries)


def test_save_registry_writes_discovery_tables_and_audit(monkeypatch):
    persistence.clear_registry_cache()
    cursor = _FakeCursor()
    connection = _FakeConnection(cursor)
    monkeypatch.setattr(persistence, "_db_connect", lambda: connection)

    registry = persistence.save_registry(
        {
            "TST": {
                "label": "Testland",
                "languages": ["en"],
                "sources": [
                    {
                        "name": "Test Statutes",
                        "base_url": "https://laws.example",
                        "domains": ["laws.example"],
                        "source_grade": "primary",
                        "adapter": "search_engine",
                        "source_type": "statute_portal",
                        "languages": ["en"],
                        "pillars": [6],
                        "priority": 100,
                    }
                ],
            }
        },
        changed_by="11111111-1111-1111-1111-111111111111",
        change_note="test save",
    )

    executed = "\n".join(query for query, _params in cursor.queries)
    assert "DELETE FROM discovery_sources" in executed
    assert "INSERT INTO discovery_countries" in executed
    assert "INSERT INTO discovery_sources" in executed
    assert "INSERT INTO discovery_source_versions" in executed
    assert "INSERT INTO discovery_source_audit_events" in executed
    assert connection.committed is True
    assert registry["TST"]["sources"][0]["name"] == "Test Statutes"


def test_get_registry_wraps_invalid_stored_data(monkeypatch):
    persistence.clear_registry_cache()
    cursor = _FakeCursor(rows=[
        [("TST", "Testland", '["en"]')],
        [
            (
                "TST",
                "Bad Statutes",
                "https://laws.example",
                '["laws.example"]',
                "primary",
                "search_engine",
                "statute_portal",
                '["en"]',
                "[99]",
                "[]",
                "[]",
                "[]",
                "[]",
                100,
                "Invalid pillar",
            )
        ],
    ])
    connection = _FakeConnection(cursor)
    monkeypatch.setattr(persistence, "_db_connect", lambda: connection)

    try:
        persistence.get_registry()
    except persistence.DiscoverySourcePersistenceError as exc:
        assert "unsupported source pillar" in str(exc)
    else:
        raise AssertionError("Expected invalid stored data to be wrapped")
    finally:
        persistence.clear_registry_cache()


def test_registry_database_backend_preserves_empty_database(monkeypatch):
    from discovery import registry as registry_module

    monkeypatch.setenv("DISCOVERY_REGISTRY_BACKEND", "database")
    monkeypatch.setattr(persistence, "get_registry", lambda: {})

    assert registry_module.get_registry() == {}
