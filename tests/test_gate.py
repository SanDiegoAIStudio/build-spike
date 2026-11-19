import json
import os
import unittest

import support  # noqa: F401  (sets the import path)
import gate


def plan(**changes):
    base = {"title": "an idea", "cheapness": 85, "stakes": "low", "action": "parse a table into json locally"}
    base.update(changes)
    return base


class GateTests(unittest.TestCase):
    def test_cheap_low_stakes_idea_may_build_whatever_else_the_plan_says(self):
        ok, why = gate.decide(plan(score=31, params="build a parser"))
        self.assertTrue(ok, why)

    def test_expensive_first_version_is_rejected(self):
        ok, why = gate.decide(plan(cheapness=40, action="x"))
        self.assertFalse(ok)
        self.assertIn("cheap", why)
        self.assertEqual(why, "first version is not cheap enough (cheapness 40 < 70)")

    def test_high_stakes_is_rejected(self):
        ok, why = gate.decide(plan(stakes="high", action="x"))
        self.assertFalse(ok)
        self.assertIn("high stakes", why)
        self.assertEqual(why, "high stakes")

    def test_missing_cheapness_is_rejected_not_crashed(self):
        ok, why = gate.decide({"stakes": "low", "action": "x"})
        self.assertFalse(ok)
        self.assertEqual(why, "no usable cheapness (expected a whole number from 0 to 100)")

    def test_a_plan_that_is_not_an_object_is_rejected(self):
        for bad in (None, [], "plan", 5):
            ok, why = gate.decide(bad)
            self.assertFalse(ok)
            self.assertIn("no usable cheapness", why)

    def test_forbidden_action_categories_are_rejected(self):
        for action, label in [("buy the domain and pay for a year", "money"),
                              ("send the email to the list", "outward"),
                              ("deploy to production", "production"),
                              ("rotate the api key", "credentials")]:
            ok, why = gate.decide(plan(action=action))
            self.assertFalse(ok, "%s should be blocked: %s" % (label, action))

    def test_each_forbidden_category_gives_its_own_reason(self):
        cases = [
            ("pay the invoice", "planned action spends money"),
            ("subscribe to the newsletter", "planned action spends money"),
            ("email the report to the team", "planned action sends something outward"),
            ("post the draft out", "planned action sends something outward"),
            ("convert text to json", "planned action sends something outward"),
            ("deploy the build", "planned action touches production"),
            ("read the customer data", "planned action touches production"),
            ("store the password in a file", "planned action touches credentials"),
            ("log in with oauth", "planned action touches credentials"),
            ("drop table users", "planned action destructive"),
            ("clean up with rm -rf build", "planned action destructive"),
        ]
        for action, reason in cases:
            self.assertEqual(gate.decide(plan(action=action)), (False, reason), action)

    def test_the_forbidden_list_has_five_categories_in_order(self):
        self.assertEqual([reason for _, reason in gate.FORBIDDEN],
                         ["spends money", "sends something outward", "touches production",
                          "touches credentials", "destructive"])

    def test_the_first_matching_category_decides(self):
        ok, why = gate.decide(plan(action="pay and then deploy it"))
        self.assertEqual(why, "planned action spends money")

    def test_forbidden_words_match_in_capitals(self):
        self.assertEqual(gate.decide(plan(action="BUY the domain")), (False, "planned action spends money"))

    def test_gate_reads_the_action_not_the_idea(self):
        ok, _ = gate.decide(plan(title="Charge customers: buy, pay, invoice, send the email, rotate the password",
                                 action="parse the pricing table into json locally"))
        self.assertTrue(ok)

    def test_nothing_but_the_three_fields_is_read(self):
        ok, _ = gate.decide(plan(notes="deploy to production and buy a domain", params="drop table users"))
        self.assertTrue(ok)

    def test_cheapness_must_be_a_whole_number_from_0_to_100(self):
        message = "no usable cheapness (expected a whole number from 0 to 100)"
        for bad in (True, False, 85.0, 85.5, "85", None, 101, -1, [85], {"n": 85}):
            self.assertEqual(gate.decide(plan(cheapness=bad)), (False, message), repr(bad))

    def test_cheapness_equal_to_the_threshold_passes(self):
        self.assertTrue(gate.decide(plan(cheapness=70))[0])
        self.assertEqual(gate.decide(plan(cheapness=69)),
                         (False, "first version is not cheap enough (cheapness 69 < 70)"))

    def test_the_threshold_can_be_changed(self):
        self.assertTrue(gate.decide(plan(cheapness=50), threshold=50)[0])
        self.assertFalse(gate.decide(plan(cheapness=50), threshold=51)[0])
        self.assertEqual(gate.DEFAULT_THRESHOLD, 70)

    def test_cheapness_100_and_0_are_in_range(self):
        self.assertTrue(gate.decide(plan(cheapness=100))[0])
        self.assertTrue(gate.decide(plan(cheapness=0), threshold=0)[0])

    def test_missing_and_unknown_stakes_are_rejected(self):
        message = "no usable stakes (expected low, medium or high)"
        for bad in (None, "", "none", "very high", 3, True, ["low"]):
            self.assertEqual(gate.decide(plan(stakes=bad)), (False, message), repr(bad))
        no_stakes = plan()
        del no_stakes["stakes"]
        self.assertEqual(gate.decide(no_stakes), (False, message))

    def test_stakes_are_read_without_regard_to_case(self):
        self.assertEqual(gate.decide(plan(stakes="HIGH")), (False, "high stakes"))
        ok, why = gate.decide(plan(stakes="Medium"))
        self.assertTrue(ok)
        self.assertIn("medium stakes", why)

    def test_an_empty_or_missing_action_is_rejected(self):
        message = "no planned action to screen"
        for bad in ("", "   ", "\n\t", None, 5, ["buy"]):
            self.assertEqual(gate.decide(plan(action=bad)), (False, message), repr(bad))
        no_action = plan()
        del no_action["action"]
        self.assertEqual(gate.decide(no_action), (False, message))

    def test_the_checks_run_in_order(self):
        everything_wrong = {"cheapness": 5, "stakes": "high", "action": "buy it"}
        self.assertIn("cheap", gate.decide(everything_wrong)[1])
        self.assertEqual(gate.decide(dict(everything_wrong, cheapness=90))[1], "high stakes")
        self.assertEqual(gate.decide(dict(everything_wrong, cheapness=90, stakes="low"))[1],
                         "planned action spends money")
        self.assertIn("no usable stakes", gate.decide({"cheapness": 90, "action": ""})[1])

    def test_the_success_message_names_the_numbers(self):
        self.assertEqual(gate.decide(plan(cheapness=85, stakes="LOW")),
                         (True, "cheap first version (85), low stakes, no forbidden step in the planned action"))

    def test_ordinary_wordings_of_each_forbidden_category_are_rejected(self):
        """source: plurals, past forms and close wordings still ask, with that category's reason."""
        cases = [
            ("buy domains for the test", "planned action spends money"),
            ("purchased a plan for the team", "planned action spends money"),
            ("paying the vendor", "planned action spends money"),
            ("renew the subscription", "planned action spends money"),
            ("add a credit card", "planned action spends money"),
            ("send emails to customers", "planned action sends something outward"),
            ("sends the digest", "planned action sends something outward"),
            ("sending it to the list", "planned action sends something outward"),
            ("email customers the link", "planned action sends something outward"),
            ("publish the page", "planned action sends something outward"),
            ("tweet the result", "planned action sends something outward"),
            ("dm the founder", "planned action sends something outward"),
            ("deploys the fix", "planned action touches production"),
            ("deploying the site", "planned action touches production"),
            ("push to prod", "planned action touches production"),
            ("read passwords from the vault", "planned action touches credentials"),
            ("use api keys", "planned action touches credentials"),
            ("copy the tokens", "planned action touches credentials"),
            ("store credentials in a file", "planned action touches credentials"),
            ("sign in to the dashboard", "planned action touches credentials"),
            ("delete the folder", "planned action destructive"),
            ("deletes the old rows", "planned action destructive"),
            ("rm -fr build", "planned action destructive"),
            ("rm -r build", "planned action destructive"),
            ("rm -r -f build", "planned action destructive"),
            ("git push --force", "planned action destructive"),
            ("force-push the branch", "planned action destructive"),
            ("force push the branch", "planned action destructive"),
            ("wipe the disk", "planned action destructive"),
            ("drop the database", "planned action destructive"),
        ]
        for action, reason in cases:
            self.assertEqual(gate.decide(plan(action=action)), (False, reason), action)

    def test_harmless_local_actions_still_build(self):
        """source: local parsing, counting and pricing stay cheap enough to build."""
        reason = "cheap first version (85), low stakes, no forbidden step in the planned action"
        for action in ("parse a table into json locally",
                       "parse a file locally",
                       "parse the saved pricing tables into json locally",
                       "parse the pricing table into json locally",
                       "summarize the notes into a markdown file",
                       "count the rows in the csv",
                       "draw a chart of the counts",
                       "write the results to out.json"):
            self.assertEqual(gate.decide(plan(action=action)), (True, reason), action)

    def test_ordinary_money_send_push_and_remove_wordings_ask(self):
        """source: charge, notify, phone, git push and remove ask with their own reason."""
        base = {"cheapness": 90, "stakes": "low"}
        cases = [
            ("charge the customer's card", "planned action spends money"),
            ("refund the order", "planned action spends money"),
            ("wire funds to the vendor", "planned action spends money"),
            ("transfer money to savings", "planned action spends money"),
            ("donate to the fund", "planned action spends money"),
            ("notify the list", "planned action sends something outward"),
            ("upload the build", "planned action sends something outward"),
            ("message the client", "planned action sends something outward"),
            ("mail the report", "planned action sends something outward"),
            ("share the doc with the team", "planned action sends something outward"),
            ("invite users", "planned action sends something outward"),
            ("submit the form", "planned action sends something outward"),
            ("call the customer", "planned action sends something outward"),
            ("phone the lead", "planned action sends something outward"),
            ("phoned the lead", "planned action sends something outward"),
            ("dial the office", "planned action sends something outward"),
            ("leave a voicemail", "planned action sends something outward"),
            ("git push the branch", "planned action touches production"),
            ("push to origin", "planned action touches production"),
            ("push to main", "planned action touches production"),
            ("remove the old folder", "planned action destructive"),
            ("overwrite the config", "planned action destructive"),
        ]
        for action, reason in cases:
            self.assertEqual(gate.decide(dict(base, action=action)), (False, reason), action)

    def test_close_wordings_sample_plans_and_named_actions_keep_their_answers(self):
        """source: wire up, call the parser, the sample plans and every action already named keep their answer."""
        build = (True, "cheap first version (90), low stakes, no forbidden step in the planned action")
        money = (False, "planned action spends money")
        outward = (False, "planned action sends something outward")
        production = (False, "planned action touches production")
        credentials = (False, "planned action touches credentials")
        destructive = (False, "planned action destructive")
        no_action = (False, "no planned action to screen")
        cases = [
            ("wire up the parser", build),
            ("call the parser on the sample", build),
            ("parse the log file", build),
            ("count the rows by kind", build),
            ("draft the summary in a local file", build),
            ("rename the columns", build),
            ("x", build),
            ("parse a table into json locally", build),
            ("parse a file locally", build),
            ("parse the saved pricing tables into json locally", build),
            ("parse the pricing table into json locally", build),
            ("summarize the notes into a markdown file", build),
            ("count the rows in the csv", build),
            ("draw a chart of the counts", build),
            ("write the results to out.json", build),
            ("", no_action),
            ("   ", no_action),
            ("\n\t", no_action),
            ("buy the domain and pay for a year", money),
            ("pay the invoice", money),
            ("subscribe to the newsletter", money),
            ("pay and then deploy it", money),
            ("BUY the domain", money),
            ("buy it", money),
            ("buy domains for the test", money),
            ("purchased a plan for the team", money),
            ("paying the vendor", money),
            ("renew the subscription", money),
            ("add a credit card", money),
            ("send the email to the list", outward),
            ("email the report to the team", outward),
            ("post the draft out", outward),
            ("convert text to json", outward),
            ("send emails to customers", outward),
            ("sends the digest", outward),
            ("sending it to the list", outward),
            ("email customers the link", outward),
            ("publish the page", outward),
            ("tweet the result", outward),
            ("dm the founder", outward),
            ("deploy to production", production),
            ("deploy the build", production),
            ("read the customer data", production),
            ("deploys the fix", production),
            ("deploying the site", production),
            ("push to prod", production),
            ("rotate the api key", credentials),
            ("store the password in a file", credentials),
            ("log in with oauth", credentials),
            ("read passwords from the vault", credentials),
            ("use api keys", credentials),
            ("copy the tokens", credentials),
            ("store credentials in a file", credentials),
            ("sign in to the dashboard", credentials),
            ("drop table users", destructive),
            ("clean up with rm -rf build", destructive),
            ("delete the folder", destructive),
            ("deletes the old rows", destructive),
            ("rm -fr build", destructive),
            ("rm -r build", destructive),
            ("rm -r -f build", destructive),
            ("git push --force", destructive),
            ("force-push the branch", destructive),
            ("force push the branch", destructive),
            ("wipe the disk", destructive),
            ("drop the database", destructive),
        ]
        base = {"cheapness": 90, "stakes": "low"}
        for action, answer in cases:
            self.assertEqual(gate.decide(dict(base, action=action)), answer, action)
        plans = {
            "plan-build.json": (True, "cheap first version (85), low stakes, no forbidden step in the planned action"),
            "plan-spends.json": (False, "planned action spends money"),
            "plan-costly.json": (False, "first version is not cheap enough (cheapness 20 < 70)"),
        }
        for name, answer in plans.items():
            with open(os.path.join(support.EXAMPLES, name), encoding="utf-8") as handle:
                plan = json.load(handle)
            self.assertEqual(gate.decide(plan), answer, name)


if __name__ == "__main__":
    unittest.main()
