"""V2.1 people: cost as a labelled range, partial contribution, HITL-only
HR decisions, skills gap -> Opportunity, candidates from emails."""

from datetime import datetime, timedelta, timezone

import pytest

from app.core.entities import (
    Communication,
    CommunicationDirection,
    Employee,
    EmployeeCostItem,
    Opportunity,
    Role,
    SkillNeed,
    Task,
    TaskStatus,
    UserProfile,
    ValueBasis,
)
from app.event_bus import build_event_bus
from app.people import service
from tests.v2_support import api_client, build_world

NOW = datetime.now(timezone.utc)


@pytest.fixture()
def world(db_session):
    w = build_world(db_session)
    from app.core.entities import BusinessContext

    db_session.add(BusinessContext(company_id=w.company.id, country="FR", monitored_domains=[], home_focus=[], declared_baselines={}, learned_notes=[], finance_settings={}))
    db_session.commit()
    return w


@pytest.fixture()
def bus(session_factory):
    return build_event_bus(session_factory)


def _employee(db_session, world, name="Alice", skills=None, salary=40000.0, basis=ValueBasis.DECLARED, **kw):
    e = Employee(company_id=world.company.id, full_name=name, job_title="Chargée de projet", status="active", skills=skills or [], responsibilities=[], data_basis=basis, **kw)
    if salary:
        e.cost_items = [EmployeeCostItem(kind="salary", annual_min=salary, annual_max=salary, basis=basis, confidence="high")]
    db_session.add(e)
    db_session.commit()
    return e


def test_cost_adds_benchmark_charges_and_stays_a_labelled_range(db_session, world):
    e = _employee(db_session, world)
    cost = service.employee_cost(db_session, e)
    charges = next(line for line in cost.lines if line.kind == "employer_charges")
    assert charges.computed and charges.basis == "benchmark" and "FR" in charges.source
    assert (cost.total_min, cost.total_max) == (40000 + 16000, 40000 + 18800)
    assert cost.basis == "benchmark"  # weakest component: never presented as exact
    assert any("Logiciels" in m for m in cost.missing)

    no_salary = _employee(db_session, world, name="Bob", salary=None)
    empty = service.employee_cost(db_session, no_salary)
    assert empty.basis == "unknown" and empty.confidence == "none"


def test_contribution_is_partial_and_says_when_data_is_insufficient(db_session, world):
    e = _employee(db_session, world)
    c = service.estimate_contribution(db_session, e)
    assert c.sufficient is False and c.confidence == "none" and "insuffisantes" in c.statement

    for i in range(5):
        db_session.add(Task(company_id=world.company.id, title=f"t{i}", status=TaskStatus.DONE, assignee_employee_id=e.id))
    db_session.commit()
    c = service.estimate_contribution(db_session, e)
    assert c.sufficient and c.confidence == "low" and "partielle" in c.statement.lower()
    assert c.attributable_margin_min is None  # no revenue attributable: none invented


def test_promotion_and_raise_only_apply_after_director_approval(session_factory, db_session, world):
    e = _employee(db_session, world)
    hr = UserProfile(company_id=world.company.id, name="Rh", role=Role.HR, access_grants=[], access_revokes=[])
    director = UserProfile(company_id=world.company.id, name="Dir", role=Role.DIRECTOR, access_grants=[], access_revokes=[])
    db_session.add_all([hr, director])
    db_session.commit()
    as_hr, as_dir = {"X-User-Id": str(hr.id)}, {"X-User-Id": str(director.id)}
    with api_client(session_factory) as client:
        # HR sees people but not salaries, and cannot propose a raise without cost access.
        assert "cost" not in client.get("/people/employees", headers=as_hr).json()[0]
        assert client.get(f"/people/employees/{e.id}", headers=as_hr).json()["cost"] is None
        assert client.post(f"/people/employees/{e.id}/decisions", json={"kind": "raise", "rationale": "x", "new_salary": 45000}, headers=as_hr).status_code == 403

        proposal = client.post(f"/people/employees/{e.id}/decisions", json={"kind": "promotion", "rationale": "Pilote le projet data", "new_job_title": "Cheffe de projet senior"}, headers=as_hr).json()
        assert client.patch(f"/people/employees/{e.id}", json={"job_title": "Directrice"}, headers=as_dir).status_code == 400  # no bypass
        db_session.expire_all()
        assert db_session.get(Employee, e.id).job_title == "Chargée de projet"  # nothing applied yet

        assert client.post(f"/actions/tasks/{proposal['task_id']}/approve", headers=as_hr).status_code == 403  # people decisions: director only
        assert client.post(f"/actions/tasks/{proposal['task_id']}/approve", headers=as_dir).status_code == 200
        db_session.expire_all()
        assert db_session.get(Employee, e.id).job_title == "Cheffe de projet senior"

        raise_ = client.post(f"/people/employees/{e.id}/decisions", json={"kind": "raise", "rationale": "Marché", "new_salary": 46000}, headers=as_dir).json()
        client.post(f"/actions/tasks/{raise_['task_id']}/approve", headers=as_dir)
        detail = client.get(f"/people/employees/{e.id}", headers=as_dir).json()
        salary = next(line for line in detail["cost"]["lines"] if line["kind"] == "salary")
        assert salary["annual_min"] == 46000 and salary["basis"] == "declared"
        timeline = client.get(f"/objects/employee/{e.id}/context", headers=as_dir).json()["timeline"]
        assert {"EmployeeDecisionApplied", "EmployeeCostChanged"} <= {t["event_type"] for t in timeline}


