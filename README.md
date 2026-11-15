# homebase

Home chore and task backend: FastAPI + Postgres, with an MCP interface to come.

## Develop

```bash
uv sync
docker compose up -d --wait db
uv run pytest
docker compose up --build
```

The tests need the local Postgres and create their own `homebase_test` database.
The app answers on http://localhost:8000/health and serves MCP on `/mcp`.

## Sign-in

The MCP endpoint is protected by OAuth with a single password. Only its scrypt
hash is stored, in `LOGIN_PASSWORD_HASH`. Generate one on the server with:

```bash
docker exec -it homebase-app-1 python -m homebase.password
```

Put the printed line in `/opt/homebase/.env` and redeploy. Clients may only
register Claude's callback (`https://claude.ai/api/mcp/auth_callback`) or a
loopback address.

## Tools

- `ping`: check that the server is reachable and you are signed in.
- `add_task`: add a chore or one-off job, optionally with estimate, interval, room and notes.
- `list_tasks`: list all open tasks.
- `complete_task`: mark a task done, optionally with the actual minutes it took.
- `update_task`: change a task's name, estimate, interval, room or notes.
- `remove_task`: remove a task that no longer applies.
- `suggest_tasks`: suggest up to three due tasks that fit in the minutes available.
- `get_time_history`: average actual minutes per task, to improve estimates.
- `get_profile`: read the lasting facts about the home.
- `set_profile_entry`: save or update a fact about the home.
- `remove_profile_entry`: remove a fact from the home profile.

## Deploy

Merging to `main` runs the tests, pushes an image to GHCR and deploys it to the
VPS over SSH. The deploy job is skipped until the repository variable
`DEPLOY_ENABLED` is `true`.

One-time server setup:

1. Install Docker Engine with the compose plugin.
2. Create `/opt/homebase`, writable by the deploy user.
3. Copy `deploy/.env.example` to `/opt/homebase/.env` and fill it in.

Repository secrets:

| Secret | Value |
|---|---|
| `DEPLOY_HOST` | Server IP or hostname |
| `DEPLOY_USER` | SSH user that can run `docker` |
| `DEPLOY_SSH_KEY` | Private key of a dedicated deploy key pair |
| `DEPLOY_KNOWN_HOSTS` | Output of `ssh-keyscan <host>` |
