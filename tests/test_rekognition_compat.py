"""End-to-end compatibility: the unmodified AWS SDK (boto3) against FaceGate.

If these pass, an attendance backend that uses the AWS SDK only needs its
endpoint URL and credentials changed.
"""

from __future__ import annotations

import uuid

import cv2
import numpy as np
import pytest
from botocore.exceptions import ClientError

from tests.conftest import image, make_client

BUSH1, BUSH2, BUSH3 = "George_W_Bush_0001.jpg", "George_W_Bush_0002.jpg", "George_W_Bush_0003.jpg"
POWELL1, POWELL2 = "Colin_Powell_0001.jpg", "Colin_Powell_0002.jpg"
SERENA = "Serena_Williams_0001.jpg"


def _no_face_jpeg() -> bytes:
    img = np.tile(np.linspace(0, 255, 320, dtype=np.uint8), (240, 1))
    ok, buf = cv2.imencode(".jpg", cv2.cvtColor(img, cv2.COLOR_GRAY2BGR))
    return buf.tobytes()


@pytest.fixture()
def collection(rek):
    cid = f"test-{uuid.uuid4().hex[:8]}"
    rek.create_collection(CollectionId=cid)
    yield cid
    try:
        rek.delete_collection(CollectionId=cid)
    except ClientError:
        pass


def _code(exc: ClientError) -> str:
    return exc.response["Error"]["Code"]


# ---------------------------------------------------------------- collections
def test_collection_lifecycle(rek):
    cid = f"life-{uuid.uuid4().hex[:8]}"
    r = rek.create_collection(CollectionId=cid)
    assert r["StatusCode"] == 200
    assert r["CollectionArn"].endswith(f":collection/{cid}")
    assert r["FaceModelVersion"]
    assert cid in rek.list_collections()["CollectionIds"]
    d = rek.describe_collection(CollectionId=cid)
    assert d["FaceCount"] == 0 and d["UserCount"] == 0
    with pytest.raises(rek.exceptions.ResourceAlreadyExistsException):
        rek.create_collection(CollectionId=cid)
    assert rek.delete_collection(CollectionId=cid)["StatusCode"] == 200
    with pytest.raises(rek.exceptions.ResourceNotFoundException):
        rek.describe_collection(CollectionId=cid)


def test_list_collections_pagination(rek):
    ids = [f"page-{uuid.uuid4().hex[:6]}" for _ in range(3)]
    for c in ids:
        rek.create_collection(CollectionId=c)
    seen, token = [], None
    while True:
        kw = {"MaxResults": 1}
        if token:
            kw["NextToken"] = token
        r = rek.list_collections(**kw)
        seen += r["CollectionIds"]
        token = r.get("NextToken")
        if not token:
            break
    assert set(ids) <= set(seen)
    for c in ids:
        rek.delete_collection(CollectionId=c)


def test_invalid_collection_id(rek):
    with pytest.raises(ClientError) as e:
        rek.create_collection(CollectionId="bad id with spaces")
    assert _code(e.value) == "ValidationException"


# ---------------------------------------------------------------- index/search
def test_index_and_search_attendance_flow(rek, collection):
    # Enrol two employees (ExternalImageId = employee number, the usual pattern).
    r1 = rek.index_faces(CollectionId=collection, Image={"Bytes": image(BUSH1)}, ExternalImageId="EMP-001", MaxFaces=1, QualityFilter="AUTO")
    r2 = rek.index_faces(CollectionId=collection, Image={"Bytes": image(POWELL1)}, ExternalImageId="EMP-002", MaxFaces=1, QualityFilter="AUTO")
    assert len(r1["FaceRecords"]) == 1 and len(r2["FaceRecords"]) == 1
    face = r1["FaceRecords"][0]["Face"]
    assert face["ExternalImageId"] == "EMP-001"
    for k in ("FaceId", "BoundingBox", "ImageId", "Confidence"):
        assert k in face
    bb = face["BoundingBox"]
    assert 0 <= bb["Left"] <= 1 and 0 < bb["Width"] <= 1
    detail = r1["FaceRecords"][0]["FaceDetail"]
    assert {lm["Type"] for lm in detail["Landmarks"]} >= {"eyeLeft", "eyeRight", "nose", "mouthLeft", "mouthRight"}
    assert set(detail["Pose"]) == {"Roll", "Yaw", "Pitch"}

    # Check-in with a *different* photo of employee 1.
    s = rek.search_faces_by_image(CollectionId=collection, Image={"Bytes": image(BUSH2)}, MaxFaces=1, FaceMatchThreshold=95)
    assert len(s["FaceMatches"]) == 1
    assert s["FaceMatches"][0]["Face"]["ExternalImageId"] == "EMP-001"
    assert s["FaceMatches"][0]["Similarity"] >= 95
    assert "SearchedFaceBoundingBox" in s and "SearchedFaceConfidence" in s

    # Same for employee 2.
    s = rek.search_faces_by_image(CollectionId=collection, Image={"Bytes": image(POWELL2)}, FaceMatchThreshold=95)
    assert s["FaceMatches"][0]["Face"]["ExternalImageId"] == "EMP-002"

    # Someone who is not registered gets no match -> attendance rejected.
    s = rek.search_faces_by_image(CollectionId=collection, Image={"Bytes": image(SERENA)}, FaceMatchThreshold=80)
    assert s["FaceMatches"] == []


