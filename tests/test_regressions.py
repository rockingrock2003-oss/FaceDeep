import hashlib
import hmac
import time

import pytest

from app.services.liveness.layer3 import Layer3IntegrityCheck
from app.services.webhook_service import webhook_service


@pytest.mark.asyncio
async def test_chunked_upload_round_trip(client, auth_data, sample_image_bytes):
    token = auth_data["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    create = await client.post(
        "/api/v2/upload/presigned-url",
        headers=headers,
        params={
            "filename": "face.jpg",
            "content_type": "image/jpeg",
            "file_size": len(sample_image_bytes),
        },
    )
    assert create.status_code == 200, create.text
    upload_id = create.json()["upload_id"]

    part = await client.post(
        f"/api/v2/upload/{upload_id}/part",
        headers=headers,
        params={"part_number": 1},
        files={"file": ("chunk.bin", sample_image_bytes, "application/octet-stream")},
    )
    assert part.status_code == 200, part.text

    complete = await client.post(
        f"/api/v2/upload/{upload_id}/complete",
        headers=headers,
    )
    assert complete.status_code == 200, complete.text
    assert complete.json()["total_size"] == len(sample_image_bytes)

    download = await client.get(
        f"/api/v2/upload/{upload_id}/file",
        headers=headers,
    )
    assert download.status_code == 200, download.text
    assert download.content == sample_image_bytes

    abort = await client.delete(
        f"/api/v2/upload/{upload_id}",
        headers=headers,
    )
    assert abort.status_code == 200


@pytest.mark.asyncio
async def test_abort_does_not_delete_another_users_upload(
    client,
    auth_data,
    sample_image_bytes,
):
    owner_headers = {"Authorization": f"Bearer {auth_data['access_token']}"}
    create = await client.post(
        "/api/v2/upload/presigned-url",
        headers=owner_headers,
        params={
            "filename": "face.jpg",
            "content_type": "image/jpeg",
            "file_size": len(sample_image_bytes),
        },
    )
    upload_id = create.json()["upload_id"]

    other = await client.post(
        "/api/v1/auth/register",
        json={
            "username": "other-upload-user",
            "email": "other-upload@example.com",
            "password": "testpass123",
        },
    )
    assert other.status_code == 200, other.text
    other_headers = {"Authorization": f"Bearer {other.json()['access_token']}"}

    forbidden = await client.delete(
        f"/api/v2/upload/{upload_id}",
        headers=other_headers,
    )
    assert forbidden.status_code == 403

    owner_abort = await client.delete(
        f"/api/v2/upload/{upload_id}",
        headers=owner_headers,
    )
    assert owner_abort.status_code == 200


@pytest.mark.asyncio
async def test_webhook_test_creates_retry_schedule(
    client,
    auth_data,
    monkeypatch,
    test_session,
):
    headers = {"Authorization": f"Bearer {auth_data['access_token']}"}
    create = await client.post(
        "/api/v2/webhooks",
        headers=headers,
        json={"url": "https://example.invalid/hook", "events": ["face.enrolled"]},
    )
    assert create.status_code == 201, create.text
    webhook_id = create.json()["id"]

    async def fail_delivery(url, payload, signature, delivery):
        delivery.attempts += 1
        delivery.response_body = "simulated failure"
        return False

    monkeypatch.setattr(webhook_service, "_send_request", fail_delivery)

    response = await client.post(
        f"/api/v2/webhooks/{webhook_id}/test",
        headers=headers,
    )
    assert response.status_code == 200, response.text

    deliveries = await client.get(
        f"/api/v2/webhooks/{webhook_id}/deliveries",
        headers=headers,
    )
    assert deliveries.status_code == 200, deliveries.text
    delivery = deliveries.json()[0]
    assert delivery["status"] == "failed"
    assert delivery["attempts"] == 1

    # Verify the service produced a valid first retry deadline rather than
    # datetime.replace(second=60), which used to raise ValueError.
    from sqlalchemy import select

    from app.models.webhook import WebhookDelivery

    result = await test_session.execute(
        select(WebhookDelivery).where(WebhookDelivery.id == delivery["id"])
    )
    stored = result.scalar_one()
    assert stored.next_retry_at is not None
    retry_delay = (stored.next_retry_at - stored.created_at).total_seconds()
    assert 55 <= retry_delay <= 65


def test_liveness_hmac_cannot_be_bypassed_when_configured():
    checker = Layer3IntegrityCheck()
    checker.hmac_secret = b"test-secret"

    missing = checker.verify_hmac(b"image")
    assert missing["passed"] is False
    assert missing["detail"] == "missing_signature"

    timestamp = str(int(time.time()))
    payload = timestamp.encode() + b"." + hashlib.sha256(b"image").digest()
    signature = hmac.new(b"test-secret", payload, hashlib.sha256).hexdigest()

    valid = checker.verify_hmac(
        b"image",
        signature=signature,
        timestamp=timestamp,
    )
    assert valid["passed"] is True


