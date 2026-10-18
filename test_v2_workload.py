"""Odin 2.0, workstream 7: workload and capacity, and the hand-over on leave.
Run with: python -m unittest test_v2_workload

The clock is frozen at Wednesday 4 Nov 2026 (the week of Mon 2 Nov) for the
workload service, so no test depends on the weekday or the month."""
from datetime import date
from unittest import mock

from test_app import STRONG_PASSWORD
from test_fix_logic import FixBase

J = {"Accept": "application/json"}
TODAY = date(2026, 11, 4)
W0, W1, W2, W3 = "2026-11-02", "2026-11-09", "2026-11-16", "2026-11-23"


class WorkloadBase(FixBase):
    def setUp(self):
        super().setUp()
        self._set_policy(timezone="UTC")
        for target in ("services.workload.local_today", "routes.workload.local_today"):
            p = mock.patch(target, return_value=TODAY)
            p.start()
            self.addCleanup(p.stop)
        self.csrf = self.client.get("/api/session").get_json()["csrf"]
        self.new_project(name="Alpha")   # rollout 1, managed by the admin

    def staff(self, username, role="Member"):
        return self._make_user(username, role)

    def due_task(self, who, due, hours=None, done=0, pid=1, title="T"):
        self.sql("INSERT INTO tasks (project_id, title, assignee_id, due_date, created_at, created_by, done, estimate_hours) "
                 "VALUES (?, ?, ?, ?, '2026-11-01T00:00:00', 'test', ?, ?)", pid, title, who, due, done, hours)

    def person(self, uid, client=None):
        data = (client or self.client).get("/api/workload").get_json()
        return next((p for p in data["people"] if p["id"] == uid), None)

    def hours(self, uid):
        return [c["hours"] for c in self.person(uid)["weeks"]]


class WeeklySumTestCase(WorkloadBase):
    def test_the_week_adds_estimates_defaults_and_the_manager_allowance(self):
        priya = self.staff("priya")
        self.sql("UPDATE projects SET owner_id = ? WHERE id = 1", priya)   # she manages one active rollout: 4 h a week
        self.due_task(priya, "2026-11-04", hours=5)        # this week, estimated
        self.due_task(priya, "2026-11-06")                 # this week, no estimate: the 2 h default
        self.due_task(priya, "2026-11-09", hours=3)        # next week (Monday)
        self.due_task(priya, "2026-11-22", hours=1.5)      # Sunday of week 2
        self.due_task(priya, "2026-12-30", hours=40)       # beyond the four weeks
        self.due_task(priya, "2026-11-05", hours=9, done=1)   # finished: not load
        self.due_task(priya, None, hours=9)                # no date: no week
        self.due_task(None, "2026-11-05", hours=9)         # nobody's
        p = self.person(priya)
        self.assertEqual([c["week"] for c in p["weeks"]], [W0, W1, W2, W3])
        self.assertEqual(self.hours(priya), [11, 7, 5.5, 4])
        self.assertEqual([c["tasks"] for c in p["weeks"]], [2, 1, 1, 0])
        self.assertEqual((p["weeks"][0]["task_hours"], p["weeks"][0]["pm_hours"], p["rollouts"], p["capacity"]), (7, 4, 1, 30))
        self.assertEqual(p["weeks"][0]["pct"], 37)

    def test_policies_move_the_numbers(self):
        priya = self.staff("priya")
        self.sql("UPDATE projects SET owner_id = ? WHERE id = 1", priya)
        self.due_task(priya, "2026-11-04")
        self._set_policy(default_task_hours="3", pm_hours_per_rollout="6", capacity_hours_per_week="20")
        self.assertEqual(self.hours(priya)[0], 9)
        self.assertEqual(self.person(priya)["capacity"], 20)

    def test_late_work_counts_now_and_only_in_the_current_week(self):
        priya = self.staff("priya")
        self.due_task(priya, "2026-10-20", hours=4)
        self.assertEqual(self.hours(priya), [4, 0, 0, 0])
        picker = self.client.get(f"/api/workload/week?date={W1}").get_json()["people"][str(priya)]
        self.assertEqual(picker["hours"], 0)   # next week's window does not take it

    def test_closed_deleted_and_inactive_work_does_not_count(self):
        self.new_project(name="Closed"); self.new_project(name="Gone")
        priya = self.staff("priya")
        self.sql("UPDATE projects SET stage = ? WHERE id = 2", self.stages(2)[-1])
        self.sql("UPDATE projects SET deleted_at = '2026-11-01T00:00:00' WHERE id = 3")
        for pid in (1, 2, 3):
            self.due_task(priya, "2026-11-04", hours=2, pid=pid)
        self.assertEqual(self.hours(priya)[0], 2)
        gone = self.staff("gone")
        self.due_task(gone, "2026-11-04", hours=2)
        self.sql("UPDATE users SET active = 0 WHERE id = ?", gone)
        self.assertIsNone(self.person(gone))

    def test_people_are_listed_busiest_first_with_counts(self):
        a, b = self.staff("alice"), self.staff("bob")
        self.sql("UPDATE users SET capacity_hours = 10 WHERE id = ?", b)
        self.due_task(a, "2026-11-04", hours=20)
        self.due_task(b, "2026-11-04", hours=11)
        d = self.client.get("/api/workload").get_json()
        names = [p["name"] for p in d["people"]]
        self.assertLess(names.index("bob"), names.index("alice"))   # 110 % before 67 %
        self.assertEqual((d["over"], d["heavy"], d["warn_pct"], d["capacity_default"]), (1, 0, 90, 30))


