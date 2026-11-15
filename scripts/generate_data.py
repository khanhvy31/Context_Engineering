"""Generate the Brightcart sandbox data.

Creates:
  data/brightcart.db                      SQLite warehouse (users, orders, refunds, sessions)
  data/raw_exports/*.csv                  raw exports from other tools

Deterministic: running it again produces identical files.

Usage:
    python scripts/generate_data.py
"""

import csv
import random
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "brightcart.db"
EXPORT_DIR = DATA_DIR / "raw_exports"

SEED = 42
N_USERS = 5000

ORDER_START = datetime(2025, 1, 1)
ORDER_END = datetime(2026, 9, 30, 23, 59, 59)

COUNTRIES = ["US", "CA", "GB", "DE", "FR", "AU", "NL", "SE", "ES", "IT"]
COUNTRY_WEIGHTS = [38, 10, 12, 9, 7, 7, 5, 4, 4, 4]

TS_FMT = "%Y-%m-%d %H:%M:%S"


def fmt(ts):
    return ts.strftime(TS_FMT)


def random_ts(rng, start, end, skew=1.0):
    """Random timestamp in [start, end]. skew > 1 puts more weight on later dates."""
    span = (end - start).total_seconds()
    u = rng.random() ** (1.0 / skew)
    return start + timedelta(seconds=int(span * u))


# ---------------------------------------------------------------------------
# Warehouse tables
# ---------------------------------------------------------------------------

def build_users(rng):
    users = []
    signup_start = datetime(2024, 6, 1)
    signup_end = datetime(2026, 8, 31)
    for user_id in range(1, N_USERS + 1):
        signup = random_ts(rng, signup_start, signup_end, skew=1.3)
        country = rng.choices(COUNTRIES, weights=COUNTRY_WEIGHTS)[0]
        is_test = int(rng.random() < 0.03)
        users.append((user_id, signup.strftime("%Y-%m-%d"), country, is_test))
    return users


def build_orders_and_refunds(rng, users):
    orders = []
    refunds = []
    order_id = 0
    refund_id = 0

    for user_id, signup_date, _country, is_test in users:
        signup = datetime.strptime(signup_date, "%Y-%m-%d")
        first_possible = max(signup, ORDER_START)
        if first_possible >= ORDER_END:
            continue

        if is_test:
            n_orders = rng.randint(4, 12)
        else:
            n_orders = rng.choices(range(0, 16),
                                   weights=[8, 14, 13, 11, 10, 9, 8, 7, 5, 4, 3, 3, 2, 1, 1, 1])[0]

        for _ in range(n_orders):
            order_id += 1
            ts = random_ts(rng, first_possible, ORDER_END, skew=1.4)
            amount = round(min(rng.lognormvariate(3.8, 0.75), 900.0), 2)
            status = "cancelled" if rng.random() < 0.06 else "completed"
            orders.append((order_id, user_id, fmt(ts), amount, status))

            if status != "completed":
                continue

            if is_test:
                p_refund = 0.35
            else:
                p_refund = min(0.004 + 0.00036 * amount, 0.25)

            if rng.random() < p_refund:
                refund_id += 1
                refund_ts = ts + timedelta(days=rng.randint(2, 30), hours=rng.randint(0, 23),
                                           minutes=rng.randint(0, 59))
                if rng.random() < 0.9:
                    refund_amount = amount
                else:
                    refund_amount = round(amount * rng.uniform(0.5, 0.9), 2)
                refunds.append((refund_id, order_id, fmt(refund_ts), refund_amount))

    return orders, refunds


def build_sessions(rng, users):
    sessions = []
    session_id = 0
    for user_id, signup_date, _country, _is_test in users:
        signup = datetime.strptime(signup_date, "%Y-%m-%d")
        start = max(signup, ORDER_START)
        if start >= ORDER_END:
            continue
        for _ in range(rng.randint(0, 9)):
            session_id += 1
            sessions.append((session_id, user_id, fmt(random_ts(rng, start, ORDER_END, skew=1.3))))
    return sessions


def write_db(users, orders, refunds, sessions):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp_path = DB_PATH.with_suffix(".db.tmp")
    if tmp_path.exists():
        tmp_path.unlink()

    con = sqlite3.connect(str(tmp_path))
    cur = con.cursor()
    cur.executescript(
        """
        CREATE TABLE users(
            user_id INTEGER PRIMARY KEY,
            signup_date TEXT,
            country TEXT,
            is_test INTEGER
        );
        CREATE TABLE orders(
            order_id INTEGER PRIMARY KEY,
            user_id INTEGER,
            order_ts TEXT,
            amount REAL,
            status TEXT
        );
        CREATE TABLE refunds(
            refund_id INTEGER PRIMARY KEY,
            order_id INTEGER,
            refund_ts TEXT,
            refund_amount REAL
        );
        CREATE TABLE sessions(
            session_id INTEGER PRIMARY KEY,
            user_id INTEGER,
            session_ts TEXT
        );
        """
    )
    cur.executemany("INSERT INTO users VALUES (?, ?, ?, ?)", users)
    cur.executemany("INSERT INTO orders VALUES (?, ?, ?, ?, ?)", orders)
    cur.executemany("INSERT INTO refunds VALUES (?, ?, ?, ?)", refunds)
    cur.executemany("INSERT INTO sessions VALUES (?, ?, ?)", sessions)
    con.commit()
    con.close()

    tmp_path.replace(DB_PATH)


# ---------------------------------------------------------------------------
# Raw exports
# ---------------------------------------------------------------------------

def write_csv(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)


