import base64
import hashlib
import secrets
from dataclasses import replace
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from homebase.app import create_app
from tests.conftest import PASSWORD, PUBLIC_URL

CLAUDE_CALLBACK = "https://claude.ai/api/mcp/auth_callback"
MCP_URL = f"{PUBLIC_URL}/mcp"
MCP_HEADERS = {"Accept": "application/json, text/event-stream"}
INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "test", "version": "1"},
    },
}


def register(client, redirect_uri=CLAUDE_CALLBACK):
    return client.post(
        "/register",
        json={
            "client_name": "Claude",
            "redirect_uris": [redirect_uri],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
        },
    )


def pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


def start_login(
    client, client_id: str, challenge: str, state: str = "state-123"
) -> str:
    response = client.get(
        "/authorize",
        params={
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": CLAUDE_CALLBACK,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": state,
            "resource": MCP_URL,
        },
    )
    assert response.status_code == 302
    login_url = urlparse(response.headers["location"])
    assert login_url.path == "/login"
    return parse_qs(login_url.query)["txn"][0]


def submit_password(client, transaction: str, password: str):
    return client.post("/login", data={"txn": transaction, "password": password})


def sign_in(client) -> dict:
    client_id = register(client).json()["client_id"]
    verifier, challenge = pkce_pair()
    transaction = start_login(client, client_id, challenge)
    redirect = submit_password(client, transaction, PASSWORD)
    code = parse_qs(urlparse(redirect.headers["location"]).query)["code"][0]
    token_response = client.post(
        "/token",
        data={
            "grant_type": "authorization_code",
            "client_id": client_id,
            "code": code,
            "code_verifier": verifier,
            "redirect_uri": CLAUDE_CALLBACK,
        },
    )
    assert token_response.status_code == 200, token_response.text
    return {"client_id": client_id, **token_response.json()}


def call_mcp(client, access_token: str | None):
    headers = dict(MCP_HEADERS)
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    return client.post("/mcp", json=INITIALIZE, headers=headers)


def test_mcp_without_token_is_refused_and_points_to_sign_in_details(client):
    response = call_mcp(client, access_token=None)

    assert response.status_code == 401
    assert (
        f'resource_metadata="{PUBLIC_URL}/.well-known/oauth-protected-resource/mcp"'
        in response.headers["www-authenticate"]
    )


def test_mcp_with_made_up_token_is_refused(client):
    assert call_mcp(client, access_token="made-up").status_code == 401


def test_discovery_documents_describe_this_server(client):
    resource = client.get("/.well-known/oauth-protected-resource/mcp").json()
    server = client.get("/.well-known/oauth-authorization-server").json()

    assert resource["resource"] == MCP_URL
    assert resource["authorization_servers"] == [PUBLIC_URL]
    assert server["issuer"] == PUBLIC_URL
    assert server["registration_endpoint"] == f"{PUBLIC_URL}/register"
    assert server["code_challenge_methods_supported"] == ["S256"]


