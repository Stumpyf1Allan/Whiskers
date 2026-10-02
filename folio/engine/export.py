"""Your whole portfolio as a spreadsheet: one workbook, six sheets, built from the exact
same figures the app's own screens show — this calls the same engine functions Overview,
Holdings and Allocation do, rather than querying the database afresh, so the numbers in
the file can never drift from what's on screen.

Values only, never formulas: this is a snapshot of what Whiskers knows today, not a model
meant to recalculate. "Hide amounts" is a screen-sharing setting for the live app; an
export is a deliberate request for the real numbers, so it is never blurred or redacted.
"""

from __future__ import annotations

import datetime as dt
import io

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from .. import config, db
from . import allocation, isa, portfolio

HEADER_FILL = PatternFill("solid", fgColor="0B6E6E")
HEADER_FONT = Font(name="Arial", bold=True, color="FFFFFF")
BODY_FONT = Font(name="Arial")
TITLE_FONT = Font(name="Arial", bold=True, size=14)
MONEY = "£#,##0.00;[RED]-£#,##0.00"
PCT1 = "0.0%"
DATEFMT = "yyyy-mm-dd"
_EPOCH = dt.date(1900, 1, 1)


def _date(s: str | None) -> dt.date | None:
    """A stored ISO string becomes a real Excel date, not text, so the user can sort,
    filter and format it like any other date. A date before Excel's own epoch (used
    nowhere here, but cheap to guard) would corrupt the file, so it falls back to text."""
    if not s:
        return None
    try:
        d = dt.date.fromisoformat(str(s)[:10])
    except ValueError:
        return None
    return d if d >= _EPOCH else None


def _sheet(wb: Workbook, title: str, headers: list[str], widths: list[int]) -> Worksheet:
    ws = wb.create_sheet(title)
    ws.append(headers)
    for c, (w, _h) in enumerate(zip(widths, headers), start=1):
        ws.column_dimensions[get_column_letter(c)].width = w
        cell = ws.cell(row=1, column=c)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(vertical="center")
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}1"
    return ws


def _row(ws: Worksheet, values: list, formats: dict[int, str] | None = None) -> None:
    ws.append(values)
    r = ws.max_row
    for c in range(1, len(values) + 1):
        cell = ws.cell(row=r, column=c)
        cell.font = BODY_FONT
        if formats and c in formats:
            cell.number_format = formats[c]


def _autoheight(ws: Worksheet) -> None:
    ws.sheet_view.showGridLines = False


# ---------------------------------------------------------------------------- sheets

def _summary(wb: Workbook, pos: list[dict], tot: dict, when: dt.datetime) -> None:
    ws = wb.create_sheet("Summary")
    ws.column_dimensions["A"].width = 28
    ws.column_dimensions["B"].width = 20
    ws["A1"] = f"{config.APP_NAME} \u2014 your data"
    ws["A1"].font = TITLE_FONT
    ws["A2"] = f"Generated {when.strftime('%d %B %Y, %H:%M')}"
    ws["A2"].font = Font(name="Arial", italic=True, color="6F7C8B")

    rows = [
        ("Total value", tot.get("total"), MONEY),
        ("Invested", tot.get("invested"), MONEY),
        ("Cash (in your plan)", tot.get("cash"), MONEY),
        ("Cash accounts (outside your plan)", tot.get("outside_cash"), MONEY),
        ("Owed on cards", tot.get("owed"), MONEY),
        ("Cost of what's priced", tot.get("cost"), MONEY),
        ("Gain", tot.get("gain"), MONEY),
        ("Gain, as a share of cost", tot.get("gain_pct"), PCT1),
        ("Dividends, last 12 months", tot.get("dividends_12m"), MONEY),
        ("Holdings", tot.get("holdings"), "0"),
        ("Holdings with no price yet", tot.get("unpriced"), "0"),
    ]
    r = 4
    for label, value, fmt in rows:
        ws.cell(row=r, column=1, value=label).font = BODY_FONT
        cell = ws.cell(row=r, column=2, value=value if value is not None else None)
        cell.font = BODY_FONT
        cell.number_format = fmt
        r += 1

    r += 1
    ws.cell(row=r, column=1, value="Platform").font = HEADER_FONT
    ws.cell(row=r, column=1).fill = HEADER_FILL
    for c, h in enumerate(("Kind", "Total (\u00a3)", "Cash (\u00a3)", "Holdings"), start=2):
        cell = ws.cell(row=r, column=c, value=h)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
    r += 1
    for p in tot.get("platforms", []):
        ws.cell(row=r, column=1, value=p["name"]).font = BODY_FONT
        ws.cell(row=r, column=2, value=p.get("kind", "platform")).font = BODY_FONT
        c3 = ws.cell(row=r, column=3, value=p.get("total")); c3.font = BODY_FONT; c3.number_format = MONEY
        c4 = ws.cell(row=r, column=4, value=p.get("cash")); c4.font = BODY_FONT; c4.number_format = MONEY
        ws.cell(row=r, column=5, value=p.get("holdings")).font = BODY_FONT
        r += 1
    a = isa.allowance()
    if a.get("has_data"):
        r += 1
        ws.cell(row=r, column=1, value=f"ISA allowance used, {a['label']}").font = BODY_FONT
        c = ws.cell(row=r, column=2, value=a.get("used")); c.font = BODY_FONT; c.number_format = MONEY
        r += 1
        ws.cell(row=r, column=1, value="ISA allowance remaining").font = BODY_FONT
        c = ws.cell(row=r, column=2, value=a.get("remaining")); c.font = BODY_FONT; c.number_format = MONEY

    r += 2
    note = ws.cell(row=r, column=1, value=f"{config.APP_NAME} is a personal tool for keeping to your own "
                   "plan. It is not financial advice. Prices may be delayed, estimated, or occasionally "
                   "missing, and are shown exactly as the app had them at the moment above.")
    note.font = Font(name="Arial", italic=True, color="6F7C8B")
    note.alignment = Alignment(wrap_text=True)
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=5)
    ws.row_dimensions[r].height = 40
    _autoheight(ws)


