"""Explicit initial schema, run once under operator control (not at Cloud Run startup)."""
from .config import Settings
from .db import Base, build_engine
if __name__=='__main__':
    settings=Settings.from_env()
    engine=build_engine(settings.database_url)
    Base.metadata.create_all(engine)
    print('C_LAB_OAUTH_GATEWAY_SCHEMA_READY')
