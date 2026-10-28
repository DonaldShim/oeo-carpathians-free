import json
import httpx
import pytest
from fastapi import HTTPException
from gateway.upstream import Upstream, _parse


def test_sse_parser_extracts_rpc_result():
    x=httpx.Response(200,headers={'content-type':'text/event-stream'},text='event: message\ndata: {"jsonrpc":"2.0","id":1,"result":{"content":[]}}\n\n')
    assert _parse(x)['result']['content']==[]


def test_sse_parser_fail_closed():
    x=httpx.Response(200,headers={'content-type':'text/event-stream'},text='data: not-json\n\n')
    with pytest.raises(HTTPException):_parse(x)


def test_unknown_upstream_tool_never_contacts_network():
    from gateway.config import Settings
    from cryptography.fernet import Fernet
    settings=Settings(public_base_url="http://127.0.0.1:8080",google_client_id="test.apps.googleusercontent.com",google_client_secret="x",allowed_google_email="x@example.org",gateway_encryption_key=Fernet.generate_key().decode(),database_url="sqlite:////tmp/unimportant.db",client_id="https://chatgpt.com/oauth/client.json",allowed_redirect_uris=("https://chatgpt.com/connector_platform_oauth_redirect",),upstream_mcp_url="http://127.0.0.1:9090/mcp",allow_sqlite_dev=True)
    upstream=Upstream(settings)
    with pytest.raises(HTTPException) as e:upstream.invoke('submit_registered_scientific_carrier','google-access')
    assert e.value.status_code==403


def test_pinned_canonical_upstream_in_prod(tmp_path):
    from dataclasses import replace
    from gateway.config import Settings
    from cryptography.fernet import Fernet
    template=Settings(public_base_url='https://gateway.example',
        google_client_id='test.apps.googleusercontent.com',google_client_secret='x',
        allowed_google_email='tester@example.org',gateway_encryption_key=Fernet.generate_key().decode(),
        database_url='postgresql+psycopg://user:pass@dbhost/db',
        client_id='https://chatgpt.com/oauth/client.json',
        allowed_redirect_uris=('https://chatgpt.com/connector_platform_oauth_redirect',),
        upstream_mcp_url='https://c-lab-gcp-control-w7neqnzura-ew.a.run.app/mcp')
    assert template.allow_sqlite_dev is False
    with pytest.raises(ValueError):replace(template,upstream_mcp_url='https://evil.example/mcp')
