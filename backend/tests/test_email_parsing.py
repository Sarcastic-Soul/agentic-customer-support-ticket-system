"""The fiddly part of the email channel (docs/09-risks.md R6) - real
email.message.Message objects, not a live mailbox.
"""

from email import message_from_string
from email.policy import default as default_policy

from app.channels.email_parsing import (
    extract_plain_text,
    is_auto_reply,
    sender_email,
    strip_quoted_and_signature,
    thread_root_id,
)


def _msg(raw: str):
    return message_from_string(raw, policy=default_policy)


def test_extract_plain_text_prefers_text_plain_over_html():
    raw = (
        "Content-Type: multipart/alternative; boundary=BOUNDARY\n"
        "\n"
        "--BOUNDARY\n"
        "Content-Type: text/plain\n"
        "\n"
        "plain body\n"
        "--BOUNDARY\n"
        "Content-Type: text/html\n"
        "\n"
        "<p>html body</p>\n"
        "--BOUNDARY--\n"
    )
    assert extract_plain_text(_msg(raw)) == "plain body"


def test_extract_plain_text_falls_back_to_stripped_html():
    raw = "Content-Type: text/html\n\n<p>Hello <b>world</b></p>\n"
    assert extract_plain_text(_msg(raw)) == "Hello world"


def test_strip_quoted_reply_gmail_style():
    body = (
        "Thanks, that fixed it!\n\n"
        "On Mon, Sep 7, 2026 at 10:00 AM John wrote:\n> original question"
    )
    assert strip_quoted_and_signature(body) == "Thanks, that fixed it!"


def test_strip_quoted_reply_outlook_style():
    body = (
        "Sure, go ahead.\n\n-----Original Message-----\n"
        "From: support@example.com\nSubject: Re: order"
    )
    assert strip_quoted_and_signature(body) == "Sure, go ahead."


def test_strip_signature():
    body = "See you then.\n--\nJohn Doe\nSenior Engineer"
    assert strip_quoted_and_signature(body) == "See you then."


def test_strip_quoted_and_signature_leaves_plain_body_untouched():
    body = "Where is my order ORD-10432? It has been 9 days."
    assert strip_quoted_and_signature(body) == body


def test_thread_root_id_prefers_references_first_entry():
    raw = "Message-ID: <c@x.com>\nIn-Reply-To: <b@x.com>\nReferences: <a@x.com> <b@x.com>\n\nbody"
    assert thread_root_id(_msg(raw)) == "a@x.com"


def test_thread_root_id_falls_back_to_in_reply_to():
    raw = "Message-ID: <b@x.com>\nIn-Reply-To: <a@x.com>\n\nbody"
    assert thread_root_id(_msg(raw)) == "a@x.com"


def test_thread_root_id_uses_own_message_id_for_fresh_thread():
    raw = "Message-ID: <a@x.com>\n\nbody"
    assert thread_root_id(_msg(raw)) == "a@x.com"


def test_is_auto_reply_detects_auto_submitted_header():
    raw = "Auto-Submitted: auto-replied\n\nOut of office"
    assert is_auto_reply(_msg(raw)) is True


def test_is_auto_reply_detects_mailing_list():
    raw = "List-Id: <announce.example.com>\n\nNewsletter content"
    assert is_auto_reply(_msg(raw)) is True


def test_is_auto_reply_detects_bulk_precedence():
    raw = "Precedence: bulk\n\nContent"
    assert is_auto_reply(_msg(raw)) is True


def test_is_auto_reply_false_for_normal_message():
    raw = "From: customer@example.com\nSubject: Help\n\nWhere is my order?"
    assert is_auto_reply(_msg(raw)) is False


def test_sender_email_extracts_address_from_display_name():
    raw = "From: John Doe <john@example.com>\n\nbody"
    assert sender_email(_msg(raw)) == "john@example.com"
