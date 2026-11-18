"""Safety boundaries plus real PostgreSQL integrity tests; no external DB accepted."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import unittest
from unittest import mock
import lib

class SafetyTests(unittest.TestCase):
    def test_unknown_container_rejected_before_inspection(self):
        with mock.patch.object(lib,'inspect') as inspected:
            with self.assertRaises(lib.LabError):lib.assert_owned('production-postgres')
            inspected.assert_not_called()

    def test_label_collision_rejected(self):
        bad={'Config':{'Labels':{lib.LABEL:'someone_else'}},'HostConfig':{'PortBindings':{}}}
        with mock.patch.object(lib,'inspect',return_value=bad):
            with self.assertRaises(lib.LabError):lib.assert_owned(lib.NAMES['pg18'])

    def test_published_port_rejected(self):
        bad={'Config':{'Labels':{lib.LABEL:lib.PROJECT}},'HostConfig':{'PortBindings':{'5432/tcp':[{'HostPort':'5432'}]}}}
        with mock.patch.object(lib,'inspect',return_value=bad):
            with self.assertRaises(lib.LabError):lib.assert_owned(lib.NAMES['pg18'])

    def test_arbitrary_database_rejected_before_exec(self):
        with mock.patch.object(lib,'assert_owned'),mock.patch.object(lib,'run') as runner:
            with self.assertRaises(lib.LabError):lib.raw_sql(lib.NAMES['pg18'],'DROP TABLE users;',database='production')
            runner.assert_not_called()

    def test_arbitrary_termination_rejected(self):
        with self.assertRaises(lib.LabError):lib.terminate_app(lib.NAMES['pg18'],'production-api')

class RealPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.n=lib.start()

    def test_marker_runtime_and_no_host_port(self):
        self.assertTrue(lib.sql_marker(self.n))
        self.assertTrue(lib.sql(self.n,'SHOW server_version;').startswith('18.7'))
        self.assertFalse(lib.assert_owned(self.n)['HostConfig']['PortBindings'])

    def test_integrity_and_duplicate_idempotency_key(self):
        before=lib.fingerprint(self.n)
        p=lib.raw_sql(self.n,"BEGIN; INSERT INTO shop.orders(id,customer_id,order_no,placed_at,status,total_cents,idempotency_key) SELECT id+1000000,customer_id,'duplicate-probe',placed_at,status,total_cents,idempotency_key FROM shop.orders WHERE id=1; COMMIT;",check=False)
        self.assertNotEqual(p.returncode,0)
        self.assertIn('23505',p.stderr)
        self.assertEqual(before,lib.fingerprint(self.n))
        self.assertEqual(before['unbalanced_orders'],0)

    def test_negative_quantity_and_foreign_key_rejected(self):
        before=lib.fingerprint(self.n)
        for query,state in [("INSERT INTO shop.order_items VALUES(1,99,1,0,100);",'23514'),("INSERT INTO shop.order_items VALUES(999999999,99,1,1,100);",'23503')]:
            p=lib.raw_sql(self.n,query,check=False)
            self.assertNotEqual(p.returncode,0)
            self.assertIn(state,p.stderr)
        self.assertEqual(before,lib.fingerprint(self.n))

if __name__=='__main__':unittest.main(verbosity=2)
