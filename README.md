# dau-worker

Hash worker for [dau-dashboard](https://github.com/tattle-made/dau-dashboard). It runs `media_hash`
jobs from dau-dashboard's Oban queue (oban-py), hashes the media file with feluda's `MediaHash`, and enqueues a `media_results` job back for dau-dashboard.

dau-dashboard owns the database schema. Run its migrations (`mix ecto.migrate`) before starting
this worker; the worker refuses to start until the Oban tables exist.

Never run `oban install` or `oban uninstall`: dau-dashboard's migrations own the schema, and `uninstall` would also drop dau-dashboard's jobs.

## Setup

```bash
uv sync
cp .env.example .env   # then fill in the AWS values
```

`AWS_BUCKET` must be the bucket dau-dashboard uploads media to.

## Run

```bash
uv run --env-file .env oban start
```

`--env-file` loads `.env` before the command starts, in any shell.

## Docker

```bash
docker build -t dau-worker .
docker run --env-file .env dau-worker
```

Inside a container, `localhost` in `OBAN_DSN` is the container itself. Point it at the
database host instead (for example the compose service name, or `host.docker.internal`).

## Test

```bash
uv run --env-file .env pytest
```

The schema contract test needs dau-dashboard's test database, migrated with
`MIX_ENV=test mix ecto.migrate`, and `DAU_TEST_DSN` set (see `.env.example`). Without it, that test
is skipped.
