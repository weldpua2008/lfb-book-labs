-- CH07..12: Neue Geldspalte wird zunächst optional ergänzt.
ALTER TABLE shop.orders ADD COLUMN IF NOT EXISTS total_eur numeric(14,2);
CREATE OR REPLACE FUNCTION shop.sync_order_money() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  -- In der Übergangsphase ist cents die autoritative Schreibschnittstelle.
  NEW.total_eur := NEW.total_cents::numeric/100;
  RETURN NEW;
END $$;
CREATE OR REPLACE TRIGGER sync_order_money BEFORE INSERT OR UPDATE OF total_cents ON shop.orders
FOR EACH ROW EXECUTE FUNCTION shop.sync_order_money();
INSERT INTO shop.schema_versions VALUES(2,'Expand: total_eur mit autoritativem cents-Schreibpfad') ON CONFLICT DO NOTHING;
INSERT INTO shop.migration_checkpoints(migration_id) VALUES('money_v2') ON CONFLICT DO NOTHING;
