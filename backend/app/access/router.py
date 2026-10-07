import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.core.i18n import tx
from app.access.deps import CurrentUser, get_current_user
from app.access.policy import ACCESS_CATALOG, ALL_PERMISSIONS, role_label, WRITE_SETTINGS, effective_permissions, role_defaults
from app.core.entities import Company, Role, UserProfile
from app.core.tenancy import current_company
from app.database import get_db

router = APIRouter(prefix="/users", tags=["users"])


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    email: str | None
    role: Role
    is_active: bool
    access_grants: list[str]
    access_revokes: list[str]
    permissions: list[str] = []

    @classmethod
    def of(cls, profile: UserProfile) -> "UserRead":
        data = cls.model_validate(profile)
        data.permissions = sorted(effective_permissions(profile.role, profile.access_grants, profile.access_revokes))
        return data


class UserCreate(BaseModel):
    name: str
    email: str | None = None
    role: Role


class UserUpdate(BaseModel):
    name: str | None = None
    email: str | None = None
    role: Role | None = None
    is_active: bool | None = None
    access_grants: list[str] | None = None
    access_revokes: list[str] | None = None


class RoleRead(BaseModel):
    role: Role
    label: str
    permissions: list[str]


class MeRead(BaseModel):
    profile: UserRead | None
    role: Role
    role_label: str
    permissions: list[str]


@router.get("/roles", response_model=list[RoleRead])
def list_roles() -> list[RoleRead]:
    return [RoleRead(role=r, label=role_label(r), permissions=sorted(role_defaults(r))) for r in Role]


@router.get("/access-catalog")
def access_catalog() -> dict:
    """Everything a director can tick/untick per profile, and each role's defaults."""

    return {
        "items": [{"permission": i.permission, "label": i.label, "group": i.group, "sensitive": i.sensitive} for i in ACCESS_CATALOG],
        "role_defaults": {r.value: sorted(role_defaults(r)) for r in Role},
    }


@router.get("/me", response_model=MeRead)
def me(user: CurrentUser = Depends(get_current_user)) -> MeRead:
    return MeRead(
        profile=UserRead.of(user.profile) if user.profile else None,
        role=user.role,
        role_label=role_label(user.role),
        permissions=sorted(user.permissions),
    )


@router.get("", response_model=list[UserRead])
def list_users(db: Session = Depends(get_db), company: Company = Depends(current_company)) -> list[UserRead]:
    return [UserRead.of(u) for u in db.query(UserProfile).filter_by(company_id=company.id).order_by(UserProfile.created_at).all()]


@router.post("", response_model=UserRead)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    company: Company = Depends(current_company),
    user: CurrentUser = Depends(get_current_user),
) -> UserRead:
    # The very first profile is created by onboarding, before anyone exists
    # to hold WRITE_SETTINGS; every later one needs it.
    has_any = db.query(UserProfile.id).filter_by(company_id=company.id).first() is not None
    if has_any and not user.can(WRITE_SETTINGS):
        raise HTTPException(status_code=403, detail=tx("Votre profil ne permet pas de gérer les utilisateurs.", "Your profile does not allow managing users."))
    profile = UserProfile(company_id=company.id, name=payload.name.strip(), email=payload.email, role=payload.role, access_grants=[], access_revokes=[])
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return UserRead.of(profile)


_ADMIN_FIELDS = {"role", "is_active", "access_grants", "access_revokes"}


@router.patch("/{user_id}", response_model=UserRead)
def update_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> UserRead:
    profile = db.get(UserProfile, user_id)
    if profile is None:
        raise HTTPException(status_code=404, detail=tx("Profil introuvable", "Profile not found"))
    changes = payload.model_dump(exclude_unset=True)
    editing_self = user.profile is not None and user.profile.id == profile.id
    admin_change = bool(_ADMIN_FIELDS & changes.keys())

    # Anyone may rename themselves. Access, role and activation are an
    # administrator's decision (write:settings) -- and never on one's own
    # profile: nobody grants themselves permissions (brain/permissions.md).
    if admin_change and editing_self:
        raise HTTPException(status_code=403, detail=tx("Vous ne pouvez pas modifier vos propres accès ou votre propre rôle.", "You cannot change your own access or your own role."))
    if (admin_change or not editing_self) and not user.can(WRITE_SETTINGS):
        raise HTTPException(status_code=403, detail=tx("Votre profil ne permet pas de gérer les utilisateurs.", "Your profile does not allow managing users."))
    for key in ("access_grants", "access_revokes"):
        if key in changes:
            unknown = set(changes[key] or []) - ALL_PERMISSIONS
            if unknown:
                raise HTTPException(status_code=400, detail=tx(f"Permission inconnue : {', '.join(sorted(unknown))}", f"Unknown permission: {', '.join(sorted(unknown))}"))
            changes[key] = sorted(set(changes[key] or []))
    for field, value in changes.items():
        setattr(profile, field, value)
    db.commit()
    db.refresh(profile)
    return UserRead.of(profile)
