"""V2.1 custom profile access: role defaults + director grants/revokes,
enforced by the backend; nobody grants themselves permissions."""

import pytest

from app.access.policy import ROLE_PERMISSIONS, effective_permissions
from app.core.entities import Role, UserProfile
from tests.v2_support import api_client, build_world


@pytest.fixture()
def world(db_session):
    return build_world(db_session)


def _profile(db_session, world, name, role, grants=None, revokes=None):
    p = UserProfile(company_id=world.company.id, name=name, role=role, access_grants=grants or [], access_revokes=revokes or [])
    db_session.add(p)
    db_session.commit()
    return p, {"X-User-Id": str(p.id)}


def test_effective_permissions_are_role_defaults_plus_grants_minus_revokes():
    base = ROLE_PERMISSIONS[Role.SALES]
    assert "view:finance" in base and "view:treasury" not in base
    custom = effective_permissions(Role.SALES, grants=["view:people", "not:a_permission"], revokes=["view:finance"])
    assert "view:people" in custom and "view:finance" not in custom
    assert "not:a_permission" not in custom  # unknown names are ignored, never trusted


def test_sensitive_areas_are_director_only_by_default():
    for role in Role:
        if role != Role.DIRECTOR:
            assert not {"view:treasury", "view:ownership", "view:employee_costs"} & ROLE_PERMISSIONS[role]


def test_director_customises_a_profile_and_the_backend_enforces_it(session_factory, db_session, world):
    director, as_director = _profile(db_session, world, "Dir", Role.DIRECTOR)
    alice, as_alice = _profile(db_session, world, "Alice", Role.SALES)
    with api_client(session_factory) as client:
        assert client.get("/finance/overview", headers=as_alice).status_code == 200
        assert client.get("/treasury/overview", headers=as_alice).status_code == 403
        assert client.get("/people/employees", headers=as_alice).status_code == 403

        updated = client.patch(f"/users/{alice.id}", json={"access_revokes": ["view:finance"], "access_grants": ["view:people"]}, headers=as_director)
        assert updated.status_code == 200
        assert "view:finance" not in updated.json()["permissions"] and "view:people" in updated.json()["permissions"]

        assert client.get("/finance/overview", headers=as_alice).status_code == 403  # revoked, refused server-side
        assert client.get("/people/employees", headers=as_alice).status_code == 200  # granted
        assert client.get("/documents/margins", headers=as_alice).status_code == 403
        me = client.get("/users/me", headers=as_alice).json()
        assert "view:finance" not in me["permissions"]

        # Nobody grants themselves anything -- not even through a role change.
        assert client.patch(f"/users/{alice.id}", json={"access_grants": ["view:treasury"]}, headers=as_alice).status_code == 403
        assert client.patch(f"/users/{alice.id}", json={"role": "director"}, headers=as_alice).status_code == 403
        assert client.patch(f"/users/{director.id}", json={"access_revokes": ["view:sales"]}, headers=as_director).status_code == 403
        assert client.patch(f"/users/{alice.id}", json={"name": "Alice M."}, headers=as_alice).status_code == 200  # renaming oneself is fine

        # Unknown permissions are refused; deactivation blocks the profile.
        assert client.patch(f"/users/{alice.id}", json={"access_grants": ["root:everything"]}, headers=as_director).status_code == 400
        assert client.patch(f"/users/{alice.id}", json={"is_active": False}, headers=as_director).status_code == 200
        assert client.get("/users/me", headers=as_alice).status_code == 401


def test_catalog_lists_every_permission_once_and_role_defaults(session_factory, world):
    with api_client(session_factory) as client:
        catalog = client.get("/users/access-catalog").json()
    permissions = [i["permission"] for i in catalog["items"]]
    assert len(permissions) == len(set(permissions))
    assert {"view:treasury", "view:ownership", "view:employee_costs"} <= {i["permission"] for i in catalog["items"] if i["sensitive"]}
    assert "view:treasury" not in catalog["role_defaults"]["sales"]


def test_restricted_objects_disappear_from_search_and_related(session_factory, db_session, world):
    _, as_buyer = _profile(db_session, world, "Bea", Role.PROCUREMENT)
    with api_client(session_factory) as client:
        found = client.get("/objects/search", params={"q": "Groupe"}, headers=as_buyer).json()
        assert all(r["type"] != "customer" for r in found)  # buyers do not see customers
        ctx = client.get(f"/objects/product/{world.product.id}/context", headers=as_buyer).json()
        assert all(g["type"] != "customer" for g in ctx["related"])
