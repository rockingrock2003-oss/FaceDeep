import pytest


@pytest.mark.asyncio
async def test_enroll_face_missing_api_key(client, sample_image_bytes):
    response = await client.post(
        "/api/v1/face/enroll",
        files={"file": ("test.jpg", sample_image_bytes, "image/jpeg")},
        data={"person_id": "person_001"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_enroll_face_invalid_api_key(client, sample_image_bytes):
    response = await client.post(
        "/api/v1/face/enroll",
        headers={"X-API-Key": "fd_invalid_key_12345"},
        files={"file": ("test.jpg", sample_image_bytes, "image/jpeg")},
        data={"person_id": "person_001"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_recognize_not_live(client, auth_data):
    import cv2
    import numpy as np

    blank_img = np.zeros((200, 200, 3), dtype=np.uint8)
    _, buffer = cv2.imencode(".jpg", blank_img)

    response = await client.post(
        "/api/v1/face/recognize",
        headers={"X-API-Key": auth_data["api_key"]},
        files={"file": ("blank.jpg", buffer.tobytes(), "image/jpeg")},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "not_live"
    assert data["person_id"] == -1


@pytest.mark.asyncio
async def test_list_persons_empty(client, auth_data):
    response = await client.get(
        "/api/v1/face/persons",
        headers={"X-API-Key": auth_data["api_key"]},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 0
    assert data["persons"] == []


@pytest.mark.asyncio
async def test_delete_nonexistent_person(client, auth_data):
    response = await client.delete(
        "/api/v1/face/delete",
        headers={"X-API-Key": auth_data["api_key"]},
        json={"person_id": "nonexistent_person"},
    )
    assert response.status_code == 404
