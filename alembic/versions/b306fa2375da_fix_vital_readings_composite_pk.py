"""fix_vital_readings_composite_pk

Revision ID: b306fa2375da
Revises: 7ba73f65e710
Create Date: 2026-03-23 01:54:24.635302

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b306fa2375da'
down_revision: Union[str, None] = '7ba73f65e710'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # TimescaleDB requires the partition column to be part of the primary key.
    # Alembic autogenerate cannot detect PK changes, so we do this manually:
    # drop the table and recreate with composite PK (id, recorded_at).
    op.drop_table('vital_readings')
    op.create_table(
        'vital_readings',
        sa.Column('id', sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('patient_id', sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('recorded_at', sa.DateTime(), nullable=False),
        sa.Column('heart_rate', sa.Float(), nullable=True),
        sa.Column('systolic_bp', sa.Float(), nullable=True),
        sa.Column('diastolic_bp', sa.Float(), nullable=True),
        sa.Column('spo2', sa.Float(), nullable=True),
        sa.Column('temperature_c', sa.Float(), nullable=True),
        sa.Column('respiratory_rate', sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(['patient_id'], ['patients.id']),
        sa.PrimaryKeyConstraint('id', 'recorded_at'),  # composite PK for TimescaleDB
    )


def downgrade() -> None:
    op.drop_table('vital_readings')
    op.create_table(
        'vital_readings',
        sa.Column('id', sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('patient_id', sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('recorded_at', sa.DateTime(), nullable=False),
        sa.Column('heart_rate', sa.Float(), nullable=True),
        sa.Column('systolic_bp', sa.Float(), nullable=True),
        sa.Column('diastolic_bp', sa.Float(), nullable=True),
        sa.Column('spo2', sa.Float(), nullable=True),
        sa.Column('temperature_c', sa.Float(), nullable=True),
        sa.Column('respiratory_rate', sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(['patient_id'], ['patients.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    pass
