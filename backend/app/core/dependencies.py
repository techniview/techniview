from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from ..models import CourseMembership, User
from .authorization import require_instructor
from .db import get_db
from .security import get_current_user

DbSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]
InstructorMembership = Annotated[CourseMembership, Depends(require_instructor)]
