from __future__ import annotations
import os
from dataclasses import dataclass
from urllib.parse import urlsplit

GOOGLE_AUTH_URL = 'https://accounts.google.com/o/oauth2/v2/auth'
GOOGLE_TOKEN_URL = 'https://oauth2.googleapis.com/token'
GOOGLE_IDENTITY_ISSUERS = ('https://accounts.google.com', 'accounts.google.com')
READ_TOOLS = frozenset(('get_control_health', 'get_controller_status', 'get_fabric_health'))

def https_url(value: str, allow_local: bool = False) -> str:
    u = urlsplit(value)
    if u.fragment or u.username or u.password or u.query:
        raise ValueError('URL contains forbidden fragment, credentials or query')
    if u.scheme != 'https' and not (allow_local and u.scheme == 'http' and u.hostname in ('localhost', '127.0.0.1')):
        raise ValueError('HTTPS required')
    if not u.hostname:
        raise ValueError('hostname required')
    return value.rstrip('/')

@dataclass(frozen=True)
class Settings:
    public_base_url: str
    google_client_id: str
    google_client_secret: str
    allowed_google_email: str
    gateway_encryption_key: str
    database_url: str
    client_id: str
    allowed_redirect_uris: tuple[str, ...]
    upstream_mcp_url: str
    storage_backend: str = "postgresql"
    firestore_project_id: str = ""
    allow_sqlite_dev: bool = False
    allow_mock_upstream: bool = False
    google_prompt_consent: bool = True
    refresh_lifetime_seconds: int = 30 * 86400
    access_lifetime_seconds: int = 300
    firestore_prefix: str = 'clab_gateway_v3'

    @classmethod
    def from_env(cls) -> 'Settings':
        req = ('GATEWAY_BASE_URL','GOOGLE_CLIENT_ID','GOOGLE_CLIENT_SECRET',
               'ALLOWED_GOOGLE_EMAIL','GATEWAY_ENCRYPTION_KEY','UPSTREAM_MCP_URL')
        backend=os.getenv("GATEWAY_STORAGE_BACKEND","postgresql")
        missing=[x for x in req if not os.getenv(x)]
        if backend == "postgresql" and not os.getenv("DATABASE_URL"): missing.append("DATABASE_URL")
        if backend == "firestore" and not os.getenv("FIRESTORE_PROJECT_ID"): missing.append("FIRESTORE_PROJECT_ID")
        if missing:
            raise ValueError('Missing required configuration keys: '+','.join(missing))
        return cls(
            public_base_url=os.environ['GATEWAY_BASE_URL'],
            google_client_id=os.environ['GOOGLE_CLIENT_ID'],
            google_client_secret=os.environ['GOOGLE_CLIENT_SECRET'],
            allowed_google_email=os.environ['ALLOWED_GOOGLE_EMAIL'],
            gateway_encryption_key=os.environ['GATEWAY_ENCRYPTION_KEY'],
            database_url=os.getenv('DATABASE_URL',''),
            storage_backend=backend,
            firestore_project_id=os.getenv('FIRESTORE_PROJECT_ID',''),
            client_id=os.getenv('CIMD_CLIENT_ID','https://chatgpt.com/oauth/client.json'),
            allowed_redirect_uris=tuple(x.strip() for x in os.getenv('CHATGPT_REDIRECT_URIS','https://chatgpt.com/connector_platform_oauth_redirect').split(',') if x.strip()),
            upstream_mcp_url=os.environ['UPSTREAM_MCP_URL'],
            allow_sqlite_dev=os.getenv('ALLOW_SQLITE_DEV')=='1',
            allow_mock_upstream=os.getenv('ALLOW_MOCK_UPSTREAM')=='1',
            google_prompt_consent=os.getenv('GOOGLE_PROMPT_CONSENT','1')=='1',
            access_lifetime_seconds=int(os.getenv('GATEWAY_ACCESS_TTL','300')),
            firestore_prefix=os.getenv('FIRESTORE_PREFIX','clab_gateway_v3'),
        )

    def __post_init__(self) -> None:
        import re
        if not 30<=self.access_lifetime_seconds<=900 or not 3600<=self.refresh_lifetime_seconds<=30*86400:
            raise ValueError('Token lifetime outside admitted bounds')
        if not re.fullmatch('[a-z][a-z0-9_]{2,70}',self.firestore_prefix):
            raise ValueError('Invalid Firestore namespace')
        local = self.allow_sqlite_dev
        https_url(self.public_base_url, local)
        https_url(self.upstream_mcp_url, local)
        https_url(self.client_id)
        if not self.allow_sqlite_dev and self.client_id!='https://chatgpt.com/oauth/client.json':
            raise ValueError('Only pinned ChatGPT CIMD client admitted')
        if self.public_base_url.endswith('/mcp'):
            raise ValueError('base URL must not include /mcp')
        if not self.allowed_redirect_uris:
            raise ValueError('explicit redirect allowlist required')
        for x in self.allowed_redirect_uris:
            https_url(x, local)
        if not local and self.allowed_redirect_uris!=('https://chatgpt.com/connector_platform_oauth_redirect',):
            raise ValueError('Only exact ChatGPT redirect admitted')
        if not self.google_client_id.endswith('.apps.googleusercontent.com'):
            raise ValueError('Invalid Google OAuth client id format')
        if not self.allowed_google_email or '@' not in self.allowed_google_email:
            raise ValueError('Explicit Google user email allowlist required')
        if self.storage_backend not in ('firestore','postgresql'):
            raise ValueError('unknown storage backend')
        if self.storage_backend=='firestore' and not self.firestore_project_id:
            raise ValueError('FIRESTORE_PROJECT_ID is required')
        if self.storage_backend=='postgresql' and not self.database_url.startswith('postgresql+psycopg://') and not (local and self.database_url.startswith('sqlite:')):
            raise ValueError('Production requires PostgreSQL with psycopg driver; SQLite dev only')
        if self.allow_mock_upstream and not self.allow_sqlite_dev:
            raise ValueError('Mock upstream forbidden in production')
        if self.public_base_url.startswith('http://') and not self.allow_sqlite_dev:
            raise ValueError('No plaintext for production')
        if not self.allow_sqlite_dev and self.upstream_mcp_url != 'https://c-lab-gcp-control-w7neqnzura-ew.a.run.app/mcp':
            raise ValueError('Upstream pinned to canonical C-Lab; no arbitrary destination')
        from cryptography.fernet import Fernet
        Fernet(self.gateway_encryption_key.encode('ascii'))

    @property
    def resource(self) -> str:
        return self.public_base_url + '/mcp'

    @property
    def google_callback(self) -> str:
        return self.public_base_url + '/google/callback'