def build_clickstream(rng, year, month, n_rows):
    start = datetime(year, month, 1)
    end = datetime(year + (month == 12), month % 12 + 1, 1) - timedelta(seconds=1)
    event_types = ["page_view", "product_view", "add_to_cart", "remove_from_cart",
                   "begin_checkout", "search", "wishlist_add", "newsletter_signup"]
    event_weights = [40, 25, 10, 3, 6, 12, 3, 1]
    pages = ["/", "/search", "/category/home", "/category/kitchen", "/category/outdoor",
             "/category/apparel", "/category/beauty", "/product", "/cart", "/checkout",
             "/account", "/help", "/blog"]
    devices = ["mobile", "desktop", "tablet"]
    referrers = ["direct", "google", "instagram", "tiktok", "newsletter", "affiliate", "bing"]
    rows = []
    for i in range(n_rows):
        ts = random_ts(rng, start, end)
        rows.append((
            f"ev_{year}{month:02d}_{i + 1:06d}",
            fmt(ts),
            f"s_{rng.randint(100000, 999999)}",
            rng.randint(1, N_USERS) if rng.random() < 0.7 else "",
            rng.choices(event_types, weights=event_weights)[0],
            rng.choice(pages),
            rng.choices(devices, weights=[62, 33, 5])[0],
            rng.choices(referrers, weights=[30, 28, 12, 9, 8, 8, 5])[0],
        ))
    rows.sort(key=lambda r: r[1])
    return rows


def build_marketing_spend(rng):
    channels = {
        "google_search": ["brand_terms", "generic_home", "generic_kitchen", "competitor_terms"],
        "meta": ["prospecting_broad", "retargeting_7d", "lookalike_1pct", "summer_sale"],
        "tiktok": ["creator_collab", "spark_ads", "back_to_school"],
        "pinterest": ["home_inspo", "holiday_preview"],
        "affiliate": ["coupon_sites", "review_blogs"],
        "email": ["weekly_digest", "abandoned_cart", "winback"],
    }
    rows = []
    day = datetime(2026, 1, 1)
    end = datetime(2026, 9, 30)
    while day <= end:
        for channel, campaigns in channels.items():
            for campaign in campaigns:
                if rng.random() < 0.55:
                    continue
                spend = round(rng.uniform(40, 1800), 2)
                impressions = int(spend * rng.uniform(60, 220))
                clicks = int(impressions * rng.uniform(0.004, 0.03))
                conversions = int(clicks * rng.uniform(0.01, 0.06))
                rows.append((day.strftime("%Y-%m-%d"), channel, campaign, spend,
                             impressions, clicks, conversions))
        day += timedelta(days=1)
    return rows


def build_support_tickets(rng, n_rows):
    categories = ["shipping_delay", "damaged_item", "wrong_item", "refund_request",
                  "account_access", "payment_issue", "product_question", "promo_code"]
    weights = [24, 10, 7, 12, 9, 8, 22, 8]
    priorities = ["low", "normal", "high", "urgent"]
    statuses = ["closed", "closed", "closed", "solved", "open", "pending"]
    agents = ["agent_" + name for name in
              ["ana", "ben", "chloe", "dev", "elif", "femi", "gus", "hana", "ivan", "jo"]]
    rows = []
    start = datetime(2026, 1, 1)
    end = datetime(2026, 9, 30, 23, 59, 59)
    for i in range(n_rows):
        created = random_ts(rng, start, end)
        status = rng.choice(statuses)
        first_response_min = rng.randint(3, 900)
        csat = rng.choice(["", "1", "2", "3", "4", "4", "5", "5", "5"]) if status in ("closed", "solved") else ""
        rows.append((
            f"T-{26000 + i + 1}",
            fmt(created),
            rng.randint(1, N_USERS),
            rng.choices(categories, weights=weights)[0],
            rng.choices(priorities, weights=[30, 50, 15, 5])[0],
            status,
            rng.choice(agents),
            first_response_min,
            csat,
        ))
    rows.sort(key=lambda r: r[1])
    return rows


def write_exports():
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    rng = random.Random(SEED + 1)

    click_header = ["event_id", "event_ts", "session_key", "user_id", "event_type",
                    "page", "device", "referrer"]
    for month, n_rows in ((7, 4200), (8, 4600), (9, 4400)):
        write_csv(EXPORT_DIR / f"clickstream_2026_{month:02d}.csv", click_header,
                  build_clickstream(rng, 2026, month, n_rows))

    write_csv(EXPORT_DIR / "marketing_spend_2026.csv",
              ["date", "channel", "campaign", "spend_usd", "impressions", "clicks", "conversions"],
              build_marketing_spend(rng))

    write_csv(EXPORT_DIR / "support_tickets_2026.csv",
              ["ticket_id", "created_ts", "user_id", "category", "priority", "status",
               "assignee", "first_response_minutes", "csat"],
              build_support_tickets(rng, 3600))


def main():
    rng = random.Random(SEED)
    users = build_users(rng)
    orders, refunds = build_orders_and_refunds(rng, users)
    sessions = build_sessions(rng, users)
    write_db(users, orders, refunds, sessions)
    write_exports()

    print(f"Wrote {DB_PATH.relative_to(ROOT)}")
    print(f"  users:    {len(users):>6}")
    print(f"  orders:   {len(orders):>6}")
    print(f"  refunds:  {len(refunds):>6}")
    print(f"  sessions: {len(sessions):>6}")
    print(f"Wrote raw exports to {EXPORT_DIR.relative_to(ROOT)}/")


if __name__ == "__main__":
    main()
