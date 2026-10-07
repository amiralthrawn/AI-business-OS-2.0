"""Who is calling, and may they (V2).

Identity comes from the `X-User-Id` header naming a UserProfile. There is no
authentication in this MVP (no password, no session, see
brain/permissions.md): the header is a *declared* identity, so this layer
is an authorization model for the product (what each profile sees and
does), enforced by the backend -- not a security boundary until a real
auth layer sets the same `CurrentUser` from a verified token.

No header -> the legacy single-operator mode every V1 client and test uses:
full director rights, reported as `profile=None` so the UI can say "no
profile selected" instead of pretending someone is signed in.
"""

import uuid
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.core.i18n import tx
from app.access.policy import can_approve_with, effective_permissions
from app.core.entities import Role, UserProfile
from app.database import get_db


@dataclass(frozen=True)
class CurrentUser:
    role: Role
    profile: UserProfile | None

    @property
    def permissions(self) -> frozenset[str]:
        # Role defaults + the director's custom grants/revokes for this profile.
        if self.profile is None:
            return effective_permissions(self.role)
        return effective_permissions(self.role, self.profile.access_grants, self.profile.access_revokes)

    def can(self, permission: str) -> bool:
        return permission in self.permissions

    def can_approve(self, task_domain: str | None) -> bool:
        return can_approve_with(self.role, self.permissions, task_domain)


LEGACY_OPERATOR = CurrentUser(role=Role.DIRECTOR, profile=None)


def get_current_user(x_user_id: str | None = Header(default=None), db: Session = Depends(get_db)) -> CurrentUser:
    if not x_user_id:
        return LEGACY_OPERATOR
    try:
        user_id = uuid.UUID(x_user_id)
    except ValueError:
        raise HTTPException(status_code=401, detail=tx("Profil utilisateur inconnu", "Unknown user profile"))
    profile = db.get(UserProfile, user_id)
    if profile is None or not profile.is_active:
        raise HTTPException(status_code=401, detail=tx("Profil utilisateur inconnu", "Unknown user profile"))
    return CurrentUser(role=profile.role, profile=profile)


def require(permission: str):
    """FastAPI dependency factory: 403 unless the caller's effective permissions include `permission`."""

    def dependency(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if not user.can(permission):
            raise HTTPException(status_code=403, detail=tx(f"Votre profil n'a pas accès à cette partie du logiciel ({permission}).", f"Your profile does not have access to this part of the software ({permission})."))
        return user

    return dependency