@pytest.mark.asyncio
async def test_team_api_key_permissions_and_org_namespace(
    client,
    auth_data,
    test_session,
):
    from sqlalchemy import select

    from app.models.organization import Team

    headers = {"Authorization": f"Bearer {auth_data['access_token']}"}
    create_org = await client.post(
        "/api/v2/organizations",
        headers=headers,
        json={"name": "Regression Org", "slug": "regression-org"},
    )
    assert create_org.status_code == 201, create_org.text
    org_id = create_org.json()["id"]

    get_org = await client.get(
        f"/api/v2/organizations/{org_id}",
        headers=headers,
    )
    assert get_org.status_code == 200, get_org.text

    result = await test_session.execute(select(Team).where(Team.organization_id == org_id))
    team = result.scalars().first()
    assert team is not None

    create_key = await client.post(
        f"/api/v2/organizations/{org_id}/api-keys",
        headers=headers,
        json={"team_id": team.id, "permissions": ["face:read"]},
    )
    assert create_key.status_code == 200, create_key.text
    team_key = create_key.json()["api_key"]
    team_headers = {"X-API-Key": team_key}

    read_faces = await client.get(
        "/api/v2/face/persons",
        headers=team_headers,
    )
    assert read_faces.status_code == 200, read_faces.text

    write_faces = await client.delete(
        "/api/v2/face/clear",
        headers=team_headers,
    )
    assert write_faces.status_code == 403
    assert "face:write" in write_faces.json()["detail"]


@pytest.mark.asyncio
async def test_unverified_registration_token_is_blocked_until_verification(
    client,
    monkeypatch,
    test_session,
):
    from sqlalchemy import select

    from app.models.verification import EmailVerification
    from app.services.email_service import email_service
    from app.services.verification import verification_service

    monkeypatch.setattr(email_service, "is_configured", lambda: True)

    async def fake_send(user, token):
        return None

    monkeypatch.setattr(verification_service, "send_verification_email", fake_send)

    registered = await client.post(
        "/api/v1/auth/register",
        json={
            "username": "needs-verification",
            "email": "needs-verification@example.com",
            "password": "testpass123",
        },
    )
    assert registered.status_code == 200, registered.text
    payload = registered.json()
    assert payload["requires_verification"] is True
    token = payload["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    blocked = await client.get("/api/v2/auth/me", headers=headers)
    assert blocked.status_code == 403

    result = await test_session.execute(
        select(EmailVerification).where(EmailVerification.user_id == payload["user_id"])
    )
    verification = result.scalars().first()
    assert verification is not None

    verified = await client.get(
        "/api/v2/auth/verify-email",
        params={"token": verification.token},
    )
    assert verified.status_code == 200, verified.text

    allowed = await client.get("/api/v2/auth/me", headers=headers)
    assert allowed.status_code == 200, allowed.text


@pytest.mark.asyncio
async def test_private_outbound_urls_are_rejected():
    from app.core.url_security import validate_public_http_url

    with pytest.raises(ValueError):
        await validate_public_http_url("http://127.0.0.1/private")

    with pytest.raises(ValueError):
        await validate_public_http_url("https://localhost/hook", https_only=True)


@pytest.mark.asyncio
async def test_paid_checkout_session_is_required_for_plan_activation(
    client,
    auth_data,
    monkeypatch,
):
    import stripe

    from app.core.config import settings

    headers = {"Authorization": f"Bearer {auth_data['access_token']}"}
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test_regression")

    def fake_retrieve(session_id):
        assert session_id == "cs_test_valid"
        return {
            "payment_status": "paid",
            "customer_details": {"email": "test@example.com"},
            "metadata": {"plan": "starter"},
            "amount_total": int(settings.STARTER_PRICE * 100),
            "customer": "cus_regression",
        }

    monkeypatch.setattr(stripe.checkout.Session, "retrieve", fake_retrieve)

    response = await client.post(
        "/api/v2/billing/activate",
        headers=headers,
        json={"plan": "starter", "session_id": "cs_test_valid"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["plan"] == "starter"

    def unpaid_retrieve(session_id):
        return {
            "payment_status": "unpaid",
            "customer_details": {"email": "test@example.com"},
            "metadata": {"plan": "pro"},
            "amount_total": int(settings.PRO_PRICE * 100),
        }

    monkeypatch.setattr(stripe.checkout.Session, "retrieve", unpaid_retrieve)
    unpaid = await client.post(
        "/api/v2/billing/activate",
        headers=headers,
        json={"plan": "pro", "session_id": "cs_test_unpaid"},
    )
    assert unpaid.status_code == 400


def test_test_user_seeding_is_disabled_by_default():
    from app.core.config import Settings

    assert Settings(_env_file=None).SEED_TEST_USER is False


def test_production_settings_require_secure_configuration():
    from app.core.config import Settings

    with pytest.raises(ValueError, match="SECRET_KEY"):
        Settings(ENVIRONMENT="production", _env_file=None)

    with pytest.raises(ValueError, match="CORS_ORIGINS"):
        Settings(
            ENVIRONMENT="production",
            SECRET_KEY="s" * 64,
            CORS_ORIGINS=["*"],
            _env_file=None,
        )

    with pytest.raises(ValueError, match="SEED_TEST_USER"):
        Settings(
            ENVIRONMENT="production",
            SECRET_KEY="s" * 64,
            CORS_ORIGINS=["https://facedeep.example"],
            SEED_TEST_USER=True,
            _env_file=None,
        )

    secure = Settings(
        ENVIRONMENT="production",
        SECRET_KEY="s" * 64,
        CORS_ORIGINS=["https://facedeep.example"],
        SEED_TEST_USER=False,
        _env_file=None,
    )
    assert secure.ENVIRONMENT == "production"
