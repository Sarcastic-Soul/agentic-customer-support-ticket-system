"""EmailAdapter.send() needs a DB lookup for both the recipient address and
threading headers (see its docstring - a real bug was found live where the
thread-root Message-ID was used as the To: address instead of a real email
lookup). Tested against the real session fixture for the lookup logic; the
SMTP call itself is mocked, no real mailbox needed.
"""

from unittest.mock import patch

from app.channels.base import OutboundMessage
from app.channels.email import EmailAdapter
from app.models import Conversation, Customer, CustomerIdentity, Message, Ticket


async def _make_thread(session, *, thread_id: str, subject: str | None) -> Conversation:
    identity_email = f"{thread_id.replace('@', '-at-')}@example.com"
    customer = Customer(full_name="Test Customer")  # deliberately no Customer.email set -
    session.add(customer)  # the recipient must come from CustomerIdentity, not this column
    await session.flush()

    session.add(
        CustomerIdentity(customer_id=customer.id, channel="email", external_id=identity_email)
    )

    conversation = Conversation(
        customer_id=customer.id, channel="email", external_thread_id=thread_id
    )
    session.add(conversation)
    await session.flush()

    ticket = Ticket(
        reference=f"T-EMAIL-{customer.id}", customer_id=customer.id,
        conversation_id=conversation.id, channel="email", subject=subject,
    )
    session.add(ticket)

    session.add(
        Message(
            conversation_id=conversation.id, role="customer", body="help please",
            channel="email", direction="inbound", external_message_id=f"{thread_id}-msg1",
        )
    )
    await session.flush()
    return conversation


async def test_send_uses_customer_identity_as_recipient_not_thread_id(session):
    # The real bug: external_thread_id is a Message-ID, not an address.
    conversation = await _make_thread(
        session, thread_id="thread-1-msgid@mail.example.com", subject="Order ORD-10432 missing"
    )

    with patch("app.channels.email.async_session_factory") as mock_factory:
        mock_factory.return_value.__aenter__.return_value = session
        adapter = EmailAdapter()
        with patch.object(adapter, "_send_sync") as mock_send:
            await adapter.send(
                OutboundMessage(
                    channel="email",
                    external_thread_id=conversation.external_thread_id,
                    text="Your order is on its way.",
                )
            )

    sent_msg = mock_send.call_args.args[0]
    assert sent_msg["To"] == "thread-1-msgid-at-mail.example.com@example.com"
    assert sent_msg["To"] != conversation.external_thread_id
    assert sent_msg["Subject"] == "Re: Order ORD-10432 missing"
    assert sent_msg["In-Reply-To"] == "<thread-1-msgid@mail.example.com-msg1>"


async def test_send_fails_gracefully_with_no_recipient_on_file(session):
    with patch("app.channels.email.async_session_factory") as mock_factory:
        mock_factory.return_value.__aenter__.return_value = session
        adapter = EmailAdapter()
        with patch.object(adapter, "_send_sync") as mock_send:
            receipt = await adapter.send(
                OutboundMessage(
                    channel="email", external_thread_id="never-seen-thread", text="hi"
                )
            )

    assert receipt.ok is False
    mock_send.assert_not_called()


async def test_send_does_not_double_prefix_re_subject(session):
    await _make_thread(session, thread_id="thread-2", subject="Re: already prefixed")

    with patch("app.channels.email.async_session_factory") as mock_factory:
        mock_factory.return_value.__aenter__.return_value = session
        adapter = EmailAdapter()
        with patch.object(adapter, "_send_sync"):
            await adapter.send(
                OutboundMessage(channel="email", external_thread_id="thread-2", text="hi")
            )
            sent_msg = adapter._send_sync.call_args.args[0]

    assert sent_msg["Subject"] == "Re: already prefixed"


async def test_send_failure_is_caught_and_returns_not_ok():
    adapter = EmailAdapter()
    with patch.object(
        adapter, "_reply_context", return_value=("customer@example.com", None, "Subject")
    ):
        with patch.object(adapter, "_send_sync", side_effect=RuntimeError("SMTP down")):
            receipt = await adapter.send(
                OutboundMessage(channel="email", external_thread_id="x", text="hi")
            )

    assert receipt.ok is False


async def test_send_success_returns_message_id():
    adapter = EmailAdapter()

    def fake_send_sync(msg):
        msg["Message-ID"] = "<generated-id@example.com>"

    with patch.object(
        adapter, "_reply_context", return_value=("customer@example.com", None, "Subject")
    ):
        with patch.object(adapter, "_send_sync", side_effect=fake_send_sync):
            receipt = await adapter.send(
                OutboundMessage(channel="email", external_thread_id="x", text="hi")
            )

    assert receipt.ok is True
    assert receipt.detail == "generated-id@example.com"
