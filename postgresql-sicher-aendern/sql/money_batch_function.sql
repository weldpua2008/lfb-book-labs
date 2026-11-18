-- Ein Aufruf gehört in eine READ-COMMITTED-Transaktion.
CREATE OR REPLACE FUNCTION shop.money_v2_batch(
  batch_size integer
) RETURNS jsonb
LANGUAGE plpgsql
AS $$
DECLARE
  cursor_id bigint;
  selected_count bigint;
  highest_id bigint;
  missing_id boolean;
  updated_count bigint;
  result jsonb;
BEGIN
  IF current_setting('transaction_isolation')
       <> 'read committed' THEN
    RAISE EXCEPTION 'READ COMMITTED required';
  END IF;
  IF batch_size IS NULL
     OR batch_size NOT BETWEEN 1 AND 10000
  THEN
    RAISE EXCEPTION 'invalid batch size';
  END IF;
  SELECT last_id INTO STRICT cursor_id
  FROM shop.migration_checkpoints
  WHERE migration_id = 'money_v2'
  FOR UPDATE;

  WITH batch AS MATERIALIZED (
    SELECT id
    FROM shop.orders
    WHERE id > cursor_id
    ORDER BY id
    LIMIT batch_size
    FOR NO KEY UPDATE
  ), changed AS (
    UPDATE shop.orders AS o
    SET total_eur = o.total_cents::numeric / 100
    FROM batch AS b
    WHERE o.id = b.id
    RETURNING o.id
  )
  SELECT (SELECT count(*) FROM batch),
         (SELECT max(id) FROM changed),
         EXISTS (
           (SELECT id FROM batch
            EXCEPT SELECT id FROM changed)
           UNION ALL
           (SELECT id FROM changed
            EXCEPT SELECT id FROM batch)
         )
  INTO selected_count, highest_id, missing_id;

  IF missing_id THEN
    RAISE EXCEPTION 'incomplete batch RETURNING';
  END IF;
  UPDATE shop.migration_checkpoints
  SET last_id = COALESCE(highest_id, cursor_id),
      finished = (selected_count = 0)
  WHERE migration_id = 'money_v2';
  GET DIAGNOSTICS updated_count = ROW_COUNT;
  IF updated_count <> 1 THEN
    RAISE EXCEPTION 'checkpoint update suppressed';
  END IF;
  SELECT to_jsonb(m) INTO STRICT result
  FROM shop.migration_checkpoints AS m
  WHERE migration_id = 'money_v2';
  RETURN result;
END;
$$;
REVOKE ALL ON FUNCTION shop.money_v2_batch(integer)
FROM PUBLIC;
