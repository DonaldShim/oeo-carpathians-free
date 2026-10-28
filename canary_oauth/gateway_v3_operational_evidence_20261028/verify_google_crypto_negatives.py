"""Real JWT crypto with isolated cert fixtures; NOT live Google OAuth evidence."""
import datetime,hashlib,json,pathlib,sys,time
import httpx
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from google.auth import crypt,jwt
from fastapi import HTTPException
R=pathlib.Path(__file__).parent;sys.path.insert(0,str(R/'source'))
from gateway.config import Settings
import gateway.google as implementation
key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
private=key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption())
public=key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo).decode()
signer=crypt.RSASigner.from_string(private,key_id='isolated-fixture')
settings=Settings(public_base_url='http://127.0.0.1:8080',google_client_id='fixture.apps.googleusercontent.com',
 google_client_secret='SYNTHETIC_NOT_A_GOOGLE_CLIENT_SECRET',allowed_google_email='fixture@example.invalid',
 gateway_encryption_key=Fernet.generate_key().decode(),database_url='sqlite:////tmp/unused.db',
 client_id='https://chatgpt.com/oauth/client.json',allowed_redirect_uris=('https://chatgpt.com/connector_platform_oauth_redirect',),
 upstream_mcp_url='http://127.0.0.1:9090/mcp',allow_sqlite_dev=True)
def certificate(method,url,**kwargs):
 assert method=='GET' and url=='https://www.googleapis.com/oauth2/v1/certs'
 return httpx.Response(200,json={'isolated-fixture':public})
implementation.request=certificate
provider=implementation.GoogleProvider(settings);now=int(time.time())
base={'iss':'https://accounts.google.com','aud':settings.google_client_id,'sub':'fixture-owner',
 'email':settings.allowed_google_email,'email_verified':True,'nonce':'fixture-nonce','iat':now-100,'exp':now+100}
def encode(claims):return jwt.encode(signer,claims).decode()
assert provider.verify(encode(base),'fixture-nonce')['sub']=='fixture-owner'
results=[]
for name,change in [('foreign_audience',{'aud':'foreign.apps.googleusercontent.com'}),
 ('expired',{'exp':now-10}),('foreign_issuer',{'iss':'https://foreign.invalid'}),
 ('foreign_user',{'email':'foreign@example.invalid'}),('unverified_email',{'email_verified':False}),
 ('foreign_nonce',{'nonce':'foreign'}),('missing_subject',{'sub':''})]:
 try:provider.verify(encode({**base,**change}),'fixture-nonce');raise AssertionError('unsafe acceptance')
 except HTTPException as e:assert e.status_code==403;results.append({'name':name,'status':'REJECTED_403'})
parts=encode(base).split('.');parts[2]=('A' if parts[2][0]!='A' else 'B')+parts[2][1:]
try:provider.verify('.'.join(parts),'fixture-nonce');raise AssertionError('signature accepted')
except HTTPException as e:assert e.status_code==403;results.append({'name':'tampered_signature','status':'REJECTED_403'})
out={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'status':'AFFIRMED_ISOLATED_CRYPTO_NEGATIVES',
 'google_managed_signature_proof':False,'real_google_token_issued':False,'fixture_private_keys_persisted':False,
 'valid_crypto_fixture_accepted':True,'negative_cases':results,
 'source_google_py_sha256':hashlib.sha256((R/'source'/'gateway'/'google.py').read_bytes()).hexdigest()}
p=R/'evidence'/'google-crypto-adversarial.json';p.write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({'certificate':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'negative_cases':len(results),'status':out['status']}))