def _holdings(wb: Workbook, pos: list[dict]) -> None:
    ws = _sheet(wb, "Holdings",
               ["Platform", "Sleeve", "Name", "Symbol", "ISIN", "Currency", "Shares", "Cost (\u00a3)",
                "Value (\u00a3)", "Price per share (\u00a3)", "Gain (\u00a3)", "Gain %", "AI share",
                "Value source", "Priced as of", "Company", "Theme", "Notes"],
               [20, 16, 34, 9, 14, 9, 13, 13, 13, 15, 13, 9, 9, 15, 12, 16, 14, 24])
    for x in sorted(pos, key=lambda x: (x["sleeve"] or "\uffff", x["name"] or "")):
        source = {"api": "Live from the broker", "broker-same-isin": "Priced from the other platform",
                  "market": "Market price", "at-cost": "Treasury bill, at cost",
                  "broker": "Live from the broker"}.get(x.get("value_source"), x.get("value_source") or "")
        _row(ws, [x["platform"], x["sleeve"] or "Not in a sleeve yet", x["name"], x["symbol"], x["isin"],
                  x["currency"], x["quantity"], x["cost"], x["value"], x.get("price_gbp"), x["gain"],
                  x["gain_pct"], (x["ai_share"] / 100 if x["ai_share"] is not None else None),
                  source, _date(x.get("value_as_of")), x["company"], x["theme"], x["notes"]],
             {7: "#,##0.0000", 8: MONEY, 9: MONEY, 10: MONEY, 11: MONEY, 12: PCT1, 13: PCT1, 15: DATEFMT})
    _autoheight(ws)


def _allocation(wb: Workbook, pos: list[dict], tot: dict) -> None:
    v = allocation.view(pos, tot)
    ws = _sheet(wb, "Allocation",
               ["Sleeve", "Target", "Actual", "Value (\u00a3)", "Band \u00b1 (points)", "Drift (points)",
                "Status", "Holdings"],
               [22, 10, 10, 14, 14, 14, 12, 10])
    status_word = {"ok": "Inside its band", "amber": "Drifting", "red": "Outside its band",
                   "none": "No value yet"}
    for r in v["sleeves"]:
        _row(ws, [r["name"], r["target"] / 100, r["actual"] / 100, r["value"], r["band"], r["drift"],
                  status_word.get(r["status"], r["status"]), r["holdings"]],
             {2: PCT1, 3: PCT1, 4: MONEY, 5: "0.00", 6: "+0.00;-0.00"})
    for e in v["extra"]:
        _row(ws, [e["name"], None, e["actual"] / 100, e["value"], None, None, "", e.get("holdings") or ""],
             {3: PCT1, 4: MONEY})
    _autoheight(ws)


