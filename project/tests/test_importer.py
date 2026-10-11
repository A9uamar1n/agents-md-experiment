import unittest

from fitstat.money import split_evenly, to_kopecks, to_rubles
from tests.helpers import demo_db


class ImporterTest(unittest.TestCase):
    def setUp(self):
        self.conn, self.cfg, self.counts = demo_db()

    def test_row_counts(self):
        self.assertEqual(
            self.counts,
            {"clubs": 2, "trainers": 3, "persons": 4, "visits": 6, "sales": 7, "sessions": 2},
        )

    def test_partner_channel_is_normalized(self):
        channel = self.conn.execute("SELECT channel FROM sales WHERE id = 2").fetchone()[0]
        self.assertEqual(channel, "partner")

    def test_amount_in_kopecks(self):
        amount = self.conn.execute("SELECT amount_kop FROM sales WHERE id = 2").fetchone()[0]
        self.assertEqual(amount, 350050)

    def test_bar_sale_without_person(self):
        person = self.conn.execute("SELECT person_id FROM sales WHERE id = 3").fetchone()[0]
        self.assertIsNone(person)


class MoneyTest(unittest.TestCase):
    def test_round_trip(self):
        self.assertEqual(to_kopecks("1234.50"), 123450)
        self.assertEqual(to_rubles(123450), 1234.5)

    def test_split_evenly(self):
        self.assertEqual(split_evenly(1001, 2), [501, 500])
        self.assertEqual(sum(split_evenly(1000, 3)), 1000)


if __name__ == "__main__":
    unittest.main()
