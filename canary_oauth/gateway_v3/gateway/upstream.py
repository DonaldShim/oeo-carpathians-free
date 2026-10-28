"""Read-only, fixed-destination MCP adapter. No write tools or arbitrary URLs."""
import json
import httpx
from fastapi import HTTPException
from .config import Settings, READ_TOOLS
from .bounded_http import request,BoundedHTTPError

TOOL_META = {
    'get_control_health':'Read-only live health of the canonical C-Lab control adapter',
    'get_controller_status':'Read-only status of the canonical C-Lab controller',
    'get_fabric_health':'Read-only probes for canonical C-Fabric components',
}

class Upstream:
    def __init__(self,settings:Settings):
        self.settings=settings

    def invoke(self,name:str,token:str):
        if name not in READ_TOOLS:
            raise HTTPException(status_code=403,detail='tool not allowlisted')
        if self.settings.allow_mock_upstream:
            return {'content':[{'type':'text','text':json.dumps({'test_only':True,'tool':name})}], 'isError':False}
        headers={'Authorization':'Bearer '+token,
                 'Accept':'application/json, text/event-stream',
                 'Content-Type':'application/json',
                 'MCP-Protocol-Version':'2025-06-18'}
        class Client:
            def __enter__(self):return self
            def __exit__(self,*args):return False
            def post(self,url,headers=None,json=None):
                try:return request('POST',url,headers=headers,json_body=json)
                except BoundedHTTPError:raise HTTPException(status_code=502,detail='bounded upstream request failed') from None
        with Client() as client:
            init={'jsonrpc':'2.0','id':'init','method':'initialize',
                  'params':{'protocolVersion':'2025-06-18','capabilities':{},
                            'clientInfo':{'name':'c-lab-oauth-read-only-bridge','version':'1.0.0'}}}
            resp=client.post(self.settings.upstream_mcp_url,headers=headers,json=init)
            if resp.status_code!=200:
                raise HTTPException(status_code=502,detail='upstream initialization failed')
            initialized=_parse(resp)
            if 'error' in initialized or initialized.get('id')!='init' or not isinstance(initialized.get('result'),dict):
                raise HTTPException(status_code=502,detail='upstream rejected initialization')
            session_id=resp.headers.get('mcp-session-id')
            if session_id:
                if len(session_id)>200 or any(not (c.isalnum() or c in '-_') for c in session_id):
                    raise HTTPException(status_code=502,detail='invalid upstream session')
                headers['mcp-session-id']=session_id
            client.post(self.settings.upstream_mcp_url,headers=headers,
                        json={'jsonrpc':'2.0','method':'notifications/initialized'})
            result=client.post(self.settings.upstream_mcp_url,headers=headers,
                json={'jsonrpc':'2.0','id':'read','method':'tools/call','params':{'name':name,'arguments':{}}})
            if result.status_code!=200:
                raise HTTPException(status_code=502,detail='upstream read failed')
            if len(result.content)>262144:
                raise HTTPException(status_code=502,detail='upstream output exceeds bound')
            payload=_parse(result)
            if 'error' in payload or payload.get('id')!='read':
                raise HTTPException(status_code=502,detail='upstream tool returned protocol error')
            if not isinstance(payload.get('result'),dict):
                raise HTTPException(status_code=502,detail='invalid upstream response')
            return payload['result']

def _parse(response:httpx.Response):
    ct=response.headers.get('content-type','')
    if 'text/event-stream' in ct:
        for line in response.text.splitlines():
            if line.startswith('data:'):
                try:
                    obj=json.loads(line[5:].strip())
                    if isinstance(obj,dict) and ('result' in obj or 'error' in obj):
                        return obj
                except ValueError: pass
        raise HTTPException(status_code=502,detail='unparseable upstream stream')
    try:
        val=response.json()
    except ValueError:
        raise HTTPException(status_code=502,detail='upstream did not return JSON')
    if not isinstance(val,dict):
        raise HTTPException(status_code=502,detail='invalid upstream JSON')
    return val