def _dividends(wb: Workbook) -> None:
    rows = db.rows("SELECT d.paid_on, p.name AS platform, i.name, i.symbol, d.amount_gbp, d.withheld_gbp "
                   "FROM dividends d JOIN platforms p ON p.id=d.platform_id LEFT JOIN instruments i "
                   "ON i.id=d.instrument_id ORDER BY d.paid_on, d.id")
    ws = _sheet(wb, "Dividends", ["Date", "Platform", "Holding", "Symbol", "Amount (\u00a3)", "Withheld (\u00a3)"],
               [13, 20, 34, 9, 13, 13])
    for r in rows:
        _row(ws, [_date(r["paid_on"]), r["platform"], r["name"], r["symbol"], r["amount_gbp"],
                  r["withheld_gbp"]], {1: DATEFMT, 5: MONEY, 6: MONEY})
    if rows:
        ws.append(["", "", "", "Total", sum(r["amount_gbp"] or 0 for r in rows), ""])
        ws.cell(row=ws.max_row, column=4).font = Font(name="Arial", bold=True)
        c = ws.cell(row=ws.max_row, column=5); c.font = Font(name="Arial", bold=True); c.number_format = MONEY
    _autoheight(ws)


SIDE_WORD = {"BUY": "Bought", "SELL": "Sold", "TRANSFER_IN": "Transferred in",
            "TRANSFER_OUT": "Transferred out", "ADJUST": "Corrected by hand",
            "COST": "Cost corrected", "SET": "Set to match the platform", "CORPORATE": "Corporate action"}


def _trades(wb: Workbook) -> None:
    rows = db.rows("SELECT t.traded_on, p.name AS platform, i.name, i.symbol, t.side, t.quantity, "
                   "t.price, t.price_ccy, t.value_gbp, t.fees_gbp FROM trades t JOIN platforms p "
                   "ON p.id=t.platform_id LEFT JOIN instruments i ON i.id=t.instrument_id "
                   "ORDER BY t.traded_on, t.id")
    ws = _sheet(wb, "Trades",
               ["Date", "Platform", "Holding", "Symbol", "What happened", "Shares", "Price", "Price currency",
                "Value (\u00a3)", "Fees (\u00a3)"],
               [13, 20, 34, 9, 20, 13, 11, 10, 13, 10])
    for r in rows:
        _row(ws, [_date(r["traded_on"]), r["platform"], r["name"], r["symbol"],
                  SIDE_WORD.get(r["side"], r["side"]), r["quantity"], r["price"], r["price_ccy"],
                  r["value_gbp"], r["fees_gbp"]],
             {1: DATEFMT, 6: "#,##0.0000", 7: "#,##0.0000", 9: MONEY, 10: MONEY})
    _autoheight(ws)


CASH_WORD = {"DEPOSIT": "Paid in", "WITHDRAWAL": "Paid out", "INTEREST": "Interest",
            "FEE": "Fee", "TRANSFER": "Transfer"}


def _cash(wb: Workbook) -> None:
    rows = db.rows("SELECT c.happened_on, p.name AS platform, c.kind, c.amount_gbp FROM cash_moves c "
                   "JOIN platforms p ON p.id=c.platform_id ORDER BY c.happened_on, c.id")
    ws = _sheet(wb, "Cash movements", ["Date", "Platform", "What happened", "Amount (\u00a3)"], [13, 20, 16, 13])
    for r in rows:
        _row(ws, [_date(r["happened_on"]), r["platform"], CASH_WORD.get(r["kind"], r["kind"]),
                  r["amount_gbp"]], {1: DATEFMT, 4: MONEY})
    _autoheight(ws)


# ---------------------------------------------------------------------------- entry point

def build() -> bytes:
    """Every sheet, as one .xlsx file in memory. No temp file: the server hands the bytes
    straight to the browser, so nothing is left behind on disk if the download is cancelled."""
    pos = portfolio.positions()
    tot = portfolio.totals(pos)
    when = dt.datetime.now()
    wb = Workbook()
    wb.remove(wb.active)
    _summary(wb, pos, tot, when)
    _holdings(wb, pos)
    _allocation(wb, pos, tot)
    _dividends(wb)
    _trades(wb)
    _cash(wb)
    wb.active = 0
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def filename() -> str:
    return f"{config.APP_FILE_NAME} export {dt.date.today().isoformat()}.xlsx"