class CapacityTestCase(WorkloadBase):
    def test_a_personal_capacity_overrides_the_policy_and_blank_goes_back(self):
        priya = self.staff("priya")
        self.assertEqual(self.person(priya)["capacity"], 30)
        r = self.client.post(f"/users/{priya}/capacity", data={"capacity_hours": "12.5"}, headers=J)
        self.assertEqual(r.status_code, 200, r.get_data())
        p = self.person(priya)
        self.assertEqual((p["capacity"], p["custom_capacity"]), (12.5, True))
        self.assertEqual(self.audits("set_user_capacity"), 1)
        self.client.post(f"/users/{priya}/capacity", data={"capacity_hours": ""}, headers=J)
        p = self.person(priya)
        self.assertEqual((p["capacity"], p["custom_capacity"]), (30, False))
        self.assertEqual(self.audits("set_user_capacity"), 2)

    def test_capacity_is_validated_and_needs_manage_users(self):
        priya = self.staff("priya")
        for bad in ("0", "81", "abc", "-3"):
            r = self.client.post(f"/users/{priya}/capacity", data={"capacity_hours": bad}, headers=J)
            self.assertEqual(r.status_code, 400, bad)
        self.assertIsNone(self.sql("SELECT capacity_hours FROM users WHERE id = ?", priya)[0][0])
        c, csrf = self._api_client("priya", STRONG_PASSWORD)
        self.assertEqual(c.post(f"/users/{priya}/capacity", data={"capacity_hours": "5"}, headers={"X-CSRF-Token": csrf, **J}).status_code, 403)

    def test_thresholds_amber_over_90_red_over_100(self):
        priya = self.staff("priya")
        self.due_task(priya, "2026-11-04", hours=27)
        level = lambda: self.person(priya)["weeks"][0]["level"]   # noqa: E731
        self.assertEqual(level(), "ok")             # 90 % exactly is still fine
        self.due_task(priya, "2026-11-04", hours=1)
        self.assertEqual(level(), "warn")           # 28 of 30
        self.due_task(priya, "2026-11-04", hours=2)
        self.assertEqual(level(), "warn")           # 30 of 30: full, not over
        self.due_task(priya, "2026-11-04", hours=1)
        self.assertEqual(level(), "over")
        self._set_policy(workload_warn_pct="50")
        self.sql("DELETE FROM tasks")
        self.due_task(priya, "2026-11-04", hours=16)
        self.assertEqual(level(), "warn")           # the 90 % is a policy


