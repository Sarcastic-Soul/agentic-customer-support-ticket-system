from app.api.admin import KBDocumentCreate, KBDocumentUpdate, create_kb_document, update_kb_document
from app.models import HumanAgent


async def _make_admin(session, tag: str) -> HumanAgent:
    agent = HumanAgent(
        email=f"admin-{tag}@example.com", full_name="Test Admin",
        password_hash="x", role="admin",
    )
    session.add(agent)
    await session.flush()
    return agent


async def test_create_kb_document_returns_populated_updated_at(session):
    """Regression: KBDocument.updated_at has onupdate=func.now(), which
    SQLAlchemy expires on flush independent of expire_on_commit. Accessing
    it right after session.commit() without a refresh raised MissingGreenlet
    - found live via the admin dashboard's KB editor.
    """
    agent = await _make_admin(session, "create")
    doc = await create_kb_document(
        KBDocumentCreate(title="Test KB Doc", body="Some body text."),
        agent=agent, session=session,
    )
    assert doc.updated_at is not None


async def test_update_kb_document_body_change_refreshes_updated_at(session):
    agent = await _make_admin(session, "update")
    created = await create_kb_document(
        KBDocumentCreate(title="Test KB Doc", body="Original body."),
        agent=agent, session=session,
    )

    # session.commit() inside create_kb_document expires all objects in this
    # test session (unlike prod's expire_on_commit=False factory), so `agent`
    # needs a refresh before reuse - real requests never hit this since each
    # gets a freshly-fetched agent via require_admin.
    await session.refresh(agent)

    updated = await update_kb_document(
        created.id, KBDocumentUpdate(body="Changed body."), agent=agent, session=session,
    )

    assert updated.version == 2
    assert updated.body == "Changed body."
    assert updated.updated_at is not None