def test_similarity_scale_matches_rekognition_semantics(rek, collection):
    rek.index_faces(CollectionId=collection, Image={"Bytes": image(BUSH1)}, ExternalImageId="EMP-001")
    s = rek.search_faces_by_image(CollectionId=collection, Image={"Bytes": image(BUSH3)}, FaceMatchThreshold=0)
    top = s["FaceMatches"][0]["Similarity"]
    # Same person: Rekognition reports 99+; apps often use a 99 threshold.
    assert top >= 99.0


def test_search_without_face_raises_like_rekognition(rek, collection):
    with pytest.raises(rek.exceptions.InvalidParameterException) as e:
        rek.search_faces_by_image(CollectionId=collection, Image={"Bytes": _no_face_jpeg()})
    assert "no faces" in str(e.value).lower()


def test_index_no_face_returns_empty_records(rek, collection):
    r = rek.index_faces(CollectionId=collection, Image={"Bytes": _no_face_jpeg()})
    assert r["FaceRecords"] == []


def test_search_missing_collection(rek):
    with pytest.raises(rek.exceptions.ResourceNotFoundException):
        rek.search_faces_by_image(CollectionId="does-not-exist", Image={"Bytes": image(BUSH1)})


def test_invalid_image_format(rek, collection):
    with pytest.raises(rek.exceptions.InvalidImageFormatException):
        rek.search_faces_by_image(CollectionId=collection, Image={"Bytes": b"GIF89a not an image"})


def test_list_and_delete_faces(rek, collection):
    ids = [rek.index_faces(CollectionId=collection, Image={"Bytes": image(f)}, ExternalImageId=e)["FaceRecords"][0]["Face"]["FaceId"]
           for f, e in ((BUSH1, "EMP-001"), (POWELL1, "EMP-002"))]
    faces = rek.list_faces(CollectionId=collection)["Faces"]
    assert {f["FaceId"] for f in faces} == set(ids)
    page = rek.list_faces(CollectionId=collection, MaxResults=1)
    assert len(page["Faces"]) == 1 and "NextToken" in page
    r = rek.delete_faces(CollectionId=collection, FaceIds=[ids[0]])
    assert r["DeletedFaces"] == [ids[0]]
    assert rek.describe_collection(CollectionId=collection)["FaceCount"] == 1
    s = rek.search_faces_by_image(CollectionId=collection, Image={"Bytes": image(BUSH2)})
    assert s["FaceMatches"] == []


def test_search_faces_by_face_id(rek, collection):
    a = rek.index_faces(CollectionId=collection, Image={"Bytes": image(BUSH1)}, ExternalImageId="EMP-001")["FaceRecords"][0]["Face"]["FaceId"]
    rek.index_faces(CollectionId=collection, Image={"Bytes": image(BUSH2)}, ExternalImageId="EMP-001")
    rek.index_faces(CollectionId=collection, Image={"Bytes": image(POWELL1)}, ExternalImageId="EMP-002")
    r = rek.search_faces(CollectionId=collection, FaceId=a, FaceMatchThreshold=90)
    assert r["SearchedFaceId"] == a
    assert [m["Face"]["ExternalImageId"] for m in r["FaceMatches"]] == ["EMP-001"]


