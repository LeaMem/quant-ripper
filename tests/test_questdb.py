from __future__ import annotations

import _path  # noqa: F401
import unittest

from quant_ripper.infrastructure.questdb_client import split_sql


class QuestDbTests(unittest.TestCase):
    def test_split_sql_keeps_semicolon_inside_strings(self):
        sql = """
        CREATE TABLE a (x STRING);
        INSERT INTO a VALUES ('a;b');
        -- a comment with ;
        CREATE TABLE b (y INT);
        """

        statements = split_sql(sql)

        self.assertEqual(len(statements), 3)
        self.assertIn("CREATE TABLE a", statements[0])
        self.assertIn("'a;b'", statements[1])
        self.assertIn("CREATE TABLE b", statements[2])
