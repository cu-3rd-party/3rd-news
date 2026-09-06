from lib.core.config import DATABASE_NAMING_CONVENTION
from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=DATABASE_NAMING_CONVENTION)
