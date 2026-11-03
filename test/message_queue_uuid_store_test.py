import tempfile
import time

from pulsar.client.util import MessageQueueUUIDStore


def test_uuid_store_iteration():
    with tempfile.TemporaryDirectory() as persistence_directory:
        store = MessageQueueUUIDStore(persistence_directory)
        # Iterating an empty store must not fall back to the sequence protocol,
        # which would call __getitem__(0).
        assert list(store) == []
        assert list(store.keys()) == []

        store["uuid-a"] = {"payload": 1}
        store["uuid-b"] = {"payload": 2}
        assert sorted(store) == ["uuid-a", "uuid-b"]
        assert sorted(store.keys()) == ["uuid-a", "uuid-b"]
        assert "uuid-a" in store
        assert store["uuid-a"] == {"payload": 1}

        del store["uuid-a"]
        assert list(store) == ["uuid-b"]
        assert store.get_time("uuid-b") <= time.time()
