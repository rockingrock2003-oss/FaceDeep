import asyncio
import logging
import time

import cv2
import numpy as np

from app.core.config import settings
from app.services.liveness.layer1 import Layer1TextureAnalysis
from app.services.liveness.layer2 import Layer2DeepContext
from app.services.liveness.layer3 import Layer3IntegrityCheck

logger = logging.getLogger("facedeep.liveness")


def _to_native(obj):
    if isinstance(obj, dict):
        return {k: _to_native(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_native(v) for v in obj]
    if isinstance(obj, np.floating):
        return float(obj)
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    return obj


class LivenessDetector:
    def __init__(self):
        self.min_score = settings.LIVENESS_MIN_SCORE
        self._layer1 = Layer1TextureAnalysis()
        self._layer2 = Layer2DeepContext()
        self._layer3 = Layer3IntegrityCheck()

    def check_liveness_sync(
        self,
        image_bytes: bytes,
        signature: str | None = None,
        timestamp: str | None = None,
    ) -> dict:
        t0 = time.time()

        nparr = np.frombuffer(image_bytes, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if frame is None:
            return _to_native({
                "status": "error",
                "liveness_score": 0,
                "label": "error",
                "message": "Could not decode image",
                "components": {},
            })

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        layers = {}
        final_status = "passed"
        final_label = "live"
        final_message = "All liveness layers passed"
        stopped_at = None

        logger.info("Liveness Layer 1: texture analysis")
        layer1_result = self._layer1.analyze(frame, gray)
        layers["layer1"] = layer1_result
        s1 = layer1_result["score"]
        p1 = layer1_result["passed"]
        logger.info("Layer 1: score=%s, passed=%s", s1, p1)

        if not layer1_result["passed"]:
            final_status = "failed"
            final_label = "not_live"
            final_message = layer1_result["message"]
            stopped_at = "layer1"
        else:
            logger.info("Liveness Layer 2: deep context analysis")
            layer2_result = self._layer2.analyze(frame, gray)
            layers["layer2"] = layer2_result
            s2 = layer2_result["score"]
            p2 = layer2_result["passed"]
            logger.info("Layer 2: score=%s, passed=%s", s2, p2)

            if not layer2_result["passed"]:
                final_status = "failed"
                final_label = "not_live"
                final_message = layer2_result["message"]
                stopped_at = "layer2"
            else:
                logger.info("Liveness Layer 3: software integrity check")
                layer3_result = self._layer3.analyze(frame, gray, image_bytes, signature, timestamp)
                layers["layer3"] = layer3_result
                s3 = layer3_result["score"]
                p3 = layer3_result["passed"]
                logger.info("Layer 3: score=%s, passed=%s", s3, p3)

                if not layer3_result["passed"]:
                    final_status = "failed"
                    final_label = "tampered"
                    final_message = layer3_result["message"]
                    stopped_at = "layer3"

        if final_status == "passed":
            scores = [layers[f"layer{i}"]["score"] for i in [1, 2, 3] if f"layer{i}" in layers]
            liveness_score = min(scores) if scores else 0
        else:
            failed_layer = layers.get(stopped_at, {})
            liveness_score = failed_layer.get("score", 0)

        elapsed_ms = round((time.time() - t0) * 1000)

        return _to_native({
            "status": final_status,
            "liveness_score": round(liveness_score, 1),
            "label": final_label,
            "message": final_message,
            "components": {
                "layers": layers,
                "elapsed_ms": elapsed_ms,
                "stopped_at": stopped_at,
            },
        })

    async def check_liveness(
        self,
        image_bytes: bytes,
        signature: str | None = None,
        timestamp: str | None = None,
    ) -> dict:
        return await asyncio.to_thread(self.check_liveness_sync, image_bytes, signature, timestamp)