def test_multiple_enrolment_images_per_employee(rek, collection):
    for f in (BUSH1, BUSH2):
        rek.index_faces(CollectionId=collection, Image={"Bytes": image(f)}, ExternalImageId="EMP-001")
    s = rek.search_faces_by_image(CollectionId=collection, Image={"Bytes": image(BUSH3)}, MaxFaces=5)
    assert len(s["FaceMatches"]) == 2
    assert all(m["Face"]["ExternalImageId"] == "EMP-001" for m in s["FaceMatches"])
    assert s["FaceMatches"][0]["Similarity"] >= s["FaceMatches"][1]["Similarity"]


# ---------------------------------------------------------- detect / compare
def test_detect_faces(rek):
    r = rek.detect_faces(Image={"Bytes": image(BUSH1)})
    assert len(r["FaceDetails"]) >= 1
    d = r["FaceDetails"][0]
    assert d["Confidence"] > 90
    assert 0 <= d["Quality"]["Brightness"] <= 100
    assert rek.detect_faces(Image={"Bytes": _no_face_jpeg()})["FaceDetails"] == []


def test_compare_faces(rek):
    same = rek.compare_faces(SourceImage={"Bytes": image(BUSH1)}, TargetImage={"Bytes": image(BUSH2)}, SimilarityThreshold=90)
    assert len(same["FaceMatches"]) == 1 and same["FaceMatches"][0]["Similarity"] >= 90
    diff = rek.compare_faces(SourceImage={"Bytes": image(BUSH1)}, TargetImage={"Bytes": image(POWELL1)}, SimilarityThreshold=80)
    assert diff["FaceMatches"] == [] and len(diff["UnmatchedFaces"]) >= 1
    assert "SourceImageFace" in diff


# --------------------------------------------------------------------- users
def test_users_api(rek, collection):
    f1 = rek.index_faces(CollectionId=collection, Image={"Bytes": image(BUSH1)})["FaceRecords"][0]["Face"]["FaceId"]
    f2 = rek.index_faces(CollectionId=collection, Image={"Bytes": image(BUSH2)})["FaceRecords"][0]["Face"]["FaceId"]
    f3 = rek.index_faces(CollectionId=collection, Image={"Bytes": image(POWELL1)})["FaceRecords"][0]["Face"]["FaceId"]
    rek.create_user(CollectionId=collection, UserId="emp-001")
    rek.create_user(CollectionId=collection, UserId="emp-002")
    with pytest.raises(rek.exceptions.ConflictException):
        rek.create_user(CollectionId=collection, UserId="emp-001")
    r = rek.associate_faces(CollectionId=collection, UserId="emp-001", FaceIds=[f1, f2, f3], UserMatchThreshold=80)
    assert {a["FaceId"] for a in r["AssociatedFaces"]} == {f1, f2}
    assert r["UnsuccessfulFaceAssociations"][0]["Reasons"] == ["LOW_MATCH_CONFIDENCE"]
    rek.associate_faces(CollectionId=collection, UserId="emp-002", FaceIds=[f3])
    assert {u["UserId"] for u in rek.list_users(CollectionId=collection)["Users"]} == {"emp-001", "emp-002"}

    s = rek.search_users_by_image(CollectionId=collection, Image={"Bytes": image(BUSH3)}, UserMatchThreshold=90)
    assert s["UserMatches"][0]["User"]["UserId"] == "emp-001"
    s = rek.search_users(CollectionId=collection, FaceId=f1, UserMatchThreshold=90)
    assert s["UserMatches"][0]["User"]["UserId"] == "emp-001"

    # Faces tied to a user cannot be deleted until disassociated (Rekognition rule).
    d = rek.delete_faces(CollectionId=collection, FaceIds=[f1])
    assert d["DeletedFaces"] == [] and d["UnsuccessfulFaceDeletions"][0]["Reasons"] == ["ASSOCIATED_TO_AN_EXISTING_USER"]
    rek.disassociate_faces(CollectionId=collection, UserId="emp-001", FaceIds=[f1])
    assert rek.delete_faces(CollectionId=collection, FaceIds=[f1])["DeletedFaces"] == [f1]
    rek.delete_user(CollectionId=collection, UserId="emp-002")
    assert {u["UserId"] for u in rek.list_users(CollectionId=collection)["Users"]} == {"emp-001"}


# ---------------------------------------------------------------------- auth
def test_wrong_secret_rejected(server):
    bad = make_client(server["url"], secret="wrong-secret")
    with pytest.raises(ClientError) as e:
        bad.list_collections()
    assert _code(e.value) == "InvalidSignatureException"


