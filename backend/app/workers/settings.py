"""arq worker entrypoint: `arq app.workers.settings.WorkerSettings`."""

from arq import cron

from app.workers.email_poll import poll_inbox_job
from app.workers.queue import _redis_settings
from app.workers.tasks import handle_message


class WorkerSettings:
    functions = [handle_message]
    # Every 30s (:00 and :30) - within the 30-60s cadence docs/07-build-stages.md
    # calls for. poll_inbox_job itself no-ops immediately if EMAIL_ENABLED is
    # false, so running this cron unconditionally costs nothing when email
    # isn't configured.
    cron_jobs = [cron(poll_inbox_job, second={0, 30})]
    redis_settings = _redis_settings()
    max_jobs = 10
