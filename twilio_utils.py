"""
twilio_utils.py — Twilio WhatsApp messaging utilities.

Provides a helper function to send WhatsApp messages asynchronously
using the Twilio REST API.  Used for:
  - Sending long-running results (job search) after the webhook has responded.
  - Splitting long messages to respect WhatsApp's character limit.
"""

import logging

from twilio.rest import Client

from config import (
    MAX_WHATSAPP_MESSAGE_LENGTH,
    TWILIO_ACCOUNT_SID,
    TWILIO_AUTH_TOKEN,
    TWILIO_WHATSAPP_NUMBER,
)

logger = logging.getLogger(__name__)


def _get_twilio_client() -> Client:
    """Create and return a Twilio REST client."""
    if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
        raise ValueError(
            "Twilio credentials are not configured. "
            "Set TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN environment variables."
        )
    return Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)


def split_message(text: str, limit: int = MAX_WHATSAPP_MESSAGE_LENGTH) -> list[str]:
    """
    Split a long message into chunks that fit within WhatsApp's character limit.

    Tries to split at newline boundaries so messages stay readable.
    """
    if len(text) <= limit:
        return [text]

    chunks = []
    current_lines = []
    current_length = 0

    for line in text.splitlines(keepends=True):
        # If a single line exceeds the limit, hard-split it
        if len(line) > limit:
            if current_lines:
                chunks.append("".join(current_lines).rstrip())
                current_lines = []
                current_length = 0
            start = 0
            while start < len(line):
                chunks.append(line[start:start + limit].rstrip())
                start += limit
            continue

        # Check if adding this line would exceed the limit
        if current_length + len(line) > limit:
            chunks.append("".join(current_lines).rstrip())
            current_lines = [line]
            current_length = len(line)
        else:
            current_lines.append(line)
            current_length += len(line)

    if current_lines:
        chunks.append("".join(current_lines).rstrip())

    return chunks


def send_whatsapp_message(to: str, body: str):
    """
    Send one or more WhatsApp messages to a user via Twilio.

    Parameters:
        to   – The recipient in Twilio format, e.g. "whatsapp:+919876543210"
        body – The message text (will be auto-split if too long)

    If the message exceeds the WhatsApp character limit, it is automatically
    split into multiple messages sent in sequence.
    """
    client = _get_twilio_client()
    from_number = TWILIO_WHATSAPP_NUMBER

    if not from_number:
        raise ValueError(
            "TWILIO_WHATSAPP_NUMBER is not configured. "
            "Set it to your Twilio Sandbox number (e.g. 'whatsapp:+14155238886')."
        )

    chunks = split_message(body)

    for i, chunk in enumerate(chunks):
        try:
            message = client.messages.create(
                from_=from_number,
                to=to,
                body=chunk,
            )
            logger.info(
                "Sent WhatsApp message %d/%d to %s (SID: %s)",
                i + 1, len(chunks), to, message.sid,
            )
        except Exception as e:
            logger.error(
                "Failed to send WhatsApp message %d/%d to %s: %s",
                i + 1, len(chunks), to, e,
            )
            raise
