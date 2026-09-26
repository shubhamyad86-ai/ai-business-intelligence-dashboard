"""
reports/report_generator.py
-----------------------------
Assembles a full business snapshot (sales + customers + inventory) into a
single Markdown report. Pure data, no LLM involved — fast and deterministic,
so it's safe to call on every request without worrying about model latency.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from tools.customer_analysis import analyze_customers
from tools.inventory_analysis import analyze_inventory
from tools.sales_analysis import analyze_sales

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "reports" / "generated"


def generate_report_markdown() -> str:
    sales = analyze_sales()
    customers = analyze_customers()
    inventory = analyze_inventory()

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = [
        "# Business Snapshot Report",
        f"_Generated {now}_",
        "",
        "## Sales",
        f"- Total revenue: €{sales['total_revenue']:,.2f}",
        f"- Total orders: {sales['total_orders']}",
        f"- Top product: {sales['top_product']}",
        f"- Top country: {sales['top_country']}",
        "",
        "### Revenue by month",
    ]
    for month, rev in sorted(sales["monthly_revenue"].items()):
        lines.append(f"- {month}: €{rev:,.2f}")

    if sales["biggest_declining_product"]:
        d = sales["biggest_declining_product"]
        lines.append(f"\n**Steepest product decline:** {d['name']} ({d['change_pct']}%)")
    if sales["biggest_declining_country"]:
        d = sales["biggest_declining_country"]
        lines.append(f"**Steepest country decline:** {d['name']} ({d['change_pct']}%)")

    lines += [
        "",
        "## Customers",
        f"- Total distinct customers: {customers['total_customers']}",
        "",
        "### Top customers by revenue",
    ]
    for c in customers["top_customers"]:
        lines.append(f"- {c['customer']}: €{c['revenue']:,.2f} ({c['orders']} orders)")

    if customers["churn_candidates"]:
        lines.append(f"\n**Possible churn ({len(customers['churn_candidates'])} customers):** "
                      + ", ".join(customers["churn_candidates"]))

    lines += [
        "",
        "## Inventory",
        f"- Total inventory value: €{inventory['total_stock_value']:,.2f}",
        "",
        "### Units by product",
    ]
    for p, v in inventory["by_product"].items():
        lines.append(f"- {p}: {v} units")

    if inventory["low_stock"]:
        lines.append("\n### ⚠ Below reorder threshold")
        for item in inventory["low_stock"]:
            lines.append(
                f"- {item['product']} at {item['warehouse']}: "
                f"{item['stock_level']}/{item['reorder_threshold']} "
                f"(short by {item['shortfall']})"
            )
    else:
        lines.append("\nAll products are above their reorder threshold.")

    return "\n".join(lines)


def save_report(filename: str = "business_report.md") -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / filename
    path.write_text(generate_report_markdown(), encoding="utf-8")
    return path


if __name__ == "__main__":
    path = save_report()
    print(f"Report written to {path}")


def generate_report_pdf_bytes() -> bytes:
    """Generate a compact PDF snapshot in memory."""
    from io import BytesIO
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, ListFlowable, ListItem
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.styles import ParagraphStyle
    buf=BytesIO(); styles=getSampleStyleSheet(); title=ParagraphStyle("title",parent=styles["Title"],alignment=TA_CENTER)
    doc=SimpleDocTemplate(buf,pagesize=A4,rightMargin=40,leftMargin=40,topMargin=40,bottomMargin=40); story=[Paragraph("AI Operations Engineer — Business Snapshot",title),Spacer(1,12)]
    for line in generate_report_markdown().splitlines():
        if not line.strip(): story.append(Spacer(1,6)); continue
        clean=line.replace("**","").replace("# ","").replace("## ","").replace("### ","").replace("_","")
        story.append(Paragraph(clean.replace("&","&amp;"),styles["BodyText"]))
    doc.build(story); return buf.getvalue()
