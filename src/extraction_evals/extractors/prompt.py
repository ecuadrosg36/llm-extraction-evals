"""One prompt for every LLM, so differences in scores come from the model, not the wording."""

INSTRUCTIONS = """Extract the invoice fields from the document.

For every field return:
- value: the normalized value, or null if the document does not contain it. Never guess.
- evidence: the exact text copied from the document that supports the value, or null.

Normalize values like this:
- dates as YYYY-MM-DD (Spanish documents write the day first: 04/03/2026 is 2026-03-04)
- currency as an ISO 4217 code (S/ or soles is PEN)
- total_amount as a plain number with a dot for decimals, e.g. 1416.00

The vendor is the company that issued the invoice, not the customer. Take the vendor's tax ID, not the
customer's. The total is the amount due including tax, not a subtotal and not an amount from another invoice."""


def user_message(text: str) -> str:
    return f"{INSTRUCTIONS}\n\n<document>\n{text}\n</document>"
