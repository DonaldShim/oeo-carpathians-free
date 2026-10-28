from __future__ import annotations
import base64, hashlib, secrets
from cryptography.fernet import Fernet

def random_token():
    return secrets.token_urlsafe(48)

def digest(value:str)->str:
    return hashlib.sha256(value.encode('utf-8')).hexdigest()

def challenge_from_verifier(verifier:str)->str:
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode('ascii')).digest()).decode('ascii').rstrip('=')

def valid_verifier(verifier:str)->bool:
    return 43<=len(verifier)<=128 and all(x.isascii() and (x.isalnum() or x in '-._~') for x in verifier)

class Cipher:
    def __init__(self,key:str):
        self.fernet=Fernet(key.encode('ascii'))
    def encrypt(self,value:str)->str:
        return self.fernet.encrypt(value.encode('utf-8')).decode('ascii')
    def decrypt(self,value:str)->str:
        return self.fernet.decrypt(value.encode('ascii')).decode('utf-8')
