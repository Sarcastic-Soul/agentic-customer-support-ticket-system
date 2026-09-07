"""arq worker entrypoint: `arq app.workers.settings.WorkerSettings`."""

from app.workers.queue import _redis_settings
from app.workers.tasks import handle_message


class WorkerSettings:
    functions = [handle_message]
    redis_settings = _redis_settings()
    max_jobs = 10
