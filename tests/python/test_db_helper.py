import os
import sys
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'processor')))

import db_helper
from db_helper import DatabaseUnavailable, get_db


def fake_mysql(connect):
    connector = types.ModuleType('mysql.connector')
    connector.connect = connect
    pkg = types.ModuleType('mysql')
    pkg.connector = connector
    return {'mysql': pkg, 'mysql.connector': connector}


class TestGetDb(unittest.TestCase):
    def test_mysql_down_raises_instead_of_switching_to_sqlite(self):
        def refuse(**_):
            raise OSError("Can't connect to MySQL server on '127.0.0.1:3306' (10061)")

        with mock.patch.dict(os.environ, {'DB_CONNECTION': 'mysql'}), \
                mock.patch.dict(sys.modules, fake_mysql(refuse)), \
                mock.patch.object(db_helper.sqlite3, 'connect') as sqlite_connect:
            with self.assertRaises(DatabaseUnavailable) as ctx:
                get_db()
        sqlite_connect.assert_not_called()
        self.assertIn("MySQL isn't reachable", str(ctx.exception))
        self.assertIn('DB_CONNECTION=sqlite', str(ctx.exception))

    def test_mysql_up_returns_mysql_connection(self):
        conn = mock.MagicMock()
        with mock.patch.dict(os.environ, {'DB_CONNECTION': 'mysql'}), \
                mock.patch.dict(sys.modules, fake_mysql(lambda **_: conn)):
            db = get_db()
        self.assertFalse(db.is_sqlite)
        self.assertIs(db.connection, conn)


if __name__ == '__main__':
    unittest.main()
