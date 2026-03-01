from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from fantasy_engine.config import Settings
from fantasy_engine.db.models import Base


def get_engine(settings: Settings | None = None):
    if settings is None:
        settings = Settings()
    return create_engine(settings.db_sync_url, echo=False)


def get_session(settings: Settings | None = None):
    engine = get_engine(settings)
    return sessionmaker(bind=engine)


def init_db(settings: Settings | None = None):
    engine = get_engine(settings)
    Base.metadata.create_all(engine)
    return engine
