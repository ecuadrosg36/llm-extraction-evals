"""Generated invoices with known answers. Every company, ID and amount is made up.

Four layouts, each with traps that real documents have:
- us:     customer tax ID printed next to the seller's; subtotal and tax before the total
- peru:   day-first dates (04/03/2026), "1.234,56" amounts, emitter and customer RUC
- mexico: no due date at all, RFC for both parties
- email:  free text that also mentions an older invoice's amount
"""

import json
import random
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

DEFAULT_SEED = 7
DOCS_PER_LAYOUT = 15
MONTHS_EN = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)
VENDORS = (
    "Andes Freight",
    "Pacifico Labs",
    "Condor Logistics",
    "Rio Verde Foods",
    "Altiplano Software",
    "Nazca Print",
    "Selva Coffee",
    "Puerto Steel",
    "Inca Solar",
    "Lima Data Works",
)
CUSTOMERS = ("Northwind Retail", "Blue Harbor Inc", "Mesa Health", "Quinoa Market", "Summit Clinics")


@dataclass(frozen=True)
class Document:
    id: str
    layout: str
    text: str
    gold: dict[str, str | None]


def _money(value: Decimal, european: bool = False) -> str:
    formatted = f"{value:,.2f}"
    return formatted.replace(",", "X").replace(".", ",").replace("X", ".") if european else formatted


def _digits(rng: random.Random, n: int) -> str:
    return "".join(str(rng.randint(0, 9)) for _ in range(n))


def _base(rng: random.Random) -> dict:
    issued = date(2026, 1, 5) + timedelta(days=rng.randint(0, 270))
    subtotal = Decimal(rng.randint(15_000, 2_500_000)) / 100
    return {
        "vendor": rng.choice(VENDORS),
        "customer": rng.choice(CUSTOMERS),
        "issued": issued,
        "due": issued + timedelta(days=rng.choice((15, 30, 45))),
        "subtotal": subtotal,
    }


def _us(rng: random.Random, i: int) -> Document:
    b = _base(rng)
    vendor, ein, number = f"{b['vendor']} LLC", f"{_digits(rng, 2)}-{_digits(rng, 7)}", f"INV-2026-{i:04d}"
    tax = (b["subtotal"] * Decimal("0.08")).quantize(Decimal("0.01"))
    total = b["subtotal"] + tax
    issued, due = b["issued"], b["due"]
    text = (
        f"INVOICE {number}\n\nBill to: {b['customer']}  EIN {_digits(rng, 2)}-{_digits(rng, 7)}\n"
        f"From: {vendor}  EIN {ein}\n"
        f"Invoice date: {MONTHS_EN[issued.month - 1]} {issued.day}, {issued.year}\n"
        f"Payment due: {MONTHS_EN[due.month - 1]} {due.day}, {due.year}\n\n"
        f"Subtotal: ${_money(b['subtotal'])}\nSales tax (8%): ${_money(tax)}\nTotal due: ${_money(total)}\n"
    )
    gold = {
        "vendor_name": vendor,
        "vendor_tax_id": ein,
        "invoice_number": number,
        "issue_date": issued.isoformat(),
        "due_date": due.isoformat(),
        "currency": "USD",
        "total_amount": f"{total:.2f}",
    }
    return Document(f"us-{i:02d}", "us", text, gold)


