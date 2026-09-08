"""Runs the automated half of the Stage 6 demo script (docs/07-build-stages.md)
against a running `make demo` stack, via the /dev/simulate endpoints - no
real WhatsApp/tunnel needed. Steps 4-5 (claim in the console, reply, the
customer seeing the human's reply) need an actual person at the console, so
this prints instructions for those instead of trying to automate them.

Usage: python scripts/demo_scenario.py [--base-url http://localhost:8000]
Called automatically by `make demo` once the API is healthy.
"""

import argparse
import json
import sys
import time

import httpx

STEP_DIVIDER = "\n" + "=" * 72


def wait_for_health(client: httpx.Client, timeout: float = 60.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            resp = client.get("/health", timeout=3.0)
            if resp.status_code == 200 and resp.json().get("status") == "ok":
                return
        except httpx.HTTPError:
            pass
        time.sleep(1.0)
    print("API never became healthy - is `make demo` still starting up?", file=sys.stderr)
    sys.exit(1)


def simulate(client: httpx.Client, path: str, payload: dict) -> dict:
    resp = client.post(path, json=payload, timeout=30.0)
    resp.raise_for_status()
    return resp.json()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    args = parser.parse_args()

    client = httpx.Client(base_url=args.base_url)
    print("Waiting for the API to come up...")
    wait_for_health(client)

    nonce = int(time.time())

    print(STEP_DIVIDER)
    print("STEP 1 - Policy question -> AI answers with citations")
    print("Customer (web chat): \"what's your return window?\"")
    result = simulate(
        client,
        "/dev/simulate/web",
        {
            "session_id": f"demo-{nonce}-policy",
            "text": "what's your return window?",
            "external_message_id": f"demo-{nonce}-policy-1",
        },
    )
    print(f"  -> stored: {json.dumps(result)}")
    print("  Watch the worker log / http://localhost:5173/console for the AI's reply.")

    print(STEP_DIVIDER)
    print("STEP 2 - Order status question -> AI calls a tool, answers with real data")
    print(
        'Customer (WhatsApp, Ananya Gupta / ORD-10008): '
        '"is my blender order ORD-10008 coming today?"'
    )
    result = simulate(
        client,
        "/dev/simulate/whatsapp",
        {
            "phone": "+919800000005",
            "text": "is my blender order ORD-10008 coming today?",
            "external_message_id": f"demo-{nonce}-order-1",
        },
    )
    print(f"  -> stored: {json.dumps(result)}")

    print(STEP_DIVIDER)
    print("STEP 3 - Large refund request -> policy denies -> escalation appears in the console")
    print(
        'Customer (WhatsApp, Rohan Sharma / ORD-10003, duplicate charge): '
        '"I was charged twice for ORD-10003, please refund the extra 4200"'
    )
    result = simulate(
        client,
        "/dev/simulate/whatsapp",
        {
            "phone": "+919800000001",
            "text": "I was charged twice for ORD-10003, please refund the extra 4200",
            "external_message_id": f"demo-{nonce}-refund-1",
        },
    )
    print(f"  -> stored: {json.dumps(result)}")
    print(
        "  This should exceed AUTO_REFUND_CEILING and land in the escalation "
        "queue - give the worker a few seconds, then check the console."
    )

    print(STEP_DIVIDER)
    print("STEPS 4-5 - now at the keyboard:")
    print("  1. Open http://localhost:5173/login and sign in (any seeded agent,")
    print("     password: dev-password).")
    print("  2. Go to the escalation console, claim the ticket from Step 3.")
    print("  3. Read the handoff packet (summary, timeline, suggested reply),")
    print("     edit it if you like, and send.")
    print("  4. Open http://localhost:5173/chat (or check the WhatsApp simulator")
    print("     log) - the customer sees your reply in the same thread the AI was using.")
    print(STEP_DIVIDER)
    print("Demo scenario done. Services are still running - Ctrl-C to stop.")


if __name__ == "__main__":
    main()
