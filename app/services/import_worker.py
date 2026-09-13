import asyncio
import json
import uuid
from datetime import UTC, datetime

import cv2
import httpx
import numpy as np
from sqlalchemy import select

from app.models.import_job import ImportJob
from app.services.embedding_store import EmbeddingStore
from app.services.face_recognition import get_face_service

embedding_store = EmbeddingStore()


async def process_import_job(
    job_id: str,
    user_id: str,
    person_id: str,
    image_urls: list[str],
):
    """Background worker that processes import jobs in batches."""
    from app.db import AsyncSessionLocal

    face_service = get_face_service()
    batch_size = 10
    success = 0
    failed = 0
    errors = []

    async with AsyncSessionLocal() as db:
        stmt = select(ImportJob).where(ImportJob.id == job_id)
        result = await db.execute(stmt)
        job = result.scalar_one_or_none()
        if not job:
            return

        job.status = "processing"
        job.total = len(image_urls)
        await db.commit()

        async with httpx.AsyncClient(timeout=30) as client:
            for i in range(0, len(image_urls), batch_size):
                batch = image_urls[i:i + batch_size]

                for url in batch:
                    face_id = str(uuid.uuid4())
                    try:
                        resp = await client.get(url)
                        if resp.status_code != 200:
                            failed += 1
                            errors.append(f"{url}: HTTP {resp.status_code}")
                            job.processed += 1
                            continue

                        image_bytes = resp.content
                        if len(image_bytes) > 10 * 1024 * 1024:
                            failed += 1
                            errors.append(f"{url}: Too large")
                            job.processed += 1
                            continue

                        img = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
                        if img is None:
                            failed += 1
                            errors.append(f"{url}: Invalid image")
                            job.processed += 1
                            continue

                        embedding, face_info = await face_service.extract_embedding(image_bytes)

                        embedding_store.add_embedding(
                            user_id=user_id,
                            face_id=face_id,
                            embedding=embedding,
                            person_id=person_id,
                        )

                        success += 1
                        job.processed += 1
                        job.success = success
                        job.failed = failed

                    except Exception as e:
                        failed += 1
                        errors.append(f"{url}: {str(e)}")
                        job.processed += 1

                await db.commit()
                await asyncio.sleep(0.1)

        job.status = "completed"
        job.completed_at = datetime.now(UTC)
        job.errors = json.dumps(errors[:100]) if errors else None
        await db.commit()