def _peru(rng: random.Random, i: int) -> Document:
    b = _base(rng)
    vendor, ruc, number = f"{b['vendor']} S.A.C.", f"20{_digits(rng, 9)}", f"F001-{rng.randint(100, 99999):08d}"
    igv = (b["subtotal"] * Decimal("0.18")).quantize(Decimal("0.01"))
    total = b["subtotal"] + igv
    issued, due = b["issued"], b["due"]
    text = (
        f"{vendor.upper()}\nRUC {ruc}\nFACTURA ELECTRÓNICA {number}\n\n"
        f"Cliente: {b['customer']} - RUC 20{_digits(rng, 9)}\n"
        f"Fecha de emisión: {issued:%d/%m/%Y}\nFecha de vencimiento: {due:%d/%m/%Y}\nMoneda: SOLES\n\n"
        f"Op. gravada: S/ {_money(b['subtotal'], european=True)}\nIGV 18%: S/ {_money(igv, european=True)}\n"
        f"Importe total: S/ {_money(total, european=True)}\n"
    )
    gold = {
        "vendor_name": vendor,
        "vendor_tax_id": ruc,
        "invoice_number": number,
        "issue_date": issued.isoformat(),
        "due_date": due.isoformat(),
        "currency": "PEN",
        "total_amount": f"{total:.2f}",
    }
    return Document(f"pe-{i:02d}", "peru", text, gold)


def _mexico(rng: random.Random, i: int) -> Document:
    b = _base(rng)
    vendor, rfc, number = (
        f"{b['vendor']} S.A. de C.V.",
        f"{b['vendor'][:3].upper()}{_digits(rng, 6)}A1B",
        f"A-{rng.randint(1000, 9999)}",
    )
    total = (b["subtotal"] * Decimal("1.16")).quantize(Decimal("0.01"))
    text = (
        f"CFDI - Factura\nFolio: {number}\nFecha: {b['issued'].isoformat()}\n"
        f"Emisor: {vendor}  RFC: {rfc}\nReceptor: {b['customer']}  RFC: XAXX010101000\n"
        f"Forma de pago: Pago en una sola exhibición\n\nTotal: MXN {_money(total)}\n"
    )
    gold = {
        "vendor_name": vendor,
        "vendor_tax_id": rfc,
        "invoice_number": number,
        "issue_date": b["issued"].isoformat(),
        "due_date": None,
        "currency": "MXN",
        "total_amount": f"{total:.2f}",
    }
    return Document(f"mx-{i:02d}", "mexico", text, gold)


def _email(rng: random.Random, i: int) -> Document:
    b = _base(rng)
    vendor, nit, number = (
        f"{b['vendor']} S.A.S.",
        f"900.{_digits(rng, 3)}.{_digits(rng, 3)}-{rng.randint(0, 9)}",
        str(rng.randint(1000, 9999)),
    )
    total = (b["subtotal"] * 1000).quantize(Decimal("1"))
    older = (total * Decimal("0.6")).quantize(Decimal("1"))
    issued, due = b["issued"], b["due"]
    text = (
        f"Hi team,\n\nLast month you paid COP {_money(older, european=True)[:-3]} for the previous order, thanks!\n"
        f"Please find our invoice no. {number} from {vendor} (NIT {nit}) dated "
        f"{issued.day} {MONTHS_EN[issued.month - 1][:3]} {issued.year}.\n"
        f"The amount of COP {_money(total, european=True)[:-3]} is payable by {due.isoformat()}.\n\nBest,\nAccounts\n"
    )
    gold = {
        "vendor_name": vendor,
        "vendor_tax_id": nit,
        "invoice_number": number,
        "issue_date": issued.isoformat(),
        "due_date": due.isoformat(),
        "currency": "COP",
        "total_amount": f"{total:.2f}",
    }
    return Document(f"em-{i:02d}", "email", text, gold)


LAYOUTS: tuple[Callable[[random.Random, int], Document], ...] = (_us, _peru, _mexico, _email)


def generate(seed: int = DEFAULT_SEED, per_layout: int = DOCS_PER_LAYOUT) -> list[Document]:
    rng = random.Random(seed)
    return [layout(rng, i) for layout in LAYOUTS for i in range(1, per_layout + 1)]


def save(documents: list[Document], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as out:
        for doc in documents:
            out.write(
                json.dumps({"id": doc.id, "layout": doc.layout, "text": doc.text, "gold": doc.gold}, ensure_ascii=False)
                + "\n"
            )


def load(path: Path) -> list[Document]:
    with path.open(encoding="utf-8") as f:
        return [Document(**json.loads(line)) for line in f if line.strip()]
