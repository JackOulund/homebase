import os
from dataclasses import dataclass
from urllib.parse import urlparse

LOCAL_DATABASE_URL = "postgresql+psycopg://homebase:homebase@localhost:54329/homebase"


@dataclass(frozen=True)
class Settings:
    public_url: str
    database_url: str
    login_password_hash: str

    @classmethod
    def from_environment(cls) -> "Settings":
        return cls(
            public_url=os.environ.get("PUBLIC_URL", "http://localhost:8000").rstrip(
                "/"
            ),
            database_url=os.environ.get("DATABASE_URL", LOCAL_DATABASE_URL),
            login_password_hash=os.environ.get("LOGIN_PASSWORD_HASH", ""),
        )

    @property
    def mcp_url(self) -> str:
        return f"{self.public_url}/mcp"

    @property
    def public_host(self) -> str:
        return urlparse(self.public_url).netloc
