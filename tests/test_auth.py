import pytest
from sqlalchemy import update

from app.models import User


@pytest.mark.asyncio
async def test_register_user(client, test_session):
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "username": "newuser",
            "email": "new@example.com",
            "password": "securepassword123",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["username"] == "newuser"


@pytest.mark.asyncio
async def test_register_duplicate_user(client):
    await client.post(
        "/api/v1/auth/register",
        json={
            "username": "dupuser",
            "email": "dup@example.com",
            "password": "password123",
        },
    )
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "username": "dupuser",
            "email": "dup2@example.com",
            "password": "password123",
        },
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_register_duplicate_email(client):
    await client.post(
        "/api/v1/auth/register",
        json={
            "username": "user1",
            "email": "same@example.com",
            "password": "password123",
        },
    )
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "username": "user2",
            "email": "same@example.com",
            "password": "password123",
        },
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_login_success(client, test_session):
    await client.post(
        "/api/v1/auth/register",
        json={
            "username": "loginuser",
            "email": "login@example.com",
            "password": "mypassword",
        },
    )
    await test_session.execute(
        update(User)
        .where(User.username == "loginuser")
        .values(is_verified=True)
    )
    await test_session.commit()

    response = await client.post(
        "/api/v1/auth/login",
        json={
            "username": "loginuser",
            "password": "mypassword",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["username"] == "loginuser"


@pytest.mark.asyncio
async def test_login_wrong_password(client, test_session):
    await client.post(
        "/api/v1/auth/register",
        json={
            "username": "wrongpwuser",
            "email": "wrongpw@example.com",
            "password": "correctpassword",
        },
    )
    await test_session.execute(
        update(User)
        .where(User.username == "wrongpwuser")
        .values(is_verified=True)
    )
    await test_session.commit()

    response = await client.post(
        "/api/v1/auth/login",
        json={
            "username": "wrongpwuser",
            "password": "wrongpassword",
        },
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_nonexistent_user(client):
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "username": "nonexistent",
            "password": "password",
        },
    )
    assert response.status_code == 401
