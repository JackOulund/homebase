import hashlib
import secrets
import time
from dataclasses import dataclass
from urllib.parse import urlencode, urlparse

import sqlalchemy as sa
from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    RefreshToken,
    RegistrationError,
    TokenError,
    construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from homebase.db import oauth_clients, oauth_tokens
from homebase.settings import Settings

CLAUDE_CALLBACK = "https://claude.ai/api/mcp/auth_callback"
LOOPBACK_HOSTS = {"localhost", "127.0.0.1"}
OWNER = "owner"

ACCESS_TOKEN_SECONDS = 60 * 60
REFRESH_TOKEN_SECONDS = 60 * 24 * 60 * 60
AUTHORIZATION_CODE_SECONDS = 5 * 60
LOGIN_TRANSACTION_SECONDS = 10 * 60
UNUSED_CLIENT_SECONDS = 24 * 60 * 60
MAX_PENDING_LOGINS = 500

ACCESS = "access"
REFRESH = "refresh"


def is_allowed_redirect_uri(redirect_uri: str) -> bool:
    if redirect_uri == CLAUDE_CALLBACK:
        return True
    parsed = urlparse(redirect_uri)
    return parsed.scheme == "http" and parsed.hostname in LOOPBACK_HOSTS


def fingerprint(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass(frozen=True)
class LoginTransaction:
    client: OAuthClientInformationFull
    params: AuthorizationParams
    expires_at: float


class HomebaseOAuthProvider:
    def __init__(self, engine: AsyncEngine, settings: Settings) -> None:
        self._engine = engine
        self._settings = settings
        self._login_transactions: dict[str, LoginTransaction] = {}
        self._authorization_codes: dict[str, AuthorizationCode] = {}

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        async with self._engine.connect() as connection:
            info = await connection.scalar(
                sa.select(oauth_clients.c.info).where(
                    oauth_clients.c.client_id == client_id
                )
            )
        return OAuthClientInformationFull.model_validate(info) if info else None

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        redirect_uris = [str(uri) for uri in client_info.redirect_uris or []]
        if not redirect_uris or not all(
            is_allowed_redirect_uri(uri) for uri in redirect_uris
        ):
            raise RegistrationError(
                "invalid_redirect_uri",
                "Only Claude's callback and loopback addresses are accepted",
            )
        async with self._engine.begin() as connection:
            await self._delete_unused_clients(connection)
            await connection.execute(
                sa.insert(oauth_clients).values(
                    client_id=client_info.client_id,
                    info=client_info.model_dump(mode="json"),
                )
            )

    async def authorize(
        self, client: OAuthClientInformationFull, params: AuthorizationParams
    ) -> str:
        self._forget_expired()
        while len(self._login_transactions) >= MAX_PENDING_LOGINS:
            self._login_transactions.pop(next(iter(self._login_transactions)))
        transaction_id = secrets.token_urlsafe(32)
        self._login_transactions[transaction_id] = LoginTransaction(
            client=client,
            params=params,
            expires_at=time.time() + LOGIN_TRANSACTION_SECONDS,
        )
        return f"{self._settings.public_url}/login?{urlencode({'txn': transaction_id})}"

    def find_login_transaction(self, transaction_id: str) -> LoginTransaction | None:
        self._forget_expired()
        return self._login_transactions.get(transaction_id)

    def complete_login(self, transaction_id: str) -> str:
        transaction = self._login_transactions.pop(transaction_id)
        params = transaction.params
        code = AuthorizationCode(
            code=secrets.token_urlsafe(32),
            scopes=params.scopes or [],
            expires_at=time.time() + AUTHORIZATION_CODE_SECONDS,
            client_id=transaction.client.client_id,
            code_challenge=params.code_challenge,
            redirect_uri=params.redirect_uri,
            redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
            resource=self._settings.mcp_url,
            subject=OWNER,
        )
        self._authorization_codes[code.code] = code
        return construct_redirect_uri(
            str(params.redirect_uri), code=code.code, state=params.state
        )

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        self._forget_expired()
        return self._authorization_codes.get(authorization_code)

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthToken:
        if self._authorization_codes.pop(authorization_code.code, None) is None:
            raise TokenError("invalid_grant", "Authorization code was already used")
        async with self._engine.begin() as connection:
            return await self._issue_tokens(
                connection, authorization_code.client_id, authorization_code.scopes
            )

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> RefreshToken | None:
        row = await self._find_token(refresh_token, REFRESH)
        if row is None:
            return None
        return RefreshToken(
            token=refresh_token,
            client_id=row.client_id,
            scopes=row.scopes,
            expires_at=row.expires_at,
            resource=self._settings.mcp_url,
            subject=OWNER,
        )

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        async with self._engine.begin() as connection:
            retired = await self._delete_grant_of(connection, refresh_token.token)
            if not retired:
                raise TokenError("invalid_grant", "Refresh token was already used")
            return await self._issue_tokens(connection, refresh_token.client_id, scopes)

    async def load_access_token(self, token: str) -> AccessToken | None:
        row = await self._find_token(token, ACCESS)
        if row is None:
            return None
        return AccessToken(
            token=token,
            client_id=row.client_id,
            scopes=row.scopes,
            expires_at=row.expires_at,
            resource=self._settings.mcp_url,
            subject=OWNER,
        )

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        async with self._engine.begin() as connection:
            await self._delete_grant_of(connection, token.token)

    async def exchange_identity_assertion(self, client, params) -> OAuthToken:
        raise TokenError(
            "unsupported_grant_type", "Identity assertions are not supported"
        )

    async def _find_token(self, token: str, kind: str) -> sa.Row | None:
        async with self._engine.connect() as connection:
            result = await connection.execute(
                sa.select(oauth_tokens).where(
                    oauth_tokens.c.token_hash == fingerprint(token),
                    oauth_tokens.c.kind == kind,
                    oauth_tokens.c.expires_at > int(time.time()),
                )
            )
            return result.first()

    async def _issue_tokens(
        self, connection: AsyncConnection, client_id: str, scopes: list[str]
    ) -> OAuthToken:
        now = int(time.time())
        access_token = secrets.token_urlsafe(32)
        refresh_token = secrets.token_urlsafe(32)
        grant_id = secrets.token_hex(16)
        await connection.execute(
            sa.delete(oauth_tokens).where(oauth_tokens.c.expires_at <= now)
        )
        await connection.execute(
            sa.insert(oauth_tokens),
            [
                {
                    "token_hash": fingerprint(access_token),
                    "kind": ACCESS,
                    "grant_id": grant_id,
                    "client_id": client_id,
                    "scopes": scopes,
                    "expires_at": now + ACCESS_TOKEN_SECONDS,
                },
                {
                    "token_hash": fingerprint(refresh_token),
                    "kind": REFRESH,
                    "grant_id": grant_id,
                    "client_id": client_id,
                    "scopes": scopes,
                    "expires_at": now + REFRESH_TOKEN_SECONDS,
                },
            ],
        )
        return OAuthToken(
            access_token=access_token,
            token_type="Bearer",
            expires_in=ACCESS_TOKEN_SECONDS,
            refresh_token=refresh_token,
            scope=" ".join(scopes) or None,
        )

    async def _delete_grant_of(self, connection: AsyncConnection, token: str) -> bool:
        grant_id = (
            sa.select(oauth_tokens.c.grant_id)
            .where(oauth_tokens.c.token_hash == fingerprint(token))
            .scalar_subquery()
        )
        result = await connection.execute(
            sa.delete(oauth_tokens).where(oauth_tokens.c.grant_id == grant_id)
        )
        return result.rowcount > 0

    async def _delete_unused_clients(self, connection: AsyncConnection) -> None:
        has_tokens = sa.exists().where(
            oauth_tokens.c.client_id == oauth_clients.c.client_id
        )
        cutoff = sa.func.now() - sa.text(f"interval '{UNUSED_CLIENT_SECONDS} seconds'")
        await connection.execute(
            sa.delete(oauth_clients).where(
                oauth_clients.c.created_at < cutoff, ~has_tokens
            )
        )

    def _forget_expired(self) -> None:
        now = time.time()
        for transaction_id, transaction in list(self._login_transactions.items()):
            if transaction.expires_at < now:
                del self._login_transactions[transaction_id]
        for code, authorization_code in list(self._authorization_codes.items()):
            if authorization_code.expires_at < now:
                del self._authorization_codes[code]
