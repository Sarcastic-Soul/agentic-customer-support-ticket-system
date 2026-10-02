from datetime import date, timedelta
from decimal import Decimal

from pydantic import BaseModel, Field
from sqlalchemy import select

from app.models import Order, Refund, Transaction
from app.policy.authorize import Decision, authorize_refund
from app.tools.context import ToolContext
from app.tools.orders import OrderNumberArgs, get_order_scoped
from app.tools.registry import register_tool

FAILURE_EXPLANATIONS = {
    "insufficient_funds": "The card/account did not have enough balance to complete the payment.",
    "card_declined": "The issuing bank declined the transaction.",
    "gateway_timeout": "The payment gateway timed out before confirming the transaction.",
}


async def _get_txn_scoped(ctx: ToolContext, txn_ref: str) -> Transaction | None:
    result = await ctx.session.execute(
        select(Transaction).where(
            Transaction.txn_ref == txn_ref, Transaction.customer_id == ctx.customer_id
        )
    )
    return result.scalar_one_or_none()


async def _has_matching_failed_or_duplicate(ctx: ToolContext, txn: Transaction) -> bool:
    """A refund only auto-approves against a *fault* - a failed payment that
    still shows a charge on the customer's end, or a genuine duplicate
    capture. Never against "the customer just wants their money back".
    """
    if txn.order_id is None:
        return False
    siblings = (
        await ctx.session.execute(
            select(Transaction).where(
                Transaction.order_id == txn.order_id, Transaction.id != txn.id
            )
        )
    ).scalars().all()
    if any(s.status == "failed" for s in siblings):
        return True
    captured_payments = [
        s for s in siblings if s.type == "payment" and s.status == "captured"
    ] + ([txn] if txn.type == "payment" and txn.status == "captured" else [])
    return len(captured_payments) > 1


class TxnRefArgs(BaseModel):
    txn_ref: str = Field(description="Transaction reference, e.g. 'TXN-88213'")


class RequestRefundArgs(BaseModel):
    txn_ref: str
    amount: Decimal = Field(description="Amount to refund")
    reason: str


@register_tool(
    "get_transaction", "Get detail for one of the customer's own transactions.", TxnRefArgs
)
async def get_transaction(ctx: ToolContext, txn_ref: str) -> dict:
    txn = await _get_txn_scoped(ctx, txn_ref)
    if txn is None:
        return {"error": "transaction_not_found"}
    return {
        "txn_ref": txn.txn_ref,
        "type": txn.type,
        "method": txn.method,
        "amount": str(txn.amount),
        "currency": txn.currency,
        "status": txn.status,
        "failure_code": txn.failure_code,
        "created_at": txn.created_at.isoformat(),
    }


@register_tool(
    "list_transactions_for_order",
    "List all transactions (payments, refunds) for one of the customer's own orders.",
    OrderNumberArgs,
)
async def list_transactions_for_order(ctx: ToolContext, order_number: str) -> dict:
    order = await get_order_scoped(ctx, order_number)
    if order is None:
        return {"error": "order_not_found"}
    txns = (
        await ctx.session.execute(select(Transaction).where(Transaction.order_id == order.id))
    ).scalars().all()
    return {
        "transactions": [
            {"txn_ref": t.txn_ref, "type": t.type, "status": t.status, "amount": str(t.amount)}
            for t in txns
        ]
    }


@register_tool(
    "get_refund_status",
    "Get the status of a refund on one of the customer's own transactions.",
    TxnRefArgs,
)
async def get_refund_status(ctx: ToolContext, txn_ref: str) -> dict:
    txn = await _get_txn_scoped(ctx, txn_ref)
    if txn is None:
        return {"error": "transaction_not_found"}
    refund = (
        await ctx.session.execute(select(Refund).where(Refund.transaction_id == txn.id))
    ).scalar_one_or_none()
    if refund is None:
        return {"error": "no_refund_on_this_transaction"}
    return {
        "status": refund.status,
        "amount": str(refund.amount),
        "expected_credit_by": refund.expected_credit_by.isoformat()
        if refund.expected_credit_by
        else None,
    }


