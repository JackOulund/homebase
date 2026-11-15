import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

metadata = sa.MetaData()

oauth_clients = sa.Table(
    "oauth_clients",
    metadata,
    sa.Column("client_id", sa.Text, primary_key=True),
    sa.Column("info", postgresql.JSONB, nullable=False),
    sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    ),
)

oauth_tokens = sa.Table(
    "oauth_tokens",
    metadata,
    sa.Column("token_hash", sa.Text, primary_key=True),
    sa.Column("kind", sa.Text, nullable=False),
    sa.Column("grant_id", sa.Text, nullable=False, index=True),
    sa.Column(
        "client_id",
        sa.Text,
        sa.ForeignKey("oauth_clients.client_id", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column("scopes", postgresql.ARRAY(sa.Text), nullable=False),
    sa.Column("expires_at", sa.BigInteger, nullable=False),
)