def test_unknown_access_key_rejected(server):
    bad = make_client(server["url"], key="AKIAUNKNOWN000000000")
    with pytest.raises(ClientError) as e:
        bad.list_collections()
    assert _code(e.value) == "UnrecognizedClientException"


def test_unsigned_request_rejected(server):
    import httpx

    r = httpx.post(server["url"] + "/", headers={"X-Amz-Target": "RekognitionService.ListCollections", "Content-Type": "application/x-amz-json-1.1"}, content=b"{}")
    assert r.status_code == 400
    assert r.json()["__type"] == "MissingAuthenticationTokenException"


# ------------------------------------------------------------------- liveness
def test_liveness_session_contract(rek, server):
    import base64

    import httpx

    sid = rek.create_face_liveness_session(Settings={"AuditImagesLimit": 2})["SessionId"]
    r = rek.get_face_liveness_session_results(SessionId=sid)
    assert r["Status"] == "CREATED"
    ch = httpx.get(f"{server['url']}/liveness/sessions/{sid}/challenge").json()
    colours = ch["Colours"]
    assert colours[0] == "white" and len(colours) >= 3
    # Replay attack: the same still photo for every frame.
    still = base64.b64encode(image(BUSH1)).decode()
    up = httpx.post(f"{server['url']}/liveness/sessions/{sid}/frames", json={"Frames": [{"Colour": c, "Bytes": still} for c in colours]}, timeout=60)
    assert up.status_code == 200, up.text
    r = rek.get_face_liveness_session_results(SessionId=sid)
    assert r["Status"] == "SUCCEEDED"
    assert r["Confidence"] < 50, r  # a static photo must not pass
    assert r["ReferenceImage"]["Bytes"][:3] == b"\xff\xd8\xff"
    # Sessions are single use.
    again = httpx.post(f"{server['url']}/liveness/sessions/{sid}/frames", json={"Frames": [{"Colour": "white", "Bytes": still}]})
    assert again.status_code == 409
    with pytest.raises(rek.exceptions.SessionNotFoundException):
        rek.get_face_liveness_session_results(SessionId=str(uuid.uuid4()))


# ----------------------------------------------------------- twins/lookalikes
def test_ambiguity_guard_withholds_coin_toss(rek, collection):
    # Enrol the same real person under two different employee ids: the
    # closest thing to identical twins we can build from public data.
    rek.index_faces(CollectionId=collection, Image={"Bytes": image(BUSH1)}, ExternalImageId="TWIN-A")
    r = rek.index_faces(CollectionId=collection, Image={"Bytes": image(BUSH2)}, ExternalImageId="TWIN-B")
    assert r["ResponseMetadata"]["HTTPHeaders"].get("x-facegate-lookalike", "").startswith("TWIN-A")
    s = rek.search_faces_by_image(CollectionId=collection, Image={"Bytes": image(BUSH3)})
    assert s["FaceMatches"] == []
    assert s["ResponseMetadata"]["HTTPHeaders"]["x-facegate-decision"].startswith("ambiguous")


def test_liveness_feedback_parses_in_aws_sdk(rek, server):
    """Low-confidence sessions carry Rekognition-shaped Feedback: [{Code, Message}]."""
    import base64

    import httpx

    sid = rek.create_face_liveness_session()["SessionId"]
    colours = httpx.get(f"{server['url']}/liveness/sessions/{sid}/challenge").json()["Colours"]
    dark = cv2.imdecode(np.frombuffer(image(BUSH1), np.uint8), cv2.IMREAD_COLOR)
    rng = np.random.default_rng(0)
    frames = []
    for k, c in enumerate(colours):
        shifted = np.roll(dark, k * 2, axis=1)
        f = np.clip(shifted.astype(np.float32) * 0.18 + rng.normal(0, 1.0, shifted.shape), 0, 255).astype(np.uint8)
        frames.append({"Colour": c, "Bytes": base64.b64encode(cv2.imencode(".jpg", f)[1].tobytes()).decode()})
    assert httpx.post(f"{server['url']}/liveness/sessions/{sid}/frames", json={"Frames": frames}, timeout=60).status_code == 200
    r = rek.get_face_liveness_session_results(SessionId=sid)
    assert r["Confidence"] < 70
    assert {"Code": "LOW_LIGHTING_DETECTED", "Message": "Poor lighting conditions were detected during the liveness check."} in r["Feedback"]
    assert "LOW_LIGHTING_DETECTED" in r["ResponseMetadata"]["HTTPHeaders"]["x-facegate-liveness-feedback"]
