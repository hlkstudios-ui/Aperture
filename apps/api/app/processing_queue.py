import redis

from app.config import get_settings

PROCESSING_QUEUE = "aperture:media-processing"


def enqueue_processing_job(job_id: str) -> None:
    client = redis.from_url(get_settings().redis_url)
    try:
        client.lpush(PROCESSING_QUEUE, job_id)
    finally:
        client.close()
