"""Atomic OAuth state backed by Firestore; no cached / local mutable authority.

Requires google-cloud-firestore; store client acquired through Cloud Run metadata ADC.
The only bearer token content stored in Firestore is encrypted (Fernet) or SHA256-hashed.
"""
from __future__ import annotations
import secrets
import time
from typing import Callable, Any
from .crypto import digest, random_token


class GrantFailure(ValueError):
    pass


class FirestoreOAuthStore:
    def __init__(self, project: str, prefix: str = 'clab_gateway_v2', client=None):
        if client is None:
            from google.cloud import firestore
            client = firestore.Client(project=project, database='(default)')
        self.client = client
        self.prefix = prefix

    def _doc(self, kind, key):
        if kind not in ('flows','grants','codes','access','refresh','audit','rate','meta'):
            raise ValueError('Unexpected storage collection')
        if not key or '/' in key or len(key) > 150:
            raise ValueError('Invalid storage key')
        return self.client.collection(self.prefix+'_'+kind).document(key)

    def _tx(self, callback: Callable):
        from google.cloud import firestore
        @firestore.transactional
        def run(transaction):
            return callback(transaction)
        return run(self.client.transaction(max_attempts=3))

    @staticmethod
    def _audit(tx, doc, t, kind, grant_id=''):
        tx.create(doc, {'epoch':t,'kind':kind,'grant_id':grant_id})

    def health(self):
        # Read metadata only; no implicit schema migration or secrets.
        self._doc('meta','ready').get()
        return True

    def admit_rate(self, ip_hash: str, t: int, limit: int = 12, window: int = 600):
        bucket=t//window
        ref=self._doc('rate', digest(ip_hash+':'+str(bucket)))
        def fn(tx):
            snap=ref.get(transaction=tx)
            count=int(snap.to_dict().get('n',0)) if snap.exists else 0
            if count>=limit: raise GrantFailure('rate_limited')
            if snap.exists: tx.update(ref, {'n':count+1})
            else: tx.create(ref, {'n':1,'expires':(bucket+1)*window})
        self._tx(fn)

    def create_flow(self, state_hash: str, payload_cipher: str, expires: int, t: int):
        ref=self._doc('flows',state_hash)
        def fn(tx):
            tx.create(ref, {'payload_cipher':payload_cipher,'expires':expires,'consumed':False})
            self._audit(tx,self._doc('audit',random_token()),t,'google_authorize_start')
        self._tx(fn)

    def take_flow(self, state_hash: str, t: int) -> str:
        ref=self._doc('flows',state_hash)
        def fn(tx):
            s=ref.get(transaction=tx)
            if not s.exists: raise GrantFailure('state_not_found')
            data=s.to_dict()
            if data.get('consumed') or data.get('expires',0)<=t:
                raise GrantFailure('state_consumed_or_expired')
            tx.update(ref, {'consumed':True})
            return data['payload_cipher']
        return self._tx(fn)

    def issue_code(self, grant_id: str, google_subject: str, email_cipher: str,
                   refresh_cipher: str, access_cipher: str, access_expires: int,
                   resource: str, client_id: str, code_hash: str,
                   code_challenge: str, redirect_uri: str, code_expires: int, t: int):
        grant=self._doc('grants',grant_id)
        code=self._doc('codes',code_hash)
        data={'google_sub':google_subject,'email_cipher':email_cipher,
              'google_refresh_cipher':refresh_cipher,'google_access_cipher':access_cipher,
              'google_access_expires':access_expires,'resource':resource,'client_id':client_id,
              'scopes':'clab.read','revoked':False,'refresh_lease_owner':None,
              'refresh_lease_until':0,'refresh_fence':0,'refresh_status':'IDLE',
              'created_epoch':t,'expires':t+30*86400}
        def fn(tx):
            tx.create(grant,data)
            tx.create(code, {'grant_id':grant_id,'challenge':code_challenge,
                'redirect_uri':redirect_uri,'expires':code_expires,'consumed':False})
            self._audit(tx,self._doc('audit',random_token()),t,'google_offline_credential_issued',grant_id)
        self._tx(fn)

    def redeem_code(self, code_hash: str, verifier_challenge: str, redirect_uri: str,
                    client_id: str, resource: str, t: int, access_ttl: int, refresh_ttl: int):
        code=self._doc('codes',code_hash)
        def fn(tx):
            snap=code.get(transaction=tx)
            if not snap.exists: raise GrantFailure('invalid_grant')
            data=snap.to_dict()
            if (data['consumed'] or data['expires']<=t or data['challenge']!=verifier_challenge
                    or data['redirect_uri']!=redirect_uri):
                raise GrantFailure('invalid_grant')
            grantref=self._doc('grants',data['grant_id'])
            gs=grantref.get(transaction=tx)
            if not gs.exists: raise GrantFailure('invalid_grant')
            gd=gs.to_dict()
            if gd['revoked'] or gd.get('expires',t+1)<=t or gd['resource']!=resource or gd['client_id']!=client_id:
                raise GrantFailure('invalid_grant')
            access=random_token(); refresh=random_token(); fam=random_token()
            tx.update(code,{'consumed':True})
            tx.create(self._doc('access',digest(access)),
                     {'grant_id':data['grant_id'],'expires':t+access_ttl,'revoked':False})
            tx.create(self._doc('refresh',digest(refresh)),
                     {'grant_id':data['grant_id'],'family':fam,'expires':t+refresh_ttl,'consumed':False})
            self._audit(tx,self._doc('audit',random_token()),t,'gateway_access_and_refresh_issued',data['grant_id'])
            return access,refresh
        return self._tx(fn)

    def rotate_refresh(self, old_hash: str, client_id: str, resource: str,
                       t: int, access_ttl: int, refresh_ttl: int):
        oldref=self._doc('refresh',old_hash)
        def fn(tx):
            old=oldref.get(transaction=tx)
            if not old.exists: raise GrantFailure('invalid_grant')
            d=old.to_dict()
            grantref=self._doc('grants',d['grant_id'])
            gs=grantref.get(transaction=tx)
            if not gs.exists: raise GrantFailure('invalid_grant')
            gd=gs.to_dict()
            if gd['revoked'] or gd.get('expires',t+1)<=t or gd['client_id']!=client_id or gd['resource']!=resource:
                raise GrantFailure('invalid_grant')
            if d['consumed']:
                # The revocation COMMITs before the caller receives an invalid_grant.
                tx.update(grantref,{'revoked':True})
                self._audit(tx,self._doc('audit',random_token()),t,'refresh_replay_grant_revoked',d['grant_id'])
                return None
            if d['expires']<=t: raise GrantFailure('invalid_grant')
            access=random_token(); refresh=random_token()
            tx.update(oldref,{'consumed':True})
            tx.create(self._doc('access',digest(access)),
                      {'grant_id':d['grant_id'],'expires':t+access_ttl,'revoked':False})
            tx.create(self._doc('refresh',digest(refresh)),
                      {'grant_id':d['grant_id'],'family':d['family'],
                       'expires':t+refresh_ttl,'consumed':False})
            self._audit(tx,self._doc('audit',random_token()),t,'gateway_refresh_success',d['grant_id'])
            return access,refresh
        result=self._tx(fn)
        if result is None: raise GrantFailure('invalid_grant_refresh_replay')
        return result

    def get_grant_from_access(self, token_hash: str, resource: str, t: int) -> str:
        def check(tx):
            tok=self._doc('access',token_hash).get(transaction=tx)
            if not tok.exists: raise GrantFailure('invalid_token')
            td=tok.to_dict()
            if td['revoked'] or td['expires']<=t: raise GrantFailure('invalid_token')
            grant=self._doc('grants',td['grant_id']).get(transaction=tx)
            if not grant.exists: raise GrantFailure('invalid_token')
            gd=grant.to_dict()
            if gd['revoked'] or gd.get('expires',t+1)<=t or gd['resource']!=resource or gd['scopes']!='clab.read':
                raise GrantFailure('invalid_token')
            return td['grant_id']
        return self._tx(check)

    def revoke(self, token_hash: str, client_id: str):
        refresh=self._doc('refresh',token_hash).get()
        access=self._doc('access',token_hash).get()
        data=refresh.to_dict() if refresh.exists else (access.to_dict() if access.exists else None)
        if not data: return
        grantref=self._doc('grants',data['grant_id'])
        def fn(tx):
            snap=grantref.get(transaction=tx)
            if snap.exists and snap.to_dict()['client_id']==client_id:
                tx.update(grantref,{'revoked':True})
                self._audit(tx,self._doc('audit',random_token()),int(time.time()),
                            'gateway_grant_revoked',data['grant_id'])
        self._tx(fn)

    def google_access(self, grant_id: str, cipher, google, t: int) -> str:
        """Short lease makes refresh one-sided, no network inside Firestore transaction."""
        ref=self._doc('grants',grant_id)
        lease=random_token()
        def claim(tx):
            snap=ref.get(transaction=tx)
            if not snap.exists or snap.to_dict().get('revoked'):raise GrantFailure('revoked')
            gd=snap.to_dict()
            if gd.get('refresh_status')=='UNKNOWN':raise GrantFailure('google_refresh_outcome_unknown_reconsent_required')
            if gd.get('refresh_status')=='INFLIGHT' and gd.get('refresh_lease_until',0)<=t:
                tx.update(ref,{'refresh_status':'UNKNOWN','refresh_lease_owner':None})
                self._audit(tx,self._doc('audit',random_token()),t,'google_refresh_abandoned',grant_id)
                return ('unknown',None)
            if gd.get('expires',t+1)<=t:raise GrantFailure('expired_grant')
            if gd.get('google_access_cipher') and gd['google_access_expires']>t+30:
                return ('cached',gd['google_access_cipher'])
            if gd.get('refresh_lease_until',0)>t:
                raise GrantFailure('refresh_in_progress')
            fence=int(gd.get('refresh_fence',0))+1
            tx.update(ref,{'refresh_lease_owner':lease,'refresh_lease_until':t+60,
                           'refresh_fence':fence,'refresh_status':'INFLIGHT'})
            self._audit(tx,self._doc('audit',random_token()),t,'google_refresh_started',grant_id)
            return ('refresh',(gd['google_refresh_cipher'],fence,t+60))
        mode,secret=self._tx(claim)
        if mode=='unknown':raise GrantFailure('google_refresh_outcome_unknown_reconsent_required')
        if mode=='cached':return cipher.decrypt(secret)
        secret,fence,deadline=secret
        try:
            result=google.refresh(cipher.decrypt(secret))
            lifetime=int(result.get('expires_in',0))
            if not result.get('access_token') or not 0<lifetime<=86400:
                raise GrantFailure('invalid_google_refresh_response')
        except Exception:
            def release(tx):
                snap=ref.get(transaction=tx)
                if snap.exists and snap.to_dict().get('refresh_lease_owner')==lease:
                    tx.update(ref,{'refresh_lease_owner':None,'refresh_lease_until':0,
                                   'refresh_status':'UNKNOWN'})
                    self._audit(tx,self._doc('audit',random_token()),int(time.time()),'google_refresh_unknown',grant_id)
            self._tx(release)
            raise
        def finish(tx):
            snap=ref.get(transaction=tx)
            if not snap.exists or snap.to_dict().get('revoked'):
                raise GrantFailure('revoked')
            if (snap.to_dict().get('refresh_lease_owner')!=lease or
                snap.to_dict().get('refresh_fence')!=fence or int(time.time())>=deadline):
                raise GrantFailure('refresh_lease_lost')
            fields={'google_access_cipher':cipher.encrypt(result['access_token']),
                    'google_access_expires':int(time.time())+lifetime,
                    'refresh_lease_owner':None,'refresh_lease_until':0,'refresh_status':'IDLE'}
            if result.get('refresh_token'):
                fields['google_refresh_cipher']=cipher.encrypt(result['refresh_token'])
            tx.update(ref,fields)
            self._audit(tx,self._doc('audit',random_token()),int(time.time()),'google_refresh_success',grant_id)
        self._tx(finish)
        return result['access_token']
