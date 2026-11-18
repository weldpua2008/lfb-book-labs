-- All people, orders and products in this lab are fictional.
CREATE ROLE hb_app LOGIN PASSWORD 'local-lab-app';
CREATE ROLE hb_payment LOGIN PASSWORD 'local-lab-payment';
CREATE ROLE hb_shipping LOGIN PASSWORD 'local-lab-shipping';
CREATE SCHEMA legacy;
CREATE SCHEMA modern;
CREATE SCHEMA ops;
CREATE SCHEMA payment AUTHORIZATION hb_payment;
CREATE SCHEMA shipping AUTHORIZATION hb_shipping;
CREATE TABLE legacy.products(sku text PRIMARY KEY, unit_net numeric(12,3) NOT NULL);
INSERT INTO legacy.products VALUES ('WARTUNG',19.995),('SENSOR',7.125),('PUMPE',49.995);
CREATE TABLE legacy.stock(sku text PRIMARY KEY REFERENCES legacy.products, available integer NOT NULL CHECK(available>=0));
INSERT INTO legacy.stock SELECT sku,100 FROM legacy.products;
CREATE TABLE legacy.orders(
 order_id text PRIMARY KEY, request_id text NOT NULL UNIQUE, fingerprint text NOT NULL,
 sku text NOT NULL, quantity integer NOT NULL CHECK(quantity BETWEEN 1 AND 20), customer_group text NOT NULL,
 subtotal_cents bigint NOT NULL, discount_cents bigint NOT NULL, net_cents bigint NOT NULL,
 tax_cents bigint NOT NULL, total_cents bigint NOT NULL, status text NOT NULL,
 created_at timestamptz NOT NULL, provider_ref text, CHECK(total_cents=net_cents+tax_cents)
);
CREATE TABLE modern.orders(LIKE legacy.orders INCLUDING ALL);
CREATE TABLE ops.outbox(
 event_id text PRIMARY KEY, order_id text NOT NULL UNIQUE, backend text NOT NULL,
 total_cents bigint NOT NULL, kind text NOT NULL DEFAULT 'ORDER_READY',
 state text NOT NULL DEFAULT 'PENDING', attempts integer NOT NULL DEFAULT 0,
 last_error text, created_at timestamptz NOT NULL DEFAULT now(), delivered_at timestamptz
);
CREATE TABLE ops.control(key text PRIMARY KEY,value text NOT NULL);
INSERT INTO ops.control VALUES ('route_percent','0'),('retired','false'),('writes_frozen','false'),('shadow','safe');
CREATE TABLE ops.consumers(name text PRIMARY KEY, backend text NOT NULL, calls integer NOT NULL DEFAULT 0);
INSERT INTO ops.consumers VALUES ('nightly-export','legacy',0);
CREATE TABLE ops.audit(id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, action text NOT NULL, detail text NOT NULL, created_at timestamptz NOT NULL DEFAULT now());
SET ROLE hb_payment;
CREATE TABLE payment.authorizations(key text PRIMARY KEY,order_id text NOT NULL, amount_cents bigint NOT NULL, provider_ref text NOT NULL UNIQUE,status text NOT NULL);
RESET ROLE;
SET ROLE hb_shipping;
CREATE TABLE shipping.dispatches(event_id text PRIMARY KEY,order_id text NOT NULL UNIQUE,total_cents bigint NOT NULL, accepted_at timestamptz NOT NULL DEFAULT now());
RESET ROLE;
GRANT USAGE ON SCHEMA legacy,modern,ops TO hb_app;
GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA legacy,modern,ops TO hb_app;
GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA ops TO hb_app;
GRANT USAGE ON SCHEMA shipping,payment TO hb_app;
GRANT SELECT ON shipping.dispatches,payment.authorizations TO hb_app;
