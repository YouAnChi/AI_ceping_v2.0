"""add_is_admin_to_user

Revision ID: 51772b4e794f
Revises: 9dfb1a784599
Create Date: 2025-06-04 13:48:00.673519

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '51772b4e794f'
down_revision = '9dfb1a784599'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.alter_column('is_admin',
               existing_type=sa.BOOLEAN(),
               nullable=True,
               existing_server_default=sa.text('0'))

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.alter_column('is_admin',
               existing_type=sa.BOOLEAN(),
               nullable=False,
               existing_server_default=sa.text('0'))

    # ### end Alembic commands ###
