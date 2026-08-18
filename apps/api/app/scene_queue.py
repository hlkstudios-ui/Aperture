import redis

from app.config import get_settings

SCENE_QUEUE = "aperture:scene-enrichment"


def enqueue_scene_job(job_id: str) -> None:
    client = redis.from_url(get_settings().redis_url)
    try:
        client.lpush(SCENE_QUEUE, job_id)
    finally:
        client.close()
