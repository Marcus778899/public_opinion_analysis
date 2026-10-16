"""comments replica identity full

Revision ID: fe540c8cd7b7
Revises: a3c1f0d2b7e4
Create Date: 2026-10-10 10:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "fe540c8cd7b7"
down_revision: str | Sequence[str] | None = "a3c1f0d2b7e4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# NOTE: 推文同步會刪除列（開發規格 7.15）；預設的刪除事件只帶主鍵，
# ClickHouse 解析非 Nullable 欄位會失敗
def upgrade() -> None:
    op.execute("ALTER TABLE comments REPLICA IDENTITY FULL")


def downgrade() -> None:
    op.execute("ALTER TABLE comments REPLICA IDENTITY DEFAULT")
