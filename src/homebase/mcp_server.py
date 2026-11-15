from mcp.server.auth.settings import (
    AuthSettings,
    ClientRegistrationOptions,
    RevocationOptions,
)
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette

from homebase.login import LoginPage, LoginThrottle
from homebase.oauth import HomebaseOAuthProvider
from homebase.settings import Settings


def build_mcp_app(settings: Settings, provider: HomebaseOAuthProvider) -> Starlette:
    server = MCPServer(
        "homebase",
        auth_server_provider=provider,
        auth=AuthSettings(
            issuer_url=settings.public_url,
            resource_server_url=settings.mcp_url,
            client_registration_options=ClientRegistrationOptions(enabled=True),
            revocation_options=RevocationOptions(enabled=True),
            # Every token this server stores was issued by it for this one resource.
            validate_token_resource=False,
        ),
    )

    @server.tool()
    def ping() -> str:
        """Check that the homebase server is reachable and you are signed in."""
        return "pong"

    login_page = LoginPage(provider, settings, LoginThrottle())
    server.custom_route("/login", methods=["GET", "POST"])(login_page.handle)

    return server.streamable_http_app(
        stateless_http=True,
        json_response=True,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=[settings.public_host],
            allowed_origins=[settings.public_url],
        ),
    )
