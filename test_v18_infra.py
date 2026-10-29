"""v1.8.0 fix round: the scheduler's health and stop (boot id, join budget) and the
packaging facts. Run with: python -m unittest test_v18_infra"""
import os
import re
from unittest.mock import patch

import scheduler
from test_fix_logic import FixBase

HERE = os.path.dirname(os.path.abspath(__file__))


def read(*parts):
    with open(os.path.join(HERE, *parts)) as fh:
        return fh.read()


class SchedulerHealthTestCase(FixBase):
    def test_a_beat_from_the_previous_container_is_not_health(self):
        """The database is shared: the old scheduler's last beat must not make a hung new one look alive."""
        scheduler.beat()
        self.assertTrue(scheduler.healthy(boot=scheduler.BOOT_ID))
        self.assertFalse(scheduler.healthy(boot="the-previous-container"))
        self.assertTrue(scheduler.healthy())   # no boot given (Settings, tests): any fresh beat
        with patch.object(scheduler, "BOOT_ID", "the-new-container"):
            self.assertFalse(scheduler.healthy(boot=scheduler.BOOT_ID))   # new process, no beat of its own yet
            scheduler.beat()
            self.assertTrue(scheduler.healthy(boot="the-new-container"))

    def test_the_healthcheck_command_needs_the_boot_file(self):
        self.assertIn("--healthcheck", read("docker-compose.yml"))
        self.assertIn("BOOT_FILE", read("scheduler.py").split('if __name__ == "__main__":')[1])


class StopBudgetTestCase(FixBase):
    def test_the_join_budget_fits_the_compose_grace_period(self):
        grace = re.search(r"scheduler:.*?stop_grace_period:\s*(\d+)m", read("docker-compose.yml"), re.S)
        self.assertLess(scheduler.STOP_BUDGET, int(grace.group(1)) * 60)

    def test_a_stop_leaves_the_batch_after_the_send_in_hand(self):
        self.addCleanup(setattr, scheduler, "_stopping", False)
        from services import outbox
        self.ctx()
        for n in range(3):
            outbox.add("mail", to=f"p{n}@corp.example", subject="s", html="x")

        def send(*_a, **_k):
            scheduler._stopping = True   # SIGTERM arrives during the first send
            return True, None
        with patch("graph.send_mail", side_effect=send):
            self.assertEqual(scheduler.outbox_pass(), 1)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM outbox WHERE sent_at IS NULL")[0][0], 2)   # untouched, for the next start


class PackagingTestCase(FixBase):
    def test_the_image_leaves_out_tests_and_most_docs_but_keeps_the_map(self):
        ignore = read(".dockerignore").split()
        for line in ("test_*.py", "tests/", "docs/*", "!docs/system-map.html"):
            self.assertIn(line, ignore)
        self.assertTrue(os.path.exists(os.path.join(HERE, "docs", "system-map.html")))

    def test_the_cloudflare_access_log_names_the_visitor(self):
        conf = read("deploy", "nginx.cloudflare.conf")
        self.assertIn("log_format odin '$client_ip", conf)
        self.assertRegex(conf, r"error_log \S+ crit;")