class PickerAndWidgetTestCase(WorkloadBase):
    def test_the_picker_hint_is_the_hours_in_the_week_of_the_due_date(self):
        priya = self.staff("priya")
        self.due_task(priya, "2026-11-10", hours=6)
        self.due_task(priya, "2026-11-12", hours=28)
        d = self.client.get("/api/workload/week?date=2026-11-15").get_json()   # a Sunday: still the week of Mon 9 Nov
        self.assertEqual(d["week"], W1)
        self.assertEqual(d["people"][str(priya)], {"hours": 34, "capacity": 30, "level": "over"})
        self.assertEqual(self.client.get("/api/workload/week?date=2026-11-02").get_json()["people"][str(priya)]["hours"], 0)
        self.assertEqual(self.client.get("/api/workload/week").get_json()["week"], W0)   # default: this week
        self.assertEqual(self.client.get("/api/workload/week?date=soon").status_code, 400)

    def test_staff_who_view_people_see_it_partners_and_anonymous_do_not(self):
        c, _ = self._api_client("admin", "changeme")
        for url in ("/api/workload", "/api/workload/week", "/people/workload"):
            self.assertEqual(c.get(url).status_code, 200, url)
        viewer = self.staff("vera", "Viewer")
        vc, _ = self._api_client("vera", STRONG_PASSWORD)
        self.assertEqual(vc.get("/api/workload").status_code, 200)   # Viewers may view People
        self._invite(1, "ann@acme.example", "Customer", "Ann")
        ext = self._external_client("ann@acme.example")
        for url in ("/api/workload", "/api/workload/week", "/people/workload"):
            self.assertEqual(ext.get(url).status_code, 403, url)
        import app as app_module
        anon = app_module.app.test_client()
        self.assertEqual(anon.get("/api/workload").status_code, 401)

    def test_the_widget_is_in_the_catalogue_validated_and_carries_the_numbers(self):
        priya = self.staff("priya")
        self.due_task(priya, "2026-11-04", hours=3)
        d = self.client.get("/api/dashboard").get_json()
        self.assertIn("workload", [w["id"] for w in d["catalogue"]])
        w = d["data"]["workload"]
        self.assertEqual(w["weeks"], [W0, W1, W2, W3])
        self.assertEqual(next(p for p in w["people"] if p["id"] == priya)["weeks"][0]["hours"], 3)
        from services.dashboard import normalize_layout
        lay = normalize_layout([{"id": "workload", "w": 9, "settings": {"limit": 99}}, {"id": "workload", "w": 1}])
        self.assertEqual(lay, [{"id": "workload", "w": 3, "settings": {"limit": 20}}])   # clamped, once
        self.assertEqual(normalize_layout([{"id": "workload", "settings": {"limit": "x"}}])[0]["settings"]["limit"], 6)
        r = self.client.put("/api/dashboard/layout", json={"layout": [{"id": "workload", "w": 2}]}, headers={"X-CSRF-Token": self.csrf})
        self.assertEqual(r.status_code, 200, r.get_json())
        self.assertEqual(self.client.get("/api/dashboard").get_json()["layout"][0]["id"], "workload")


