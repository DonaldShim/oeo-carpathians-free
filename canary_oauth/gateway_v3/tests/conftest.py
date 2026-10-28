import os
os.environ.update({
    'GATEWAY_BASE_URL':'http://127.0.0.1:8080',
    'GOOGLE_CLIENT_ID':'mock-client.apps.googleusercontent.com',
    'GOOGLE_CLIENT_SECRET':'mock-secret-in-test-only',
    'ALLOWED_GOOGLE_EMAIL':'tester@example.org',
    'GATEWAY_ENCRYPTION_KEY':'pHhSJC8FFtyDuTQupWxZo8qULkwyOA2lnI1MiZZJaHg=',
    'DATABASE_URL':'sqlite:////tmp/just-for-test-fixture.db',
    'UPSTREAM_MCP_URL':'http://127.0.0.1:9090/mcp',
    'ALLOW_SQLITE_DEV':'1',
    'ALLOW_MOCK_UPSTREAM':'1',
    'CHATGPT_REDIRECT_URIS':'https://chatgpt.com/connector_platform_oauth_redirect',
})

# The integration fixture lives in test_gateway; make it visible to all sibling tests.
