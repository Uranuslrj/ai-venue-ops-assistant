"""Isolated HTTP smoke test; it copies the app and CSV fixtures to a temp dir."""
import json
import csv
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import date, timedelta
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parent
CSV_FILES = ["dm_profile_template.csv", "player_requirement_weights.csv", "script_catalog.csv",
             "session_records.csv", "feedback_records.csv", "recommendation_records.csv",
             "ai_feedback_results.csv", "improvement_records.csv"]

def post_or_get(url, payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    req = Request(url, data=data, headers={"Content-Type": "application/json"} if data else {})
    try:
        with urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read().decode())
    except HTTPError as e:
        return e.code, json.loads(e.read().decode())

class FlowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="script-kill-flow-")
        cls.work = Path(cls.temp.name)
        shutil.copy2(ROOT / "app.py", cls.work / "app.py")
        shutil.copytree(ROOT / "rag", cls.work / "rag")
        shutil.copytree(ROOT / "rag_knowledge", cls.work / "rag_knowledge")
        for name in CSV_FILES:
            shutil.copy2(ROOT / name, cls.work / name)
        # Clear historical feedback from the isolated fixture so assertions measure only this run.
        for name in ("feedback_records.csv", "ai_feedback_results.csv", "improvement_records.csv"):
            path = cls.work / name
            with path.open("r", encoding="utf-8-sig", newline="") as source:
                header = next(csv.reader(source), [])
            with path.open("w", encoding="utf-8-sig", newline="") as target:
                csv.writer(target).writerow(header)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            cls.port = sock.getsockname()[1]
        env = os.environ.copy()
        env["PORT"] = str(cls.port)
        for k in ("OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_MODEL", "AI_PROVIDER"):
            env.pop(k, None)
        cls.proc = subprocess.Popen([sys.executable, str(cls.work / "app.py")], cwd=cls.work, env=env,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cls.base = f"http://127.0.0.1:{cls.port}"
        for _ in range(60):
            try:
                if post_or_get(cls.base + "/api/dashboard")[0] == 200:
                    break
            except Exception:
                time.sleep(.15)
        else:
            raise RuntimeError("isolated server did not start")

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate()
        try:
            cls.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            cls.proc.kill()
            cls.proc.wait(timeout=5)
        cls.temp.cleanup()

    def test_rag_retrieval_grounding_and_fallback(self):
        cases = json.loads((ROOT / "rag" / "evaluation_cases.json").read_text(encoding="utf-8"))
        by_id = {case["case_id"]: case for case in cases}
        relevant = by_id["EVAL-001"]["query"]
        code, result = post_or_get(self.base + "/api/rag?" + urlencode({"query": relevant, "top_k": 3}))
        self.assertEqual(code, 200)
        self.assertTrue(result["grounded"])
        self.assertTrue(result["citations"])
        self.assertTrue(any(x["source"] == "dm_service_sop.md" for x in result["results"]))
        unrelated = by_id["EVAL-004"]["query"]
        code, result = post_or_get(self.base + "/api/rag?" + urlencode({"query": unrelated}))
        self.assertEqual(code, 200)
        self.assertFalse(result["grounded"])
        self.assertFalse(result["results"])
        self.assertIn("人工复核", result["fallback"])
        positive = by_id["EVAL-005"]["query"]
        code, result = post_or_get(self.base + "/api/rag?" + urlencode({"query": positive}))
        self.assertEqual(code, 200)
        self.assertTrue(result["grounded"])
        self.assertFalse(result["create_improvement"])

    def test_session_to_advice(self):
        code, dash = post_or_get(self.base + "/api/dashboard")
        self.assertEqual(code, 200)
        script = next(s for s in dash["scripts"] if s.get("status") == "启用")
        weekdays = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")
        slot = None
        for offset in range(1, 15):
            d = date.today() + timedelta(days=offset)
            for dm in dash["dms"]:
                hostable = {x.strip() for x in dm.get("hostable_scripts", "").replace("，", ",").split(",")}
                days = {x.strip() for x in dm.get("available_days", "").replace("，", ",").split(",")}
                times = [x.strip() for x in dm.get("available_time_slots", "").replace("，", ",").split(",") if x.strip()]
                if dm.get("available_status") == "可用" and script["script_name"] in hostable and weekdays[d.weekday()] in days and times:
                    slot = (d.strftime("%Y-%m-%d"), times[0].split("-")[0], dm)
                    break
            if slot:
                break
        self.assertIsNotNone(slot, "no matching future DM availability")
        session_date, session_time, _ = slot
        code, created = post_or_get(self.base + "/api/session", {"action":"create", "script_id":script["script_id"],
            "session_date":session_date, "session_time":session_time, "player_count":"6", "room_id":"R-E2E",
            "scenario_name":"E2E流程验证"})
        self.assertEqual(code, 200, created)
        sid, rid = created["session_id"], created["request_id"]

        # A cancelled session stays in history but cannot enter the recommendation flow.
        cancel_code, cancel_created = post_or_get(self.base + "/api/session", {"action":"create", "script_id":script["script_id"],
            "session_date":session_date, "session_time":session_time, "player_count":"6", "room_id":"R-CANCEL", "scenario_name":"E2E取消场次验证"})
        self.assertEqual(cancel_code, 200, cancel_created)
        cancel_id, cancel_request_id = cancel_created["session_id"], cancel_created["request_id"]
        cancel_code, cancelled = post_or_get(self.base + "/api/session", {"action":"cancel", "session_id":cancel_id})
        self.assertEqual(cancel_code, 200, cancelled)
        cancel_code, cancel_recommend = post_or_get(self.base + f"/api/recommend?request_id={cancel_request_id}")
        self.assertEqual(cancel_code, 400, cancel_recommend)
        self.assertIn("已取消", cancel_recommend["error"])
        cancel_code, cancel_dashboard = post_or_get(self.base + "/api/dashboard")
        cancelled_row = next(x for x in cancel_dashboard["sessions"] if x["session_id"] == cancel_id)
        self.assertEqual(cancelled_row["session_status"], "已取消")
        code, rec = post_or_get(self.base + f"/api/recommend?request_id={rid}")
        self.assertEqual(code, 200, rec)
        eligible = [r for r in rec["results"] if r["hard_filter_result"] == "通过"]
        self.assertTrue(eligible, "no recommended eligible DM")
        dm = eligible[0]["dm_id"]
        status, transition_error = post_or_get(self.base + "/api/session", {"action":"start", "session_id":sid})
        self.assertEqual(status, 400, transition_error)
        status, transition_error = post_or_get(self.base + "/api/session", {"action":"finish", "session_id":sid})
        self.assertEqual(status, 400, transition_error)
        for action, extra in [("assign", {"dm_id":dm}), ("start", {}), ("finish", {})]:
            code, result = post_or_get(self.base + "/api/session", {"action":action, "session_id":sid, **extra})
            self.assertEqual(code, 200, result)
        # Feedback must reference the DM actually assigned to the session.
        other_dm = next(x["dm_id"] for x in dash["dms"] if x["dm_id"] != dm)
        status, mismatched = post_or_get(self.base + "/api/feedback", {
            "session_id":sid,"dm_id":other_dm,"player_id":"E2E-WRONG-DM",
            "rule_explanation_rating":"3","script_pace_rating":"3","humor_comedy_rating":"3",
            "performance_immersion_rating":"3","on_site_adaptability_rating":"3","service_attitude_rating":"3",
            "comment_text":"测试DM关联校验。"})
        self.assertEqual(status, 400, mismatched)

        feedback_ids = []
        comment = "玩家多次表示规则没有听清，DM没有及时停下来重新解释，导致后续机制理解困难。"
        for player in ("E2E-P01", "E2E-P02"):
            code, result = post_or_get(self.base + "/api/feedback", {"session_id":sid,"dm_id":dm,"player_id":player,
                "rule_explanation_rating":"2","script_pace_rating":"3","humor_comedy_rating":"4",
                "performance_immersion_rating":"3","on_site_adaptability_rating":"2","service_attitude_rating":"4",
                "comment_text":comment})
            self.assertEqual(code, 200, result)
            feedback_ids.append(result["feedback_id"])
        status, after_feedback = post_or_get(self.base + "/api/dashboard")
        self.assertEqual(status, 200)
        refreshed_dm = next(x for x in after_feedback["dms"] if x["dm_id"] == dm)
        self.assertEqual(refreshed_dm["total_review_count"], "2")
        self.assertAlmostEqual(float(refreshed_dm["rule_explanation"]), (2 * 2 + 5 * 3.8) / 7, places=3)
        self.assertEqual(refreshed_dm["last_30d_review_count"], "2")
        code, result = post_or_get(self.base + "/api/analyze", {})
        self.assertEqual(code, 200, result)
        self.assertGreaterEqual(result["analyzed"], 2)
        self.assertEqual(result["mode"], "local")
        code, dash = post_or_get(self.base + "/api/dashboard")
        self.assertEqual(code, 200)
        reviews = [r for r in dash["reviews"] if r["feedback_id"] in feedback_ids]
        self.assertEqual(len(reviews), 2)
        status, before_review = post_or_get(self.base + "/api/aggregate")
        self.assertEqual(status, 200, before_review)
        self.assertEqual(before_review["groups"], [], "pending analyses must not aggregate before manager review")
        for r in reviews:
            self.assertEqual(r["issue_dimension"], "规则讲解")
            self.assertEqual(r["severity"], "高")
            code, saved = post_or_get(self.base + "/api/review", {"ai_result_id":r["ai_result_id"],
                "manager_severity":"高","manager_correction":"E2E复核确认","ai_status":"已确认"})
            self.assertEqual(code, 200, saved)
        code, agg = post_or_get(self.base + "/api/aggregate")
        self.assertEqual(code, 200, agg)
        group = next((x for x in agg["groups"] if x["dm_id"] == dm and x["issue_type"] == "规则讲解不充分"), None)
        self.assertIsNotNone(group, "issue group missing")
        self.assertEqual(group["count"], "2")
        self.assertTrue(group["triggered"], "high severity x2 did not trigger")
        code, dash = post_or_get(self.base + "/api/dashboard")
        tasks = [x for x in dash["improvements"] if x["dm_id"] == dm and x["issue_type"] == "规则讲解不充分"]
        self.assertTrue(tasks, "improvement task missing")
        self.assertEqual(tasks[0]["status"], "待店长复核")
        self.assertEqual(tasks[0]["source_review_count"], "2")
        self.assertIn("高严重度累计2次", tasks[0]["trigger_rule"])

        # A rejected follow-up must not be reclassified or counted by aggregation.
        status, rejected_followup = post_or_get(self.base + "/api/feedback", {
            "session_id":sid,"dm_id":dm,"player_id":"E2E-P03",
            "rule_explanation_rating":"2","script_pace_rating":"3","humor_comedy_rating":"4",
            "performance_immersion_rating":"3","on_site_adaptability_rating":"2","service_attitude_rating":"4",
            "comment_text":comment})
        self.assertEqual(status, 200, rejected_followup)
        status, analyzed = post_or_get(self.base + "/api/analyze", {})
        self.assertEqual(status, 200, analyzed)
        status, dash = post_or_get(self.base + "/api/dashboard")
        rejected_row = next(x for x in dash["reviews"] if x["feedback_id"] == rejected_followup["feedback_id"])
        status, rejected = post_or_get(self.base + "/api/review", {
            "ai_result_id":rejected_row["ai_result_id"],"manager_severity":"",
            "manager_correction":"E2E驳回测试","ai_status":"已驳回"})
        self.assertEqual(status, 200, rejected)
        status, after_reject = post_or_get(self.base + "/api/aggregate")
        group = next(x for x in after_reject["groups"] if x["dm_id"] == dm and x["issue_type"] == "规则讲解不充分")
        self.assertEqual(group["count"], "2", "rejected analysis must not be reclassified into the group")
        status, dash = post_or_get(self.base + "/api/dashboard")
        tasks = [x for x in dash["improvements"] if x["dm_id"] == dm and x["issue_type"] == "规则讲解不充分"]
        self.assertEqual(len(tasks), 1, "rerunning aggregation should not duplicate an open advice task")

        # Three low-severity instances stay below threshold; the fourth triggers.
        pace_feedback_ids = []
        for index in range(3):
            status, result = post_or_get(self.base + "/api/feedback", {
                "session_id":sid,"dm_id":dm,"player_id":f"E2E-L{index+1}",
                "rule_explanation_rating":"4","script_pace_rating":"2","humor_comedy_rating":"4",
                "performance_immersion_rating":"4","on_site_adaptability_rating":"4","service_attitude_rating":"4",
                "comment_text":"中间节奏稍慢，等待时间偏长。"})
            self.assertEqual(status, 200, result)
            pace_feedback_ids.append(result["feedback_id"])
        status, analyzed = post_or_get(self.base + "/api/analyze", {})
        self.assertEqual(status, 200, analyzed)
        status, dash = post_or_get(self.base + "/api/dashboard")
        pace_reviews = [x for x in dash["reviews"] if x["feedback_id"] in pace_feedback_ids]
        self.assertEqual(len(pace_reviews), 3)
        for review in pace_reviews:
            self.assertEqual(review["severity"], "低")
            status, saved = post_or_get(self.base + "/api/review", {
                "ai_result_id":review["ai_result_id"],"manager_severity":"低",
                "manager_correction":"E2E低严重度阈值测试","ai_status":"已确认"})
            self.assertEqual(status, 200, saved)
        status, low_agg = post_or_get(self.base + "/api/aggregate")
        low_group = next(x for x in low_agg["groups"] if x["dm_id"] == dm and x["issue_type"] == "中段推进偏慢")
        self.assertEqual(low_group["severity_counts"], {"高":0,"中":0,"低":3})
        self.assertFalse(low_group["triggered"], "three low-severity instances must not trigger")

        status, fourth = post_or_get(self.base + "/api/feedback", {
            "session_id":sid,"dm_id":dm,"player_id":"E2E-L4",
            "rule_explanation_rating":"4","script_pace_rating":"2","humor_comedy_rating":"4",
            "performance_immersion_rating":"4","on_site_adaptability_rating":"4","service_attitude_rating":"4",
            "comment_text":"中间节奏稍慢，等待时间偏长。"})
        self.assertEqual(status, 200, fourth)
        status, analyzed = post_or_get(self.base + "/api/analyze", {})
        self.assertEqual(status, 200, analyzed)
        status, dash = post_or_get(self.base + "/api/dashboard")
        fourth_review = next(x for x in dash["reviews"] if x["feedback_id"] == fourth["feedback_id"])
        status, saved = post_or_get(self.base + "/api/review", {
            "ai_result_id":fourth_review["ai_result_id"],"manager_severity":"低",
            "manager_correction":"E2E第四条低严重度测试","ai_status":"已确认"})
        self.assertEqual(status, 200, saved)
        status, low_agg = post_or_get(self.base + "/api/aggregate")
        low_group = next(x for x in low_agg["groups"] if x["dm_id"] == dm and x["issue_type"] == "中段推进偏慢")
        self.assertEqual(low_group["severity_counts"], {"高":0,"中":0,"低":4})
        self.assertTrue(low_group["triggered"], "four low-severity instances should trigger")
        status, final_dash = post_or_get(self.base + "/api/dashboard")
        low_tasks = [x for x in final_dash["improvements"] if x["dm_id"] == dm and x["issue_type"] == "中段推进偏慢"]
        self.assertTrue(low_tasks, "low-severity advice task missing")

if __name__ == "__main__":
    unittest.main(verbosity=2)






