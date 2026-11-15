# Brightcart Metric Definitions

Owner: Analytics team

This page defines the core metrics used in Brightcart dashboards and business reviews.

## Refund Rate

**Definition:** The share of completed orders that were refunded.

```
Refund Rate = (number of completed orders with a refund) / (number of completed orders)
```

- Orders are assigned to a period by **order date** (`orders.order_ts`), not refund date.
- An order counts as refunded if it has a row in `refunds`, whether the refund was full or partial.
- Reported as a percentage with one decimal place.

## Monthly Active Users (MAU)

**Definition:** The number of distinct users with at least one session in the trailing **30 days**.

```
MAU = COUNT(DISTINCT user_id) from sessions where session_ts is within the last 30 days
```

## Average Order Value (AOV)

**Definition:** The average amount of completed orders in the period.

```
AOV = SUM(amount) / COUNT(order_id), completed orders only
```

## Conversion Rate

**Definition:** The share of sessions that led to a completed order by the same user on the same day.

```
Conversion Rate = (sessions followed by a completed order the same day) / (all sessions)
```

## Repeat Purchase Rate

**Definition:** The share of customers with a completed order in the period who had at least one earlier completed order.
