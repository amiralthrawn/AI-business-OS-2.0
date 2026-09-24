import enum
import uuid

from sqlalchemy import JSON, Boolean, Enum, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.entities.base import Base, IdMixin, TimestampMixin


class Role(str, enum.Enum):
    """The job a user holds (V2). Drives navigation, what can be edited and
    which actions can be triggered -- see app.access.policy for the matrix."""

    DIRECTOR = "director"
    SALES = "sales"
    PROCUREMENT = "procurement"
    OPERATIONS = "operations"
    HR = "hr"
    EMPLOYEE = "employee"


class UserProfile(Base, IdMixin, TimestampMixin):
    """A person using the OS and their role. Deliberately NOT an account:
    there is no password and no session in this MVP, so a profile is a
    declared identity, not an authenticated one (brain/permissions.md)."""

    __tablename__ = "users"

    company_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("companies.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(Enum(Role), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # V2.1 custom access: permissions a director added to / removed from the
    # role's defaults for this profile (app.access.policy.effective_permissions).
    access_grants: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    access_revokes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