def test_assigned_tasks_appear_on_the_employee(session_factory, db_session, world):
    e = _employee(db_session, world)
    with api_client(session_factory) as client:
        client.post(f"/people/employees/{e.id}/tasks", json={"title": "Préparer le reporting", "due_at": (NOW - timedelta(days=1)).isoformat()})
        detail = client.get(f"/people/employees/{e.id}").json()
    assert detail["task_list"][0]["title"] == "Préparer le reporting"
    assert detail["tasks"]["open"] == 1 and detail["tasks"]["overdue"] == 1


def test_skills_gap_detects_uncovered_need_and_feeds_v1_opportunities(db_session, world, bus):
    _employee(db_session, world, skills=["vente", "excel"])
    db_session.add(SkillNeed(company_id=world.company.id, skill="Data / automatisation", keywords=["python", "sql"], priority="high", reason="Reporting manuel"))
    db_session.add(SkillNeed(company_id=world.company.id, skill="Vente", keywords=["négociation"], priority="low"))
    db_session.commit()
    gap = service.skills_gap(db_session, world.company.id)
    assert [g["skill"] for g in gap["gaps"]] == ["Data / automatisation"]
    assert gap["gaps"][0]["recommendation"]["priority"] == "high"
    assert [c["skill"] for c in gap["covered"]] == ["Vente"]

    assert service.publish_skill_gaps(db_session, bus, world.company.id) == 1
    assert service.publish_skill_gaps(db_session, bus, world.company.id) == 0  # idempotent
    assert db_session.query(Opportunity).filter_by(title="Recruter ou former : Data / automatisation").count() == 1


def test_evolution_suggestion_is_a_suggestion_not_a_decision(db_session, world):
    e = _employee(db_session, world, skills=["python", "sql"], hired_at=NOW - timedelta(days=800))
    db_session.add(SkillNeed(company_id=world.company.id, skill="Data / automatisation", keywords=["python"], priority="high"))
    db_session.commit()
    suggestions = service.evolution_suggestions(db_session, e)
    assert suggestions and "aucune décision automatique" in suggestions[0]["note"]
    assert db_session.query(Task).filter_by(pending_action=service.HR_DECISION_ACTION).count() == 0


def test_candidate_from_application_email_is_matched_and_invited_only_after_validation(session_factory, db_session, world):
    db_session.add(SkillNeed(company_id=world.company.id, skill="Data / automatisation", keywords=["python", "sql", "power bi"], priority="high"))
    msg = Communication(
        company_id=world.company.id, channel="email", direction=CommunicationDirection.INBOUND, status="received", occurred_at=NOW,
        subject="Candidature au poste de Data Analyst", from_address="sofia@example.org",
        body="Bonjour, je postule au poste de Data Analyst. 4 ans d'expérience : Python, SQL, Power BI.",
    )  # fmt: skip
    db_session.add(msg)
    db_session.commit()
    with api_client(session_factory) as client:
        assert any(i["key"] == "application" for i in client.post(f"/communications/{msg.id}/analyze").json()["intents"])
        assert [a["id"] for a in client.get("/people/applications").json()] == [str(msg.id)]
        candidate = client.post(f"/people/candidates/from-communication/{msg.id}").json()
        assert set(candidate["skills"]) >= {"python", "sql", "power bi"} and candidate["years_experience"] == 4
        assert candidate["applied_for"].startswith("Data Analyst") and candidate["basis"] == "declared"
        assert candidate["matches"][0]["match"] == "élevée" and candidate["matches"][0]["need_is_gap"]
        assert client.post(f"/people/candidates/from-communication/{msg.id}").json()["id"] == candidate["id"]  # idempotent

        draft = client.post("/communications/drafts", json={"purpose": "interview_invite", "object_type": "candidate", "object_id": candidate["id"]}).json()
        assert draft["to_address"] == "sofia@example.org" and "entretien" in draft["body"]
        assert client.get("/people/candidates").json()[0]["status"] == "new"  # nothing sent yet
        task_id = client.post(f"/communications/{draft['id']}/submit").json()["task_id"]
        client.post(f"/actions/tasks/{task_id}/approve")
        assert client.get("/people/candidates").json()[0]["status"] == "interview_proposed"
