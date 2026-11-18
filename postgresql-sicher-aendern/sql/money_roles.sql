-- Nur im besitzgeprüften, isolierten Buchcluster.
DO $$
DECLARE
  role_name text;
  owner_marker text;
BEGIN
  FOREACH role_name IN ARRAY ARRAY[
    'lfb_money_old', 'lfb_money_backfill',
    'lfb_money_target'
  ] LOOP
    SELECT shobj_description(oid, 'pg_authid')
    INTO owner_marker
    FROM pg_roles WHERE rolname = role_name;
    IF FOUND THEN
      IF owner_marker IS DISTINCT FROM
           'lfb_pg_book_20261118' THEN
        RAISE EXCEPTION 'foreign role: %', role_name;
      END IF;
    ELSE
      EXECUTE format('CREATE ROLE %I LOGIN', role_name);
      EXECUTE format('COMMENT ON ROLE %I IS %L',
        role_name, 'lfb_pg_book_20261118');
    END IF;
    IF EXISTS (
      SELECT 1 FROM pg_roles
      WHERE rolname = role_name
      AND (rolsuper OR rolcreaterole OR rolcreatedb
           OR rolreplication OR rolbypassrls)
    ) OR EXISTS (
      SELECT 1 FROM pg_auth_members
      WHERE member = (SELECT oid FROM pg_roles
                      WHERE rolname = role_name)
    ) THEN
      RAISE EXCEPTION 'unexpected role authority';
    END IF;
  END LOOP;
END;
$$;
