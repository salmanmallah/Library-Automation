import pytest
from fastapi.testclient import TestClient
from core.database.models import User, Book, BookCopy, Shelf
from core.auth.security import hash_password, create_access_token
from core.services import catalog_service, circulation_service

def test_unauthenticated_scanner_switch_rejected(client: TestClient):
    """Anonymous access to scanner camera switch must return 401 Unauthorized."""
    res = client.post("/api/scanner/switch", json={"source": "0"})
    assert res.status_code == 401

def test_member_scanner_switch_forbidden(client: TestClient, member_token: str):
    """Member role is forbidden from toggling physical scanner hardware."""
    res = client.post(
        "/api/scanner/switch",
        json={"source": "0"},
        headers={"Authorization": f"Bearer {member_token}"}
    )
    assert res.status_code == 403

def test_scanner_ssrf_prevention(client: TestClient, admin_token: str):
    """Camera switch must block SSRF attempts to cloud metadata or link-local destinations."""
    # Test AWS/GCP metadata address
    res = client.post(
        "/api/scanner/switch",
        json={"source": "http://169.254.169.254/latest/meta-data/"},
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert res.status_code == 400
    detail = res.json().get("detail", "").lower()
    assert "metadata" in detail or "forbidden" in detail

    # Test link-local IP
    res2 = client.post(
        "/api/scanner/switch",
        json={"source": "http://169.254.1.1:8080/stream"},
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert res2.status_code == 400
    detail2 = res2.json().get("detail", "").lower()
    assert "link-local" in detail2 or "forbidden" in detail2

def test_user_profile_ownership_enforcement(client: TestClient, db_session, member_token: str):
    """Members cannot view other users' profiles via /api/users/{id}."""
    # Create another member
    other_member = User(
        username="other_student",
        email="other@test.edu",
        hashed_password=hash_password("Pass123"),
        full_name="Bob Other",
        role="member",
        member_code="TEST-MEM-99",
        is_active=True
    )
    db_session.add(other_member)
    db_session.commit()

    # Logged-in member (student1) tries to view other_member's details
    res = client.get(
        f"/api/users/{other_member.id}",
        headers={"Authorization": f"Bearer {member_token}"}
    )
    assert res.status_code == 403
    assert "Cannot view another member's profile" in res.json().get("detail", "")

def test_cross_member_loan_renewal_forbidden(client: TestClient, db_session, member_token: str):
    """A member cannot renew a loan belonging to another member."""
    # Create victim member
    victim = User(
        username="victim_student",
        email="victim@test.edu",
        hashed_password=hash_password("Pass123"),
        full_name="Victim Student",
        role="member",
        member_code="TEST-VICTIM-01",
        is_active=True
    )
    db_session.add(victim)
    db_session.commit()

    # Create book & issue to victim
    book, _ = catalog_service.create_or_update_book(
        db_session,
        {"isbn": "9780201616224", "title": "The Pragmatic Programmer"},
        initial_copies=1
    )
    copy = book.copies[0]
    loan = circulation_service.issue_book(db_session, copy.copy_barcode, victim.member_code)

    # Now student1 (member_token) tries to renew victim's loan
    res = client.post(
        f"/api/circulation/renew/{loan.id}",
        headers={"Authorization": f"Bearer {member_token}"}
    )
    assert res.status_code == 403
    assert "You can only renew your own active loans" in res.json().get("detail", "")

def test_csv_formula_injection_sanitization(client: TestClient, db_session, admin_token: str):
    """Exporting catalog to CSV escapes formula characters (=, +, -, @) to neutralize Excel/Calc injection."""
    # Create book with malicious Excel formula in title
    malicious_title = "=cmd|'/c calc'!A1"
    catalog_service.create_or_update_book(
        db_session,
        {"isbn": "9781111111111", "title": malicious_title},
        initial_copies=1
    )

    res = client.get("/api/analytics/export/csv", headers={"Authorization": f"Bearer {admin_token}"})
    assert res.status_code == 200
    csv_text = res.text
    # Cell starting with '=' must be prefixed with single quote "'"
    assert f"'{malicious_title}" in csv_text or "'=cmd" in csv_text
