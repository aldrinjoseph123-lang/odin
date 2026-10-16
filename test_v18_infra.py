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
        calls = []

        def drain(limit):
            calls.append(limit)
            scheduler._stopping = True   # SIGTERM arrives during the first send
            return 1
        with patch("services.outbox.drain", drain):
            self.assertEqual(scheduler.outbox_pass(), 1)
        self.assertEqual(calls, [1])


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
