"""Official OpenAI Responses API -> existing C-Lab OAuth CANARY MCP.
This is NOT a ChatGPT account/plugin connection or ChatGPT OAuth-refresh test.
The caller must handle its own OAuth login, secure token vault and refresh.
No API calls on import, no token storage or logging.
"""
CANARY_MCP='https://c-lab-oauth-canary-20261025.onrender.com/mcp'

def mcp_tool(access_token: str) -> dict:
    if not isinstance(access_token,str) or len(access_token)<32 or '\n' in access_token:
        raise ValueError('Provide an existing current OAuth access token')
    return {
        'type':'mcp', 'server_label':'clab_auth_canary',
        'server_url':CANARY_MCP, 'authorization':access_token,
        'allowed_tools':['canary_control_health'], 'require_approval':'never'
    }

def call_canary(openai_client, access_token: str, model='gpt-6'):
    return openai_client.responses.create(
        model=model,
        input='Call canary_control_health once and report only its ok boolean.',
        tools=[mcp_tool(access_token)])
