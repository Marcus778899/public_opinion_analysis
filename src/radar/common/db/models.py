"""PG 表定義，schema 的唯一來源（見 docs/development-spec.md 2.4）。

表在 S1-01 加入；Alembic autogenerate 讀取 Base.metadata。
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
