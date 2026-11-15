# Brightcart Data Dictionary

Warehouse: `data/brightcart.db` (SQLite). All timestamps are UTC, stored as text in `YYYY-MM-DD HH:MM:SS` format.

## users

One row per registered account.

| Column | Type | Description |
|---|---|---|
| `user_id` | INTEGER | Primary key. |
| `signup_date` | TEXT | Date the account was created (`YYYY-MM-DD`). |
| `country` | TEXT | Two-letter country code from the shipping address at signup. |
| `is_test` | INTEGER | Flag for internal QA accounts (1 = QA account, 0 = regular account). |

## orders

One row per order placed on the storefront.

| Column | Type | Description |
|---|---|---|
| `order_id` | INTEGER | Primary key. |
| `user_id` | INTEGER | Foreign key to `users.user_id`. |
| `order_ts` | TEXT | Timestamp when the order was placed. |
| `amount` | REAL | Order total in USD, after discounts, before tax. |
| `status` | TEXT | `completed` or `cancelled`. |

## refunds

One row per refund issued. An order has at most one refund.

| Column | Type | Description |
|---|---|---|
| `refund_id` | INTEGER | Primary key. |
| `order_id` | INTEGER | Foreign key to `orders.order_id`. |
| `refund_ts` | TEXT | Timestamp when the refund was issued. |
| `refund_amount` | REAL | Amount refunded in USD. Can be less than the order amount (partial refund). |

## sessions

One row per storefront visit by a logged-in user.

| Column | Type | Description |
|---|---|---|
| `session_id` | INTEGER | Primary key. |
| `user_id` | INTEGER | Foreign key to `users.user_id`. |
| `session_ts` | TEXT | Timestamp when the session started. |

## Other data

Raw exports from third-party tools (clickstream, marketing spend, support tickets) are in `data/raw_exports/` as CSV files. They are not loaded into the warehouse.
