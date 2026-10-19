import asyncio

from oban import Cancel, Job, Oban, worker

from dau_worker.contract import HASH_QUEUE, RESULT_MAX_ATTEMPTS, RESULT_QUEUE, RESULT_WORKER, HASH_TIMEOUT_SECONDS
from dau_worker.hashers import HASHERS

# No max_attempts: dau-dashboard sets it when it inserts these jobs, and oban-py only applies
# decorator options to jobs Python inserts itself.
@worker(queue=HASH_QUEUE)
class HashWorker:
    async def process(self, job):
        media_type = job.args["media_type"]
        hasher = HASHERS.get(media_type)

        if hasher is None:
            return Cancel(f"unsupported media_type: {media_type}")

        # runs the hasher in a new thread so the worker is still responsive.
        # on timeout: it raises with TimeoutError. This marks the job as `retryable`.
        # Oban tries to run the job again based on backoff period.
        #
        # NOTE: cancellation is cooperative. it does not stop the thread: python cannot stop a
        # running thread, and feluda has no cancel hook, so the download and hash run to the end
        # and only then do we check. the same goes for the timeout above: it stops the job, but
        # the thread keeps running in the background and its result is thrown away.
        hash_value = await asyncio.wait_for(
            asyncio.to_thread(hasher.hash, job.args["file_key"]),
            timeout=HASH_TIMEOUT_SECONDS,
        )

        # if a job gets cancelled, do not enqueue the result.
        if job.cancelled():
            return Cancel("cancelled while hashing")

        await Oban.get_instance().enqueue(
            Job(
                RESULT_WORKER,
                queue=RESULT_QUEUE,
                max_attempts=RESULT_MAX_ATTEMPTS,
                args={
                    "inbox_id": job.args["inbox_id"],
                    "media_type": media_type,
                    "hash_value": hash_value,
                    "worker_version": hasher.algorithm,
                },
            )
        )
