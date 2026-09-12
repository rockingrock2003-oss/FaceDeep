import numpy as np
import pytest

from app.services.liveness import LivenessDetector


@pytest.fixture
def detector():
    return LivenessDetector()


def test_detector_initialization(detector):
    assert detector.min_score == 70.0
    assert detector.face_mesh is not None


def test_check_liveness_invalid_image(detector):
    result = detector.check_liveness_sync(b"not an image")
    assert result["status"] == "error"
    assert result["label"] == "error"


def test_check_liveness_blank_image(detector):
    import cv2

    blank = np.zeros((200, 200, 3), dtype=np.uint8)
    _, buffer = cv2.imencode(".jpg", blank)

    result = detector.check_liveness_sync(buffer.tobytes())
    assert result["status"] == "error"
    assert result["label"] == "no_face"


def test_check_liveness_components(detector):
    import cv2

    img = np.zeros((300, 300, 3), dtype=np.uint8)
    cv2.circle(img, (150, 120), 40, (180, 180, 180), -1)
    cv2.circle(img, (135, 110), 5, (50, 50, 50), -1)
    cv2.circle(img, (165, 110), 5, (50, 50, 50), -1)
    cv2.ellipse(img, (150, 150), (15, 8), 0, 0, 180, (50, 50, 50), 2)

    _, buffer = cv2.imencode(".jpg", img)
    result = detector.check_liveness_sync(buffer.tobytes())

    assert "liveness_score" in result
    assert "label" in result
    assert "components" in result
    assert isinstance(result["liveness_score"], float)


@pytest.mark.asyncio
async def test_check_liveness_async(detector):
    import cv2

    blank = np.zeros((200, 200, 3), dtype=np.uint8)
    _, buffer = cv2.imencode(".jpg", blank)

    result = await detector.check_liveness(buffer.tobytes())
    assert "status" in result
    assert "liveness_score" in result


def test_liveness_score_range(detector):
    import cv2

    img = np.random.randint(0, 255, (300, 300, 3), dtype=np.uint8)
    _, buffer = cv2.imencode(".jpg", img)

    result = detector.check_liveness_sync(buffer.tobytes())
    assert 0 <= result["liveness_score"] <= 100
