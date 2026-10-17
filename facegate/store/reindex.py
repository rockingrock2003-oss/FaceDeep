"""Re-embed stored face crops after a recognition-model upgrade.

Because FaceGate keeps the aligned face crop (encrypted), moving to a better
model is a background job instead of asking every employee to re-enrol.
"""

from __future__ import annotations

import cv2
import numpy as np

from facegate.engine.pipeline import FaceEngine
from facegate.store.db import FaceStore


def reindex_all(engine: FaceEngine, store: FaceStore) -> dict:
    done, skipped, missing = 0, 0, []
    for cid in store.list_collections():
        for rec in store.list_faces(cid):
            if rec.model_id == store.model_id:
                skipped += 1
                continue
            crop = store.get_crop(rec.face_id)
            if crop is None:
                missing.append(rec.face_id)
                continue
            aligned = cv2.imdecode(np.frombuffer(crop, np.uint8), cv2.IMREAD_COLOR)
            store.replace_embedding(rec.face_id, engine.embedder.embed(aligned))
            done += 1
    return {"Reindexed": done, "AlreadyCurrent": skipped, "MissingCrops": missing}
