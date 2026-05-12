"""
Alert routing service.
Finds on-call clinicians for a given ward to receive sepsis alert notifications.
"""
from typing import List

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.patient import Doctor


async def get_on_call_doctors(ward: str, db: AsyncSession) -> List[Doctor]:
    """
    Return all active, currently on-call doctors who cover the given ward.

    A doctor covers a ward if their ward_assignment matches exactly OR is "All".
    Both conditions are checked to support:
      - Ward-specific intensivists  (ward_assignment = "MICU")
      - Duty consultants on call    (ward_assignment = "All")
    """
    result = await db.execute(
        select(Doctor).where(
            Doctor.is_active == True,
            Doctor.is_on_call == True,
            or_(
                Doctor.ward_assignment == ward,
                Doctor.ward_assignment == "All",
                Doctor.ward_assignment.is_(None),  # no ward restriction = receives all alerts
            ),
        )
    )
    return list(result.scalars().all())
