from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# .env lives at the repo root (one .env for docker compose and the backend
# alike), not in backend/ - resolve it relative to this file, not cwd, so it
# is found the same way whether run from repo root, backend/, or alembic.
_REPO_ROOT_ENV = Path(__file__).resolve().parents[2] / ".env"

# pydantic-settings' env_file loads values into the Settings object only -
# it does not export them to os.environ. A few things (LangGraph's
# LANGGRAPH_STRICT_MSGPACK, read via os.getenv at import time) need a real
# process env var, so load .env into the process too. Safe to call more than
# once; load_dotenv never overrides a variable the shell already set.
load_dotenv(_REPO_ROOT_ENV)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_REPO_ROOT_ENV, extra="ignore")

    env: str = "dev"
    log_level: str = "INFO"
    secret_key: str = "change-me"
    public_base_url: str = "http://localhost:8000"

    # database
    database_url: str = "postgresql+asyncpg://support:support@localhost:5432/support"
    checkpoint_database_url: str = "postgresql://support:support@localhost:5432/support"
    langgraph_strict_msgpack: bool = True
    db_pool_size: int = 5
    checkpoint_pool_size: int = 5

    # redis
    redis_url: str = "redis://localhost:6379/0"

    # llm
    llm_provider: str = "stub"  # gemini | groq | stub
    llm_fallback_provider: str = "groq"
    gemini_api_key: str = ""
    groq_api_key: str = ""

    model_classify: str = "gemini-3.5-flash-lite"
    model_reason: str = "gemini-3.8-flash"
    model_verify: str = "gemini-3.5-flash-lite"
    model_summarize: str = "gemini-3.8-flash"
    fallback_model_classify: str = "openai/gpt-oss-20b"
    fallback_model_reason: str = "openai/gpt-oss-120b"
    judge_model: str = "openai/gpt-oss-120b"

    llm_timeout_seconds: int = 30
    llm_max_retries: int = 3

    # embeddings
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dim: int = 384

    # retrieval
    retrieval_top_k_dense: int = 20
    retrieval_top_k_sparse: int = 20
    retrieval_final_k: int = 5
    retrieval_score_min: float = 0.55
    reranker_enabled: bool = False

    # agent policy
    intent_confidence_min: float = 0.60
    max_ai_turns: int = 4
    max_tool_calls: int = 5
    auto_refund_ceiling: float = 1000.00
    auto_cancel_max_age_hours: int = 24
    conversation_idle_hours: int = 24

    # whatsapp
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_whatsapp_from: str = "whatsapp:+14155238886"
    twilio_validate_signature: bool = True

    # email
    email_enabled: bool = False
    imap_host: str = "imap.gmail.com"
    imap_port: int = 993
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    support_email: str = ""
    support_email_app_password: str = ""
    email_poll_seconds: int = 45

    # voice
    voice_enabled: bool = False
    stt_primary: str = "nvidia/parakeet-tdt-0.6b-v3"
    stt_fallback: str = "distil-large-v3"
    stt_api_fallback: str = "whisper-large-v3"
    tts_voice: str = "en_US-amy-medium"

    # demo
    demo_mode: str = "live"  # live | replay

    # eval ablations (Stage 11) - None in production; the eval harness sets
    # this per run to knock out one piece of the pipeline at a time.
    eval_ablation: str | None = None  # no_rag | no_verify | dense_only | all_tools


settings = Settings()
