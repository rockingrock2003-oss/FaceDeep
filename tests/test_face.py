import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_and_get_api_key(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "username": "faceuser",
            "email": "face@example.com",
            "password": "facepassword",
        },
    )
    assert response.status_code == 201
    api_key = response.json()["api_key"]
    assert api_key is not None
    return api_key


@pytest.mark.asyncio
async def test_enroll_face_missing_api_key(client: AsyncClient, sample_image_bytes):
    response = await client.post(
        "/api/v1/face/enroll",
        files={"file": ("test.jpg", sample_image_bytes, "image/jpeg")},
        data={"person_id": "person_001", "label": "John Doe"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_enroll_face_invalid_api_key(client: AsyncClient, sample_image_bytes):
    response = await client.post(
        "/api/v1/face/enroll",
        headers={"X-API-Key": "fd_invalid_key_12345"},
        files={"file": ("test.jpg", sample_image_bytes, "image/jpeg")},
        data={"person_id": "person_001", "label": "John Doe"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_liveness_no_face(client: AsyncClient):
    import numpy as np
    import cv2

    response = await client.post(
        "/api/v1/auth/register",
        json={
            "username": "livenessuser",
            "email": "liveness@example.com",
            "password": "password123",
        },
    )
    api_key = response.json()["api_key"]

    blank_img = np.zeros((200, 200, 3), dtype=np.uint8)
    _, buffer = cv2.imencode(".jpg", blank_img)

    response = await client.post(
        "/api/v1/face/liveness",
        headers={"X-API-Key": api_key},
        files={"file": ("blank.jpg", buffer.tobytes(), "image/jpeg")},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["label"] in ["no_face", "not_live", "uncertain"]


@pytest.mark.asyncio
async def test_list_persons_empty(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "username": "listuser",
            "email": "list@example.com",
            "password": "password123",
        },
    )
    api_key = response.json()["api_key"]

    response = await client.get(
        "/api/v1/face/persons",
        headers={"X-API-Key": api_key},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 0
    assert data["persons"] == []


@pytest.mark.asyncio
async def test_delete_nonexistent_person(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "username": "deluser",
            "email": "del@example.com",
            "password": "password123",
        },
    )
    api_key = response.json()["api_key"]

    response = await client.delete(
        "/api/v1/face/delete",
        headers={"X-API-Key": api_key},
        json={"person_id": "nonexistent_person"},
    )
    assert response.status_code == 404
