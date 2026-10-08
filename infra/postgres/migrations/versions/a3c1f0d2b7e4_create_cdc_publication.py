"""create cdc publication for posts and comments

Revision ID: a3c1f0d2b7e4
Revises: 4856307c62e5
Create Date: 2026-10-07 15:30:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a3c1f0d2b7e4"
down_revision: str | Sequence[str] | None = "4856307c62e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# NOTE: 名稱需與 infra/debezium/radar-cdc.json 的 publication.name 一致（設計文件 6.1）
PUBLICATION = "radar_cdc"


def upgrade() -> None:
    op.execute(f"CREATE PUBLICATION {PUBLICATION} FOR TABLE posts, comments")


def downgrade() -> None:
    op.execute(f"DROP PUBLICATION IF EXISTS {PUBLICATION}")
