"""End-to-end check that this worker and dau-dashboard agree on the database.

Runs only when DAU_TEST_DSN points at dau-dashboard's test database, migrated with
`MIX_ENV=test mix ecto.migrate`; skipped otherwise.

1. Insert a media_hash job straight into oban_jobs, shaped the way dau-dashboard's
   MediaMatch.create_job/2 inserts it (worker string, queue, args, max_attempts), relying on
   the Elixir schema's column defaults for state and scheduled_at.
2. Start real oban-py (leadership=False, queue media_hash) on the tables dau-dashboard's Ecto
   migrations created. Only HASHERS is faked, so nothing is downloaded from S3.
3. Wait for the job to reach `completed`: oban-py fetched, ran, and acked it on that schema.
4. Assert the media_results job has exactly the worker, queue, max_attempts and args that
   dau-dashboard's HashResultWorker expects.
5. Delete both rows in a `finally`, so the shared test database stays clean.

It fails if an oban-py upgrade stops working with the Elixir tables, or if either side
renames a queue, worker string, or argument.
"""

import asyncio
import os

import psycopg
import pytest
from oban import Oban
from psycopg.types.json import Jsonb

from dau_worker import hash_worker

DSN = os.environ.get("DAU_TEST_DSN")

pytestmark = [
    pytest.mark.contract,
    pytest.mark.skipif(not DSN, reason="set DAU_TEST_DSN to the migrated dau-dashboard test database"),
]

REQUEST = {
    "inbox_id": 1,
    "file_key": "temp/0b6c2f2e-6a43-4f7e-9b1d-2f0c1e9a7d10",
    "media_type": "video",
}


class FakeHasher:
    algorithm = "fake-hasher@1"

    def hash(self, file_key):
        return "contract-test-hash"


async def wait_for_state(conn, job_id, state, timeout=15):
    for _ in range(timeout * 10):
        cur = await conn.execute("SELECT state::text FROM oban_jobs WHERE id = %s", (job_id,))
        (current,) = await cur.fetchone()
        if current == state:
            return
        await asyncio.sleep(0.1)
    raise AssertionError(f"job {job_id} did not reach {state}, last state {current}")


async def test_runs_an_elixir_shaped_job_and_enqueues_the_result(monkeypatch):
    monkeypatch.setattr(hash_worker, "HASHERS", {"video": FakeHasher()})
    pool = await Oban.create_pool(DSN)

    async with await psycopg.AsyncConnection.connect(DSN, autocommit=True) as conn:
        cur = await conn.execute(
            "INSERT INTO oban_jobs (worker, queue, args, max_attempts) VALUES (%s, %s, %s, %s) RETURNING id",
            ("dau_worker.hash_worker.HashWorker", "media_hash", Jsonb(REQUEST), 5),
        )
        (job_id,) = await cur.fetchone()

        try:
            async with Oban(pool=pool, queues={"media_hash": 1}, leadership=False):
                await wait_for_state(conn, job_id, "completed")

            cur = await conn.execute(
                "SELECT worker, queue, max_attempts, args FROM oban_jobs WHERE queue = 'media_results' AND args @> %s",
                (Jsonb({"hash_value": "contract-test-hash"}),),
            )
            assert await cur.fetchone() == (
                "DAU.MediaMatch.HashResultWorker",
                "media_results",
                5,
                {
                    "inbox_id": 1,
                    "media_type": "video",
                    "hash_value": "contract-test-hash",
                    "worker_version": "fake-hasher@1",
                },
            )
        finally:
            await conn.execute(
                "DELETE FROM oban_jobs WHERE id = %s OR args @> %s",
                (job_id, Jsonb({"hash_value": "contract-test-hash"})),
            )

    await pool.close()
