-- After actual writer fence; not a latency guarantee.
BEGIN ISOLATION LEVEL READ COMMITTED;
SET LOCAL lock_timeout = '500ms';
SET LOCAL statement_timeout = '30s';
LOCK TABLE shop.orders, shop.order_items, shop.payments
IN SHARE MODE;
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM shop.orders
    WHERE total_eur IS NULL
       OR total_eur IS DISTINCT FROM
          total_cents::numeric / 100
  ) OR EXISTS (
    SELECT 1 FROM shop.orders AS o
    LEFT JOIN (
      SELECT order_id,
             sum(quantity::bigint * unit_price_cents) AS s
      FROM shop.order_items GROUP BY order_id
    ) AS i ON i.order_id = o.id
    WHERE o.total_cents IS DISTINCT FROM i.s
  ) OR EXISTS (
    SELECT 1 FROM shop.orders AS o
    LEFT JOIN shop.payments AS p ON p.order_id = o.id
    WHERE o.status = 'bezahlt'
      AND (p.order_id IS NULL OR
           p.amount_cents IS DISTINCT FROM o.total_cents)
  ) THEN
    RAISE EXCEPTION 'money acceptance refused';
  END IF;
END;
$$;
COMMIT;