@register_tool(
    "explain_payment_failure",
    "Explain why one of the customer's own payments failed.",
    TxnRefArgs,
)
async def explain_payment_failure(ctx: ToolContext, txn_ref: str) -> dict:
    txn = await _get_txn_scoped(ctx, txn_ref)
    if txn is None:
        return {"error": "transaction_not_found"}
    if txn.status != "failed":
        return {"error": "transaction_did_not_fail", "status": txn.status}
    return {
        "failure_code": txn.failure_code,
        "explanation": FAILURE_EXPLANATIONS.get(txn.failure_code, "Unknown failure reason."),
        "amount_charged": "0.00 - failed transactions are never captured, nothing was deducted",
    }


@register_tool(
    "request_refund",
    "Request a refund on one of the customer's own transactions. Auto-approved "
    "up to the policy ceiling when there is a matching failed or duplicate "
    "charge; anything else goes to the human approval queue and the customer "
    "is told it is under review. Asking again does not change the outcome.",
    RequestRefundArgs,
    write=True,
)
async def request_refund(ctx: ToolContext, txn_ref: str, amount: Decimal, reason: str) -> dict:
    txn = await _get_txn_scoped(ctx, txn_ref)
    if txn is None:
        return {"error": "transaction_not_found"}
    order = await ctx.session.get(Order, txn.order_id) if txn.order_id else None
    order_number = order.order_number if order else None

    if amount <= 0 or amount > txn.amount:
        return {
            "denied": True, "order_number": order_number,
            "reason": f"refund amount must be above 0 and at most the payment amount {txn.amount}",
        }

    existing = (
        await ctx.session.execute(
            select(Refund).where(Refund.transaction_id == txn.id, Refund.status != "rejected")
        )
    ).scalars().first()
    if existing is not None:
        # Same customer asking twice, or two turns both deciding to refund -
        # one payment gets one refund.
        return {
            "denied": True, "order_number": order_number, "refund_id": existing.id,
            "reason": f"a refund for this payment already exists (status: {existing.status})",
        }

    has_matching = await _has_matching_failed_or_duplicate(ctx, txn)
    decision = authorize_refund(amount, has_matching)
    needs_approval = decision.decision != Decision.ALLOW or ctx.force_approval

    if ctx.propose_only:
        return {
            "proposed": True, "order_number": order_number, "needs_approval": needs_approval,
            "reason": decision.reason,
            "would": f"refund {amount} on {txn_ref}"
            + (" (sent for human approval)" if needs_approval else ""),
        }

    # authorize() still decides - the model can ask for any refund, but
    # only one inside the ceiling with a matching fault is approved here.
    # Anything else becomes a request a human approves or rejects from the
    # console's approval queue, which is far less work for them than taking
    # over the whole conversation (see docs/decisions/0007-fewer-handoffs.md).
    refund = Refund(
        transaction_id=txn.id,
        ticket_id=ctx.ticket_id or None,
        amount=amount,
        reason=reason,
        status="requested" if needs_approval else "approved",
        requested_by_type="ai",
        requested_by_id=str(ctx.run_id),
        expected_credit_by=None if needs_approval else date.today() + timedelta(days=7),
    )
    ctx.session.add(refund)
    await ctx.session.flush()
    if needs_approval:
        return {
            "pending_approval": True, "refund_id": refund.id, "order_number": order_number,
            "status": "awaiting human approval",
            "reason": decision.reason if decision.decision != Decision.ALLOW
            else "several refunds together pass the auto-approval ceiling",
        }
    return {
        "approved": True, "refund_id": refund.id, "order_number": order_number,
        "status": refund.status, "expected_credit_by": refund.expected_credit_by.isoformat(),
    }


@register_tool(
    "generate_invoice", "Get an invoice link for one of the customer's own orders.", OrderNumberArgs
)
async def generate_invoice(ctx: ToolContext, order_number: str) -> dict:
    order = await get_order_scoped(ctx, order_number)
    if order is None:
        return {"error": "order_not_found"}
    # Stub: no real invoice generation/storage in this prototype. Real
    # enough to demo the tool-calling path; not a real document.
    return {
        "invoice_url": f"https://support.example.com/invoices/{order.order_number}.pdf",
        "note": "stub link - invoice generation is not implemented in this prototype",
    }
