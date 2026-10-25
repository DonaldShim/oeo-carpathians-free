"""Fixed trusted Postgres audit. Random temporary schema; never live token tables."""
import concurrent.futures,hashlib,secrets,threading,time,uuid
from sqlalchemy import create_engine,text,select,update
from sqlalchemy.orm import sessionmaker
from fastapi.responses import Response

def run(s):
 if s.dbengine is None or s.dbengine.dialect.name!='postgresql':return {'status':'OPEN','blocker':'REAL_POSTGRES_REQUIRED'}
 schema='canary_audit_'+uuid.uuid4().hex
 checks={};durations={};results={};started=time.monotonic()
 with s.dbengine.connect() as guard:
  if not guard.execute(text('SELECT pg_try_advisory_lock(145301,20261025)')).scalar():return {'status':'OPEN','blocker':'AUDIT_ALREADY_ACTIVE'}
  guard.execute(text('CREATE SCHEMA '+schema));guard.commit()
  engine=create_engine(s.dbengine.url,pool_pre_ping=True,pool_size=4,max_overflow=0,connect_args={'connect_timeout':5,'options':'-c search_path='+schema+' -c statement_timeout=5000 -c lock_timeout=3000 -c idle_in_transaction_session_timeout=5000'})
  Db=sessionmaker(bind=engine)
  def cas_rotate(db,raw):
   s.count(db,'refresh_grant_received')
   row=db.execute(select(s.Token).where(s.Token.hashed==s.hashed(raw),s.Token.kind=='refresh')).scalar_one_or_none()
   if row is None:return s.error(400,'invalid_grant')
   won=db.execute(update(s.Token).where(s.Token.id==row.id,s.Token.consumed_at.is_(None)).values(consumed_at=s.clock())).rowcount
   db.expire(row);fam=db.execute(select(s.Family).where(s.Family.id==row.family).with_for_update()).scalar_one()
   if fam.revoked or fam.client!=s.CLIENT or fam.resource!=s.ISSUER+'/mcp' or fam.policy_hash!=s.policy_binding() or 'offline_access' not in fam.scope.split() or row.expires<=s.clock():return s.error(400,'invalid_grant')
   if not won:
    if s.clock()-row.consumed_at>3:fam.revoked=True
    return s.error(400,'invalid_grant')
   result=s.mint(db,fam.id,fam.scope);s.count(db,'refresh_success');return result
  def fixture():
   with Db.begin() as db:
    fam=s.Family(user_hash=s.hashed(secrets.token_urlsafe(24)),client=s.CLIENT,resource=s.ISSUER+'/mcp',scope='c_lab_canary.read offline_access',policy_hash=s.policy_binding());db.add(fam);db.flush();fid=fam.id;p=s.mint(db,fid,fam.scope)
   return fid,p
  def rotate(fn,raw):
   with Db.begin() as db:return fn(db,raw)
  try:
   for label,fn in [('CONDITIONAL_UPDATE_CAS',cas_rotate),('ROW_LOCK_GRACE',s.rotate_refresh)]:
    begin=time.monotonic();s.Base.metadata.create_all(engine);done=[]
    fid,p=fixture();barrier=threading.Barrier(2)
    def worker():barrier.wait(timeout=3);return rotate(fn,p['refresh_token'])
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
     a=pool.submit(worker);b=pool.submit(worker);out=[a.result(timeout=12),b.result(timeout=12)]
    assert sum(isinstance(x,dict) for x in out)==1,'CONCURRENT_MULTIPLE_MINT'
    winner=next(x for x in out if isinstance(x,dict))
    with Db.begin() as db:
     assert not db.get(s.Family,fid).revoked,'CONCURRENT_SESSION_DESTROYED'
     assert db.execute(select(s.Token).where(s.Token.hashed==s.hashed(winner['access_token']))).scalar_one()
     total=db.execute(text('SELECT count(*) FROM canary_token')).scalar()
    done+=['concurrent_exactly_one_winner','concurrent_loser_no_tokens','winner_session_preserved']
    assert isinstance(rotate(fn,p['refresh_token']),Response)
    with Db.begin() as db:
     assert db.execute(text('SELECT count(*) FROM canary_token')).scalar()==total
     db.execute(update(s.Token).where(s.Token.hashed==s.hashed(p['refresh_token'])).values(consumed_at=s.clock()-4))
    assert isinstance(rotate(fn,p['refresh_token']),Response)
    with Db.begin() as db:assert db.get(s.Family,fid).revoked
    done+=['duplicate_no_remint','late_reuse_revokes_family']
    for bad in ['expiry','revoked','client','resource','policy','scope']:
     f,q=fixture()
     with Db.begin() as db:
      fam=db.get(s.Family,f)
      if bad=='expiry':db.execute(update(s.Token).where(s.Token.hashed==s.hashed(q['refresh_token'])).values(expires=1))
      elif bad=='revoked':fam.revoked=True
      elif bad=='client':fam.client='other-client'
      elif bad=='resource':fam.resource=s.ISSUER+'/wrong'
      elif bad=='policy':fam.policy_hash='0'*64
      else:fam.scope='c_lab_canary.read'
     assert isinstance(rotate(fn,q['refresh_token']),Response),bad
     done.append('deny_'+bad)
    f,q=fixture()
    try:
     with Db.begin() as db:assert isinstance(fn(db,q['refresh_token']),dict);raise RuntimeError('FIXED_TRANSACTION_FAULT')
    except RuntimeError:pass
    with Db.begin() as db:assert db.execute(select(s.Token).where(s.Token.hashed==s.hashed(q['refresh_token']))).scalar_one().consumed_at is None
    assert isinstance(rotate(fn,q['refresh_token']),dict)
    done.append('transaction_rollback_recovers_unused_token')
    with Db.begin() as db:
     stored=list(db.scalars(select(s.Token.hashed)));assert all(len(x)==64 and x not in (q['access_token'],q['refresh_token']) for x in stored)
    done.append('hash_only_storage')
    engine.dispose()
    with Db.begin() as db:assert db.get(s.Family,f) is not None
    done.append('connection_restart_persistence')
    checks[label]=done;durations[label]=round(time.monotonic()-begin,3)
    s.Base.metadata.drop_all(engine)
   results={'status':'AFFIRMED','database_backend':'postgresql','mechanisms':checks,'elapsed_s':durations,'selected':'ROW_LOCK_GRACE','selection_reason':'Same safety cases pass; selected mechanism is the exact endpoint helper, without a second claim/update path. Grace rejects duplicates without returning successor tokens.','live_google':'OPEN','real_chatgpt_refresh':'OPEN','plaintext_tokens_output':False}
  except Exception as e:results={'status':'REJECTED','blocker':type(e).__name__,'detail':str(e)[:120] if isinstance(e,AssertionError) else 'SANITIZED_DB_AUDIT_FAILURE','completed':checks}
  finally:
   engine.dispose();guard.execute(text('DROP SCHEMA '+schema+' CASCADE'));guard.commit();guard.execute(text('SELECT pg_advisory_unlock(145301,20261025)'));guard.commit()
  results['isolated_schema_removed']=True;results['live_token_tables_mutated']=False;results['total_elapsed_s']=round(time.monotonic()-started,3)
  return results
