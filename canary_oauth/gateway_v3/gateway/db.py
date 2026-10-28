from __future__ import annotations
from sqlalchemy import Boolean, Column, Integer, String, Text, create_engine, Index
from sqlalchemy.orm import DeclarativeBase, Session

class Base(DeclarativeBase): pass

class Flow(Base):
    __tablename__ = 'flows'
    state_hash=Column(String(64),primary_key=True)
    payload_cipher=Column(Text,nullable=False)
    expires=Column(Integer,nullable=False)
    consumed=Column(Boolean,nullable=False,default=False)

class Grant(Base):
    __tablename__ = 'grants'
    id=Column(String(64),primary_key=True)
    google_sub=Column(String(255),nullable=False)
    email_cipher=Column(Text,nullable=False)
    google_refresh_cipher=Column(Text,nullable=False)
    google_access_cipher=Column(Text,nullable=True)
    google_access_expires=Column(Integer,nullable=False,default=0)
    resource=Column(Text,nullable=False)
    client_id=Column(Text,nullable=False)
    scopes=Column(String(255),nullable=False)
    revoked=Column(Boolean,nullable=False,default=False)

class AuthCode(Base):
    __tablename__ = 'auth_codes'
    code_hash=Column(String(64),primary_key=True)
    grant_id=Column(String(64),nullable=False,index=True)
    redirect_uri=Column(Text,nullable=False)
    challenge=Column(String(100),nullable=False)
    expires=Column(Integer,nullable=False)
    consumed=Column(Boolean,nullable=False,default=False)

class AccessToken(Base):
    __tablename__ = 'access_tokens'
    token_hash=Column(String(64),primary_key=True)
    grant_id=Column(String(64),nullable=False,index=True)
    expires=Column(Integer,nullable=False)
    revoked=Column(Boolean,nullable=False,default=False)

class RefreshToken(Base):
    __tablename__ = 'refresh_tokens'
    token_hash=Column(String(64),primary_key=True)
    grant_id=Column(String(64),nullable=False,index=True)
    family=Column(String(64),nullable=False,index=True)
    expires=Column(Integer,nullable=False)
    consumed=Column(Boolean,nullable=False,default=False)

class Audit(Base):
    __tablename__='audit_events'
    id=Column(Integer,primary_key=True,autoincrement=True)
    epoch=Column(Integer,nullable=False)
    kind=Column(String(80),nullable=False)
    grant_id=Column(String(64),nullable=True)
    note=Column(String(100),nullable=False,default='')

def build_engine(url:str):
    kwargs={'pool_pre_ping':True}
    if url.startswith('sqlite:'):
        kwargs['connect_args']={'check_same_thread':False}
    return create_engine(url,**kwargs)

def record(session:Session,epoch:int,kind:str,grant_id:str|None=None,note:str=''):
    session.add(Audit(epoch=epoch,kind=kind,grant_id=grant_id,note=note[:100]))
