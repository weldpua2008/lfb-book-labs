TRUNCATE legacy.orders,modern.orders,ops.outbox,ops.audit,payment.authorizations,shipping.dispatches RESTART IDENTITY;
UPDATE legacy.stock SET available=100;
UPDATE ops.control SET value=CASE key WHEN 'route_percent' THEN '0' WHEN 'shadow' THEN 'safe' ELSE 'false' END;
TRUNCATE ops.consumers;
INSERT INTO ops.consumers VALUES('nightly-export','legacy',0);
