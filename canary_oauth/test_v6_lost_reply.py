"""V6 loss-of-successful-refresh-response replay using actual isolated canary source.
NO production tokens, NO Google/ChatGPT credentials, NO internet requests.
"""
import os, secrets, asyncio, json, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ["CANARY_REFRESH_RECOVERY_KEY"]=secrets.token_urlsafe(64)
os.environ["CANARY_V6_RECOVERY_ENABLED"]="1"
import httpx
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from canary_oauth import canary_server as s

s.READY=True
s.ISSUER="https://isolated.example.test"
s.ALLOWED_EMAIL="test-identity@example.test"
s.PEPPER=secrets.token_urlsafe(48)
s.dbengine=create_engine("sqlite://",poolclass=StaticPool,connect_args={"check_same_thread":False})
s.Db=sessionmaker(bind=s.dbengine)
s.Base.metadata.create_all(s.dbengine)
checks=[]
def ok(name,condition):
    assert condition,name
    checks.append(name)
def seed():
    with s.Db.begin() as db:
        fam=s.Family(user_hash=s.hashed("fixture-"+secrets.token_urlsafe(16)),
            client=s.PROBE_CLIENT,resource=s.ISSUER+"/mcp",
            scope="c_lab_canary.read offline_access",policy_hash=s.policy_binding(s.PROBE_CLIENT))
        db.add(fam);db.flush()
        return s.mint(db,fam.id,fam.scope)
now=s.clock()
s.clock=lambda:now
async def test():
    global now
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=s.app),base_url=s.ISSUER) as c:
        p=seed()
        base={"grant_type":"refresh_token","client_id":s.PROBE_CLIENT,"resource":s.ISSUER+"/mcp","refresh_token":p["refresh_token"]}
        r=await c.post("/token",data=base)
        ok("baseline_refresh",r.status_code==200)
        now+=6
        ok("baseline_lost_response_fails",(await c.post("/token",data=base)).status_code==400)
        p=seed();base["refresh_token"]=p["refresh_token"]
        key=secrets.token_urlsafe(48)
        r=await c.post("/token",data=base,headers={"Idempotency-Key":key})
        ok("first_rotation",r.status_code==200)
        now+=6
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=s.app),base_url=s.ISSUER) as fresh:
            replay=await fresh.post("/token",data=base,headers={"Idempotency-Key":key})
            ok("successor_restored",replay.status_code==200 and replay.json()==r.json())
            ok("wrong_attempt_denied",(await fresh.post("/token",data=base,headers={"Idempotency-Key":secrets.token_urlsafe(48)})).status_code==400)
        p=seed();base["refresh_token"]=p["refresh_token"]
        key=secrets.token_urlsafe(48)
        r=await c.post("/token",data=base,headers={"Idempotency-Key":key})
        ok("second_rotation",r.status_code==200)
        now+=121
        ok("expired_receipt_denied",(await c.post("/token",data=base,headers={"Idempotency-Key":key})).status_code==400)
        ok("weak_nonce_denied",(await c.post("/token",data=base,headers={"Idempotency-Key":"weak"})).status_code==400)
        p=seed();base["refresh_token"]=p["refresh_token"];key=secrets.token_urlsafe(48)
        r=await c.post("/token",data=base,headers={"Idempotency-Key":key})
        ok("final_rotation",r.status_code==200)
        with s.Db.begin() as db:
            old=db.execute(select(s.Token).where(s.Token.hashed==s.hashed(p["refresh_token"]))).scalar_one()
            receipt=db.get(s.RefreshRecovery,old.id)
            ok("encrypted_receipt_at_rest",receipt is not None and receipt.nonce and "refresh_token" not in receipt.encrypted_result)
        return {"status":"AFFIRMED","checks":checks,"n":len(checks),"source":"V6 isolated GitHub candidate",
                "real_postgres":False,"chatgpt_client":False,"token_values_output":False}
if __name__=="__main__":
    print(json.dumps(asyncio.run(test()),indent=2))
