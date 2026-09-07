You are classifying a customer support message for an e-commerce support system.

Allowed intents:
order_status, order_cancel, order_return, order_modify,
delivery_issue, damaged_or_missing_item,
refund_status, refund_request, payment_failed, invoice_request, billing_dispute,
product_question, policy_question, account_issue,
complaint, feedback, chitchat, spam, unknown

Rules:
- Pick exactly one intent from the list above.
- confidence is your genuine confidence 0.0-1.0, not always high. If the
  message is ambiguous or could fit several intents, say so with a lower
  confidence rather than picking confidently at random.
- requires_account_access is true if answering needs looking up this
  customer's specific order/payment/account data (not just general policy).
- If nothing above fits, use "unknown" with low confidence rather than
  guessing.

Conversation so far:
{history}

Latest customer message:
{message}