class HandOverTestCase(WorkloadBase):
    def setUp(self):
        super().setUp()
        self.new_project(name="Beta"); self.new_project(name="Done")
        self.sql("UPDATE projects SET stage = ? WHERE id = 3", self.stages(3)[-1])
        self.leaver, self.heir = self.staff("lee"), self.staff("hana")
        self.sql("UPDATE projects SET owner_id = ? WHERE id IN (1, 3)", self.leaver)
        self.sql("DELETE FROM project_participants WHERE project_id IN (1, 3)")   # the PM row follows the owner, as the edit page keeps it
        for pid in (1, 3):
            self.sql("INSERT INTO project_participants (project_id, user_id, role, added_at) VALUES (?, ?, 'Project manager', 'n')", pid, self.leaver)
        self.due_task(self.leaver, "2026-11-05", title="One")
        self.due_task(self.leaver, None, title="Two", pid=2)
        self.due_task(self.leaver, "2026-11-05", title="Finished", done=1)
        self.due_task(self.leaver, "2026-11-05", title="On closed", pid=3)
        for kind, status, pid in (("risk", "open", 1), ("issue", "closed", 1), ("decision", "decided", 2), ("blocker", "open", 2)):
            self.sql("INSERT INTO raid_items (project_id, kind, title, status, owner_id, created_by, created_at, updated_at) VALUES (?, ?, 'R', ?, ?, 't', 'n', 'n')",
                     pid, kind, status, self.leaver)

    def deactivate(self, who=None, to=None, client=None):
        fields = {"active": "0", **({"handover_to": str(to)} if to is not None else {})}
        return (client or self.client).post(f"/users/{who or self.leaver}/active", data=fields, headers=J)

    def owned(self, uid):
        return {
            "tasks": self.sql("SELECT COUNT(*) FROM tasks WHERE assignee_id = ? AND done = 0", uid)[0][0],
            "rollouts": [r[0] for r in self.sql("SELECT id FROM projects WHERE owner_id = ? ORDER BY id", uid)],
            "raid": self.sql("SELECT COUNT(*) FROM raid_items WHERE owner_id = ?", uid)[0][0],
        }

    def test_the_users_list_says_what_each_person_holds(self):
        users = {u["id"]: u for u in self.client.get("/api/users").get_json()["users"]}
        self.assertEqual(users[self.leaver]["holds"], {"tasks": 2, "rollouts": 1, "raid": 2})   # open work on live, open rollouts only
        self.assertEqual(users[self.heir]["holds"], {"tasks": 0, "rollouts": 0, "raid": 0})

    def test_it_moves_tasks_rollouts_and_raid_in_one_audited_step(self):
        r = self.deactivate(to=self.heir)
        self.assertEqual(r.status_code, 200, r.get_data())
        self.assertIn("handed over to hana: 2 open tasks, 1 rollout, 2 RAID items", " ".join(r.get_json()["messages"]))
        self.assertEqual(self.sql("SELECT active FROM users WHERE id = ?", self.leaver)[0][0], 0)
        self.assertEqual(self.owned(self.heir), {"tasks": 2, "rollouts": [1], "raid": 2})
        # what is closed or finished stays on the record under the person it was theirs
        self.assertEqual(self.owned(self.leaver), {"tasks": 1, "rollouts": [3], "raid": 2})
        self.assertEqual(self.sql("SELECT COUNT(*) FROM tasks WHERE assignee_id = ? AND done = 1", self.leaver)[0][0], 1)
        # the new manager is the rollout's PM, the old one stays on as a coordinator
        roles = dict(self.sql("SELECT user_id, role FROM project_participants WHERE project_id = 1"))
        self.assertEqual((roles[self.heir], roles[self.leaver]), ("Project manager", "Coordinator"))
        rows = self.sql("SELECT details FROM audit_logs WHERE action = 'set_user_active'")
        self.assertEqual(len(rows), 1)
        self.assertIn("handed over to hana: 2 open tasks, 1 rollout, 2 RAID items", rows[0][0])

    def test_a_failure_half_way_leaves_everything_as_it_was(self):
        before = (self.owned(self.leaver), self.owned(self.heir))
        with mock.patch("routes.users.set_project_manager", side_effect=RuntimeError("boom")):
            try:
                r = self.deactivate(to=self.heir)
                self.assertEqual(r.status_code, 500)
            except RuntimeError:
                pass   # a testing app lets the error through
        self.assertEqual(self.sql("SELECT active FROM users WHERE id = ?", self.leaver)[0][0], 1)
        self.assertEqual((self.owned(self.leaver), self.owned(self.heir)), before)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM notifications WHERE user_id = ?", self.heir)[0][0], 0)

    def test_the_new_owner_is_told(self):
        self.deactivate(to=self.heir)
        n = self.sql("SELECT kind, title, body, link FROM notifications WHERE user_id = ?", self.heir)
        self.assertEqual(len(n), 1)
        self.assertEqual(n[0][0], "assigned")
        self.assertIn("2 open tasks", n[0][2]); self.assertIn("Alpha", n[0][2]); self.assertIn("2 RAID items", n[0][2])
        self.assertEqual(n[0][3], "/my-work")

    def test_without_a_target_it_is_the_old_deactivate_and_nothing_moves(self):
        self.assertEqual(self.deactivate().status_code, 200)
        self.assertEqual(self.owned(self.leaver), {"tasks": 3, "rollouts": [1, 3], "raid": 4})
        self.assertEqual(self.sql("SELECT COUNT(*) FROM notifications WHERE user_id = ?", self.heir)[0][0], 0)

    def test_it_refuses_an_inactive_external_pending_or_the_same_account_and_changes_nothing(self):
        before = (self.owned(self.leaver), self.owned(self.heir))
        sleepy = self.staff("sam")
        self.sql("UPDATE users SET active = 0 WHERE id = ?", sleepy)
        waiting = self.staff("wen")
        self.sql("UPDATE users SET pending = 1 WHERE id = ?", waiting)
        self.sql("INSERT INTO users (username, password_hash, name, role, active, kind) VALUES ('ext@x.com', 'x', 'Ext', 'External', 1, 'external')")
        ext = self.sql("SELECT id FROM users WHERE username = 'ext@x.com'")[0][0]
        for target in (sleepy, waiting, ext, self.leaver, 9999):
            r = self.deactivate(to=target)
            self.assertEqual(r.status_code, 400, target)
        self.assertEqual(self.sql("SELECT active FROM users WHERE id = ?", self.leaver)[0][0], 1)   # still active: the whole step was refused
        self.assertEqual((self.owned(self.leaver), self.owned(self.heir)), before)
        self.assertEqual(self.audits("set_user_active"), 0)

    def test_a_hand_over_is_only_for_leaving_and_a_manager_must_be_able_to_manage(self):
        self.sql("UPDATE users SET active = 0 WHERE id = ?", self.leaver)
        self.assertEqual(self.client.post(f"/users/{self.leaver}/active", data={"active": "1", "handover_to": str(self.heir)}, headers=J).status_code, 400)
        self.sql("UPDATE users SET active = 1 WHERE id = ?", self.leaver)
        viewer = self.staff("vic", "Viewer")
        r = self.deactivate(to=viewer)   # he holds a rollout and a Viewer cannot manage it
        self.assertEqual(r.status_code, 400)
        self.assertIn("cannot manage rollouts", r.get_json()["error"])
        self.assertEqual(self.owned(self.leaver)["rollouts"], [1, 3])
        # with no rollout to move, anyone active on staff may take the tasks
        self.sql("UPDATE projects SET owner_id = 1 WHERE owner_id = ?", self.leaver)
        self.assertEqual(self.deactivate(to=viewer).status_code, 200)
        self.assertEqual(self.owned(viewer)["tasks"], 2)

    def test_needs_manage_users_and_an_admin_account_stays_an_admins_to_deactivate(self):
        c, csrf = self._api_client("hana", STRONG_PASSWORD)
        self.assertEqual(self.deactivate(client=c).status_code, 403)
        self.assertEqual(self.sql("SELECT active FROM users WHERE id = ?", self.leaver)[0][0], 1)
