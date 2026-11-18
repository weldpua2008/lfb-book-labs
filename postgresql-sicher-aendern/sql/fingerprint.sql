SELECT json_build_object(
 'orders',(SELECT count(*) FROM shop.orders),
 'items',(SELECT count(*) FROM shop.order_items),
 'customers',(SELECT count(*) FROM shop.customers),
 'products',(SELECT count(*) FROM shop.products),
 'payments',(SELECT count(*) FROM shop.payments),
 'total_cents',(SELECT sum(total_cents) FROM shop.orders),
 'item_total_cents',(SELECT sum(quantity::bigint*unit_price_cents) FROM shop.order_items),
 'paid_cents',(SELECT sum(amount_cents) FROM shop.payments),
 'unbalanced_orders',(SELECT count(*) FROM shop.orders o JOIN (SELECT order_id,sum(quantity::bigint*unit_price_cents) n FROM shop.order_items GROUP BY order_id) s ON s.order_id=o.id WHERE o.total_cents<>s.n),
 'orders_md5',(SELECT md5(string_agg(id||':'||customer_id||':'||order_no||':'||(placed_at AT TIME ZONE 'UTC')||':'||status||':'||total_cents||':'||idempotency_key||':'||(updated_at AT TIME ZONE 'UTC'),'|' ORDER BY id)) FROM shop.orders),
 'items_md5',(SELECT md5(string_agg(order_id||':'||line_no||':'||product_id||':'||quantity||':'||unit_price_cents,'|' ORDER BY order_id,line_no)) FROM shop.order_items),
 'customers_md5',(SELECT md5(string_agg(id||':'||customer_no||':'||display_name||':'||email||':'||region,'|' ORDER BY id)) FROM shop.customers),
 'products_md5',(SELECT md5(string_agg(id||':'||sku||':'||name||':'||unit_price_cents||':'||active,'|' ORDER BY id)) FROM shop.products),
 'payments_md5',(SELECT md5(string_agg(id||':'||order_id||':'||amount_cents||':'||provider_reference||':'||(paid_at AT TIME ZONE 'UTC'),'|' ORDER BY id)) FROM shop.payments),
 'inventory_md5',(SELECT md5(string_agg(product_id||':'||available||':'||reserved,'|' ORDER BY product_id)) FROM shop.inventory),
 'unbalanced_payments',(SELECT count(*) FROM shop.payments p JOIN shop.orders o ON o.id=p.order_id WHERE p.amount_cents<>o.total_cents)
);
