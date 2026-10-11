import unittest

from fitstat.reports import club_monthly_report, network_monthly_report, trainer_monthly_report
from tests.helpers import demo_db


class ClubReportTest(unittest.TestCase):
    def setUp(self):
        self.conn, self.cfg, _ = demo_db()

    def test_club_may(self):
        report = club_monthly_report(self.conn, self.cfg, 1, "2026-05")
        self.assertEqual(report["revenue"], 11750.5)
        self.assertEqual(report["revenue_own"], 8250.0)
        self.assertEqual(report["visits"], 4)
        self.assertEqual(report["active_members"], 2)
        self.assertEqual(report["pt_sessions"], 1)
        self.assertEqual(report["pt_revenue"], 2000.0)

    def test_empty_month(self):
        report = club_monthly_report(self.conn, self.cfg, 2, "2026-03")
        self.assertEqual(report["revenue"], 0.0)
        self.assertEqual(report["visits"], 0)


class TrainerReportTest(unittest.TestCase):
    def setUp(self):
        self.conn, self.cfg, _ = demo_db()

    def test_trainer_may(self):
        report = trainer_monthly_report(self.conn, self.cfg, 1, "2026-05")
        self.assertEqual(report["sessions"], 1)
        self.assertEqual(report["pt_revenue"], 2000.0)

    def test_trainer_without_sessions(self):
        report = trainer_monthly_report(self.conn, self.cfg, 2, "2026-05")
        self.assertEqual(report["sessions"], 0)
        self.assertEqual(report["pt_revenue"], 0.0)


class NetworkReportTest(unittest.TestCase):
    def setUp(self):
        self.conn, self.cfg, _ = demo_db()

    def test_closed_club_excluded(self):
        report = network_monthly_report(self.conn, self.cfg, "2026-05")
        self.assertEqual(report["clubs_count"], 1)
        self.assertEqual(report["revenue"], 11750.5)
        self.assertEqual(report["visits"], 4)

    def test_club_open_before_closing(self):
        report = network_monthly_report(self.conn, self.cfg, "2026-04")
        self.assertEqual(report["clubs_count"], 2)
        self.assertEqual(report["revenue"], 100.0)


if __name__ == "__main__":
    unittest.main()
