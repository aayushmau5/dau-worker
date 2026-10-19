import asyncio
import time
from types import SimpleNamespace

import pytest
from oban import Cancel
from oban.testing import process_job

from dau_worker import hash_worker
from dau_worker.hash_worker import HashWorker

REQUEST = {
    "inbox_id": 1,
    "file_key": "temp/0b6c2f2e-6a43-4f7e-9b1d-2f0c1e9a7d10",
    "media_type": "video",
}


class FakeHasher:
    algorithm = "fake-hasher@1"

    def __init__(self, hash_value="abc123", error=None, delay=0):
        self.hash_value = hash_value
        self.error = error
        self.delay = delay

    def hash(self, file_key):
        time.sleep(self.delay)
        if self.error:
            raise self.error
        return self.hash_value


class FakeOban:
    def __init__(self):
        self.enqueued = []

    async def enqueue(self, job):
        self.enqueued.append(job)
        return job


@pytest.fixture
def oban(monkeypatch):
    fake = FakeOban()
    monkeypatch.setattr(hash_worker, "Oban", SimpleNamespace(get_instance=lambda: fake))
    return fake


def test_worker_name_matches_what_elixir_enqueues():
    assert HashWorker.new(REQUEST).worker == "dau_worker.hash_worker.HashWorker"


async def test_enqueues_a_result_job_for_elixir(monkeypatch, oban):
    monkeypatch.setattr(hash_worker, "HASHERS", {"video": FakeHasher("abc123")})

    await process_job(HashWorker.new(REQUEST))

    [result] = oban.enqueued
    assert result.worker == "DAU.MediaMatch.HashResultWorker"
    assert result.queue == "media_results"
    assert result.max_attempts == 5
    assert result.args == {
        "inbox_id": 1,
        "media_type": "video",
        "hash_value": "abc123",
        "worker_version": "fake-hasher@1",
    }


async def test_cancels_an_unsupported_media_type(monkeypatch, oban):
    monkeypatch.setattr(hash_worker, "HASHERS", {"video": FakeHasher()})

    result = await process_job(HashWorker.new({**REQUEST, "media_type": "text"}))

    assert isinstance(result, Cancel)
    assert oban.enqueued == []


async def test_a_hasher_error_raises_so_the_job_retries(monkeypatch, oban):
    monkeypatch.setattr(hash_worker, "HASHERS", {"video": FakeHasher(error=RuntimeError("boom"))})

    with pytest.raises(RuntimeError):
        await process_job(HashWorker.new(REQUEST))

    assert oban.enqueued == []


async def test_times_out_a_slow_hash(monkeypatch, oban):
    monkeypatch.setattr(hash_worker, "HASHERS", {"video": FakeHasher(delay=0.5)})
    monkeypatch.setattr(hash_worker, "HASH_TIMEOUT_SECONDS", 0.05)

    with pytest.raises(TimeoutError):
        await process_job(HashWorker.new(REQUEST))

    assert oban.enqueued == []


async def test_a_job_cancelled_while_hashing_enqueues_no_result(monkeypatch, oban):
    monkeypatch.setattr(hash_worker, "HASHERS", {"video": FakeHasher()})
    job = HashWorker.new(REQUEST)
    job._cancellation = asyncio.Event()
    job._cancellation.set()

    result = await process_job(job)

    assert isinstance(result, Cancel)
    assert oban.enqueued == []
