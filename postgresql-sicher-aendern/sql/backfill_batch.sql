-- Daten und genau ein Checkpoint committen gemeinsam.
BEGIN ISOLATION LEVEL READ COMMITTED;
SET LOCAL lock_timeout = '500ms';
SET LOCAL statement_timeout = '5s';
SELECT shop.money_v2_batch(:batch_size);
COMMIT;
