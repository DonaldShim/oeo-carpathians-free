"""Isolated real PostgreSQL V6 recovery audit. Only random disposable schema.
Runs from Render private network, no user token/session material consumed.
"""
import json, time, uuid, secrets, concurrent.futures, threading
from sqlalchemy import create_engine, select, text, update
from sqlalchemy.orm import sessionmaker
from fastapi import Response

LOCK_A,LOCK_B=145306,20261025

def run(s):
    start=time.monotonic()
    checks=[]
    info={"status":"OPEN","backend":"unknown","checks":checks,"live_token_tables_mutated":False,
          "real_chatgpt_refresh":"OPEN","secrets_output":False}
    if s.dbengine is None or s.dbengine.dialect.name!="postgresql":
        return {**info,"blocker":"REAL_POSTGRES_REQUIRED"}
    if s.recovery_key() is None:return {**info,"blocker":"RECOVERY_KEY_REQUIRED"}
    guard=s.dbengine.connect()
    isolated=None
    name="canary_v6_audit_"+uuid.uuid4().hex
    acquired=False
    try:
        acquired=bool(guard.execute(text("SELECT pg_try_advisory_lock(:a,:b)"),{"a":LOCK_A,"b":LOCK_B}).scalar())
        guard.commit()
        if not acquired:return {**info,"blocker":"AUDIT_ALREADY_ACTIVE"}
        guard.execute(text("CREATE SCHEMA "+name))
        guard.commit()
        def new_engine():
            return create_engine(s.dbengine.url,pool_pre_ping=True,pool_size=4,max_overflow=1,
                    connect_args={"connect_timeout":5,"options":"-c search_path="+name+" -c statement_timeout=7000 -c lock_timeout=5000 -c idle_in_transaction_session_timeout=5000"})
        isolated=new_engine()
        s.Base.metadata.create_all(isolated)
        Db=sessionmaker(bind=isolated,expire_on_commit=False)
        def ck(name,condition):
            assert condition,name
            checks.append(name)
        def seed():
            with Db.begin() as db:
                f=s.Family(user_hash=s.hashed(secrets.token_urlsafe(32)),client=s.PROBE_CLIENT,
                    resource=s.ISSUER+"/mcp",scope="c_lab_canary.read offline_access",
                    policy_hash=s.policy_binding(s.PROBE_CLIENT))
                db.add(f);db.flush()
                return s.mint(db,f.id,f.scope)
        def refresh(raw,attempt):
            with Db.begin() as db:
                return s.rotate_refresh(db,raw,s.PROBE_CLIENT,attempt)
        def is_error(x):
            return isinstance(x,Response) and x.status_code in (400,401,503)
        p=seed()
        key=secrets.token_urlsafe(48)
        barrier=threading.Barrier(2)
        def race():
            barrier.wait(timeout=5)
            return refresh(p["refresh_token"],key)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
            fs=[ex.submit(race) for _ in range(2)]
            two=[f.result(timeout=15) for f in fs]
        ck("same_key_concurrent_both_accepted",all(isinstance(v,dict) for v in two))
        ck("same_key_returns_identical_successor",two[0]==two[1])
        with Db.begin() as db:
            e={v.name:v.total for v in db.scalars(select(s.Event))}
            ck("one_real_refresh_success",e.get("refresh_success")==1)
            ck("one_new_refresh_token",db.execute(select(s.Token).where(s.Token.hashed==s.hashed(two[0]["refresh_token"]))).scalar_one_or_none() is not None)
            entry=db.execute(select(s.RefreshRecovery)).scalar_one()
            ck("opaque_ciphertext_saved",bool(entry.encrypted_result) and "refresh_token" not in entry.encrypted_result and len(entry.nonce)==24)
        ck("wrong_attempt_rejected",is_error(refresh(p["refresh_token"],secrets.token_urlsafe(48))))
        ck("valid_successor_remains_usable", isinstance(refresh(two[0]["refresh_token"],secrets.token_urlsafe(48)),dict))
        original=seed();k2=secrets.token_urlsafe(48)
        first=refresh(original["refresh_token"],k2)
        ck("lost_reply_baseline_rotation",isinstance(first,dict))
        # Readback over physically new DB pool/connection, without mutating runtime global state.
        isolated.dispose()
        isolated=new_engine()
        Db=sessionmaker(bind=isolated,expire_on_commit=False)
        restored=refresh(original["refresh_token"],k2)
        ck("new_engine_restores_identical_tokens",isinstance(restored,dict) and restored==first)
        ck("wrong_attempt_after_reconnect_denied",is_error(refresh(original["refresh_token"],secrets.token_urlsafe(48))))
        # Explicitly expire only the isolated receipt; no clock monkeypatch.
        with Db.begin() as db:
            item=db.execute(select(s.Token).where(s.Token.hashed==s.hashed(original["refresh_token"]))).scalar_one()
            receipt=db.get(s.RefreshRecovery,item.id)
            receipt.expires=s.clock()-1
        ck("receipt_expiry_rejects_recovery",is_error(refresh(original["refresh_token"],k2)))
        q=seed();k3=secrets.token_urlsafe(48)
        try:
            with Db.begin() as db:
                got=s.rotate_refresh(db,q["refresh_token"],s.PROBE_CLIENT,k3)
                assert isinstance(got,dict)
                raise RuntimeError("INJECTED_TRANSACTION_FAILURE")
        except RuntimeError as e:
            assert str(e)=="INJECTED_TRANSACTION_FAILURE"
        with Db.begin() as db:
            item=db.execute(select(s.Token).where(s.Token.hashed==s.hashed(q["refresh_token"]))).scalar_one()
            ck("rollback_leaves_input_token_available",item.consumed_at is None)
            ck("rollback_leaves_no_receipt",db.get(s.RefreshRecovery,item.id) is None)
        ck("refresh_after_rollback_succeeds",isinstance(refresh(q["refresh_token"],k3),dict))
        z=seed();keyz=secrets.token_urlsafe(48)
        firstz=refresh(z["refresh_token"],keyz)
        ck("tamper_fixture_created",isinstance(firstz,dict))
        with Db.begin() as db:
            item=db.execute(select(s.Token).where(s.Token.hashed==s.hashed(z["refresh_token"]))).scalar_one()
            db.get(s.RefreshRecovery,item.id).encrypted_result="AAAA"
        bad=refresh(z["refresh_token"],keyz)
        ck("tampered_receipt_fails_closed",is_error(bad))
        with Db.begin() as db:
            vals=list(db.scalars(select(s.Token.hashed)))
            ck("only_digest_tokens_stored",bool(vals) and all(len(a)==64 for a in vals))
        info.update({"status":"AFFIRMED","backend":"postgresql","checks":checks,"check_count":len(checks),
                     "concurrency":"2 racers, same attempt key","engine_reconstruction":True,
                     "token_values_output":False,"live_google_login":"not used"})
    except Exception as e:
        info.update({"status":"REJECTED","failure_class":type(e).__name__,
                     "failed_check":str(e)[:80] if isinstance(e,AssertionError) else "SANITIZED_V6_PG_AUDIT_FAILURE"})
    finally:
        if isolated is not None:isolated.dispose()
        try:
            if acquired:
                guard.execute(text("DROP SCHEMA IF EXISTS "+name+" CASCADE"))
                guard.commit()
                info["isolated_schema_removed"]=True
        except Exception:
            guard.rollback()
            info["isolated_schema_removed"]=False
            if info["status"]=="AFFIRMED":info["status"]="REJECTED"
        try:
            if acquired:
                guard.execute(text("SELECT pg_advisory_unlock(:a,:b)"),{"a":LOCK_A,"b":LOCK_B})
                guard.commit()
        except Exception:pass
        guard.close()
        info["elapsed_seconds"]=round(time.monotonic()-start,3)
    return info