def test_health_stays_public(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_registration_accepts_claude_callback(client):
    response = register(client)

    assert response.status_code == 201
    assert response.json()["client_id"]


def test_registration_accepts_claude_code_loopback_callback(client):
    assert register(client, "http://localhost:3118/callback").status_code == 201
    assert register(client, "http://127.0.0.1:50000/callback").status_code == 201


def test_registration_rejects_any_other_callback(client):
    for redirect_uri in [
        "https://evil.example/callback",
        "https://claude.ai.evil.example/api/mcp/auth_callback",
        "http://claude.ai/api/mcp/auth_callback",
        "https://localhost/callback",
    ]:
        response = register(client, redirect_uri)

        assert response.status_code == 400, redirect_uri
        assert response.json()["error"] == "invalid_redirect_uri"


def test_login_page_shows_who_is_asking_and_where_it_returns(client):
    client_id = register(client).json()["client_id"]
    transaction = start_login(client, client_id, pkce_pair()[1])

    page = client.get("/login", params={"txn": transaction})

    assert page.status_code == 200
    assert "Claude" in page.text
    assert "claude.ai" in page.text
    assert page.headers["x-frame-options"] == "DENY"
    assert page.headers["cache-control"] == "no-store"


def test_login_page_with_unknown_transaction_is_rejected(client):
    assert client.get("/login", params={"txn": "nope"}).status_code == 400
    assert submit_password(client, "nope", PASSWORD).status_code == 400


def test_wrong_password_does_not_sign_in(client):
    client_id = register(client).json()["client_id"]
    transaction = start_login(client, client_id, pkce_pair()[1])

    response = submit_password(client, transaction, "wrong")

    assert response.status_code == 401
    assert "location" not in response.headers


def test_correct_password_returns_to_claude_with_code_and_state(client):
    client_id = register(client).json()["client_id"]
    transaction = start_login(client, client_id, pkce_pair()[1], state="abc")

    response = submit_password(client, transaction, PASSWORD)

    assert response.status_code == 302
    location = urlparse(response.headers["location"])
    assert f"{location.scheme}://{location.netloc}{location.path}" == CLAUDE_CALLBACK
    query = parse_qs(location.query)
    assert query["state"] == ["abc"]
    assert query["code"]


def test_login_transaction_cannot_be_reused(client):
    client_id = register(client).json()["client_id"]
    transaction = start_login(client, client_id, pkce_pair()[1])
    submit_password(client, transaction, PASSWORD)

    assert submit_password(client, transaction, PASSWORD).status_code == 400


def test_signed_in_client_can_call_mcp(client):
    tokens = sign_in(client)

    response = call_mcp(client, tokens["access_token"])

    assert response.status_code == 200, response.text


def test_authorization_code_cannot_be_exchanged_twice(client):
    client_id = register(client).json()["client_id"]
    verifier, challenge = pkce_pair()
    transaction = start_login(client, client_id, challenge)
    redirect = submit_password(client, transaction, PASSWORD)
    code = parse_qs(urlparse(redirect.headers["location"]).query)["code"][0]
    exchange = {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "code": code,
        "code_verifier": verifier,
        "redirect_uri": CLAUDE_CALLBACK,
    }

    assert client.post("/token", data=exchange).status_code == 200
    second = client.post("/token", data=exchange)

    assert second.status_code == 400
    assert second.json()["error"] == "invalid_grant"


def test_refresh_rotates_tokens_and_retires_the_old_ones(client):
    tokens = sign_in(client)
    refresh = {
        "grant_type": "refresh_token",
        "client_id": tokens["client_id"],
        "refresh_token": tokens["refresh_token"],
    }

    refreshed = client.post("/token", data=refresh)

    assert refreshed.status_code == 200, refreshed.text
    new_tokens = refreshed.json()
    assert new_tokens["access_token"] != tokens["access_token"]
    assert new_tokens["refresh_token"] != tokens["refresh_token"]
    assert call_mcp(client, new_tokens["access_token"]).status_code == 200
    assert call_mcp(client, tokens["access_token"]).status_code == 401
    reused = client.post("/token", data=refresh)
    assert reused.status_code == 400
    assert reused.json()["error"] == "invalid_grant"


def test_tokens_survive_a_restart(client, settings):
    tokens = sign_in(client)

    with TestClient(create_app(settings), base_url=PUBLIC_URL) as restarted:
        assert call_mcp(restarted, tokens["access_token"]).status_code == 200


def test_tokens_are_not_stored_in_readable_form(client, database_url):
    import sqlalchemy as sa

    tokens = sign_in(client)

    engine = sa.create_engine(database_url)
    with engine.connect() as connection:
        stored = connection.execute(sa.text("select * from oauth_tokens")).all()
    engine.dispose()

    assert stored
    assert tokens["access_token"] not in str(stored)
    assert tokens["refresh_token"] not in str(stored)


def test_login_locks_after_repeated_wrong_passwords(client):
    client_id = register(client).json()["client_id"]
    for _ in range(5):
        transaction = start_login(client, client_id, pkce_pair()[1])
        assert submit_password(client, transaction, "wrong").status_code == 401

    transaction = start_login(client, client_id, pkce_pair()[1])

    assert submit_password(client, transaction, PASSWORD).status_code == 429


def test_sign_in_is_impossible_when_no_password_is_configured(settings, empty_database):
    app = create_app(replace(settings, login_password_hash=""))
    with TestClient(app, base_url=PUBLIC_URL, follow_redirects=False) as client:
        client_id = register(client).json()["client_id"]
        transaction = start_login(client, client_id, pkce_pair()[1])

        assert submit_password(client, transaction, "").status_code == 401
        assert submit_password(client, transaction, PASSWORD).status_code == 401
