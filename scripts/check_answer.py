"""Answer key: Q3 2026 refund rate computed three ways vs the 2026 target.

Usage:
    python scripts/check_answer.py
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "brightcart.db"
TARGET = 3.0  # 2026 target: refund rate below 3.0% (docs/reports/q3_2026_business_review.md)
Q3 = "o.order_ts >= '2026-07-01' AND o.order_ts < '2026-10-01'"

METHODS = [
    (
        "Correct (order-based, excl. test accounts, excl. cancelled)",
        f"""
        SELECT COUNT(DISTINCT r.order_id), COUNT(DISTINCT o.order_id)
        FROM orders o
        JOIN users u ON u.user_id = o.user_id
        LEFT JOIN refunds r ON r.order_id = o.order_id
        WHERE {Q3} AND o.status = 'completed' AND u.is_test = 0
        """,
        "orders",
    ),
    (
        "Order-based, INCLUDING test accounts",
        f"""
        SELECT COUNT(DISTINCT r.order_id), COUNT(DISTINCT o.order_id)
        FROM orders o
        LEFT JOIN refunds r ON r.order_id = o.order_id
        WHERE {Q3} AND o.status = 'completed'
        """,
        "orders",
    ),
    (
        "Revenue-based (glossary: refunded $ / order $)",
        f"""
        SELECT COALESCE(SUM(r.refund_amount), 0), SUM(o.amount)
        FROM orders o
        LEFT JOIN refunds r ON r.order_id = o.order_id
        WHERE {Q3}
        """,
        "usd",
    ),
]


def main():
    con = sqlite3.connect(str(DB_PATH))
    print("Q3 2026 refund rate (orders dated 2026-07-01 to 2026-09-30)")
    print(f"2026 target: below {TARGET:.1f}%\n")
    print(f"{'Method':60} {'Numerator':>12} {'Denominator':>13} {'Rate':>7}  Target")
    print("-" * 104)
    for name, sql, kind in METHODS:
        num, den = con.execute(sql).fetchone()
        rate = 100.0 * num / den
        verdict = "HIT" if rate < TARGET else "MISSED"
        if kind == "usd":
            num_s, den_s = f"${num:,.0f}", f"${den:,.0f}"
        else:
            num_s, den_s = f"{num:,}", f"{den:,}"
        print(f"{name:60} {num_s:>12} {den_s:>13} {rate:6.2f}%  {verdict}")
    con.close()


if __name__ == "__main__":
    main()
