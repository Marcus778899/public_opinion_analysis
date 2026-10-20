"""add posts comment_count

Revision ID: e13f7623dcb5
Revises: 8a9b4796098b
Create Date: 2026-10-17 15:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e13f7623dcb5"
down_revision: str | Sequence[str] | None = "8a9b4796098b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# NOTE: 補值只更新推文數不為 0 的文章；每列產生一筆 posts CDC 事件（開發規格 7.24）
def upgrade() -> None:
    op.add_column(
        "posts",
        sa.Column("comment_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.execute(
        "UPDATE posts SET comment_count = c.n "
        "FROM (SELECT post_id, count(*) AS n FROM comments GROUP BY post_id) AS c "
        "WHERE posts.post_id = c.post_id"
    )


def downgrade() -> None:
    op.drop_column("posts", "comment_count")
