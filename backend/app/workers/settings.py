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
    # arq's default (300s) isn't enough headroom on a degraded free-tier day:
    # one real ticket, live-tested during Stage 12, took over 300s across
    # classify + a multi-round tool loop + verify, each role paying Gemini's
    # 429-then-Groq-fallback dance - arq killed and retried it mid-flight.
    # MAX_TOOL_CALLS/MAX_AI_TURNS already bound the graph's own loop; this is
    # just enough operational slack that provider slowness doesn't look like
    # a hang and trigger a redundant retry (and a second AgentRun) on top of
    # a run that would have finished on its own.
    job_timeout = 900
