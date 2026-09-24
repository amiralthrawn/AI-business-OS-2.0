import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, Float, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.entities.base import Base, IdMixin, TimestampMixin, ValueBasis


class Employee(Base, IdMixin, TimestampMixin):
    """A person working for the company (V2.1, brain/business_object_model.md).

    Deliberately small -- NOT an HR system: enough to connect a person to what
    they cost, what they work on and what that produces
    (EMPLOYEE -> COST -> TASKS -> CONTRIBUTION). Distinct from UserProfile (a
    person *using* the OS): `user_id` links the two when they are the same
    person, which is how an employee's owned deals are found.

    `data_basis` says where the HR facts come from: DECLARED when entered by
    the company, SIMULATED for demonstration data -- never shown as real."""

    __tablename__ = "employees"

    company_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("companies.id"), nullable=False, index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"), nullable=True, index=True)
    manager_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("employees.id"), nullable=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255))
    job_title: Mapped[str | None] = mapped_column(String(120))
    department: Mapped[str | None] = mapped_column(String(120))
    # "active" | "on_leave" | "left"
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    hired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    weekly_hours: Mapped[float | None] = mapped_column(Float)
    leave_days_remaining: Mapped[float | None] = mapped_column(Float)
    skills: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    responsibilities: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    data_basis: Mapped[ValueBasis] = mapped_column(Enum(ValueBasis), nullable=False, default=ValueBasis.DECLARED)
    notes: Mapped[str | None] = mapped_column(Text)

    cost_items: Mapped[list["EmployeeCostItem"]] = relationship(back_populates="employee", cascade="all, delete-orphan")


class EmployeeCostItem(Base, IdMixin, TimestampMixin):
    """One component of what an employee costs the company per year (salary,
    employer charges, software licences, equipment, benefits...), as a range
    with its basis -- the same honesty rule as a commercial CostItem."""

    __tablename__ = "employee_cost_items"

    employee_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True)
    # "salary" | "employer_charges" | "software" | "equipment" | "benefits" | "other"
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    label: Mapped[str | None] = mapped_column(String(255))
    annual_min: Mapped[float] = mapped_column(Float, nullable=False)
    annual_max: Mapped[float] = mapped_column(Float, nullable=False)
    basis: Mapped[ValueBasis] = mapped_column(Enum(ValueBasis), nullable=False)
    confidence: Mapped[str] = mapped_column(String(10), nullable=False, default="medium")
    source: Mapped[str | None] = mapped_column(String(120))

    employee: Mapped[Employee] = relationship(back_populates="cost_items")


class SkillNeed(Base, IdMixin, TimestampMixin):
    """A capability the company says it needs (DECLARED), e.g. "data /
    automation". Compared with the team's skills and workload to detect gaps."""

    __tablename__ = "skill_needs"

    company_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("companies.id"), nullable=False, index=True)
    skill: Mapped[str] = mapped_column(String(120), nullable=False)
    # Words that count as covering this need in a skill list / candidate email.
    keywords: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    level: Mapped[str] = mapped_column(String(20), nullable=False, default="confirmé")
    reason: Mapped[str | None] = mapped_column(Text)
    expected_impact: Mapped[str | None] = mapped_column(Text)
    priority: Mapped[str] = mapped_column(String(10), nullable=False, default="medium")
    basis: Mapped[ValueBasis] = mapped_column(Enum(ValueBasis), nullable=False, default=ValueBasis.DECLARED)


class Candidate(Base, IdMixin, TimestampMixin):
    """A job applicant, usually extracted from an inbound email. Not an ATS:
    a candidate record, its source message, what it says and how it matches
    the company's declared needs."""

    __tablename__ = "candidates"

    company_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("companies.id"), nullable=False, index=True)
    communication_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("communications.id"), nullable=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255))
    applied_for: Mapped[str | None] = mapped_column(String(160))
    skills: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    years_experience: Mapped[float | None] = mapped_column(Float)
    # "new" | "shortlisted" | "interview_proposed" | "rejected" | "hired"
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="new")
    # DECLARED (what the applicant wrote) or SIMULATED (demo data).
    basis: Mapped[ValueBasis] = mapped_column(Enum(ValueBasis), nullable=False, default=ValueBasis.DECLARED)
    # "rules" | "rules+llm" | "manual" -- how the fields were extracted.
    extracted_by: Mapped[str] = mapped_column(String(20), nullable=False, default="manual")
