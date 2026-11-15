# homebase

Home chore and task backend: FastAPI + Postgres, with an MCP interface to come.

## Develop

```bash
uv sync
uv run pytest
docker compose up --build
```

The app answers on http://localhost:8000/health.

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
