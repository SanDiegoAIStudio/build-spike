"""The build-or-ask rule.

An idea may be built without asking when the worst case of building it is a
folder nobody opens. That is checkable from three facts: the first runnable
version is cheap, the stakes are not high, and the step the automation plans to
take does not spend money, send anything, touch production, touch credentials
or destroy data. This module gives permission only. It does not rank ideas.
"""
import re
from typing import Tuple

DEFAULT_THRESHOLD = 70

STAKES = ("low", "medium", "high")

# Categories a spike may never touch. They are matched against the planned
# action, not against the idea text: an idea may be about customers or money,
# but the automatic step taken on it may not spend, send, deploy or sign in.
FORBIDDEN = (
    (r"\b(?:buys?|buying|bought|purchas(?:e|es|ed|ing)|pays?|paying|payments?|paid|invoices?|"
     r"subscri(?:ptions|ption|bing|bes|bed|be)|checkouts?|stripe|billings?|"
     r"renew(?:als|al|ed|ing|s)?|credit cards?|"
     r"charg(?:e|es|ed|ing)|refund(?:s|ed|ing)?|donat(?:e|es|ed|ing)|money|funds?)\b",
     "spends money"),
    (r"\b(?:sends?|sending|sent|emails?|emailed|emailing|dms?|texts?|texted|texting|sms|"
     r"posts?|posted|posting|publish(?:es|ed|ing)?|tweets?|tweeted|tweeting|outreach|"
     r"replies|replied|replying|reply|"
     r"notif(?:y|ies|ied|ying|ication|ications)|upload(?:s|ed|ing)?|messag(?:e|es|ed|ing)|mails?|mailed|mailing|shar(?:e|es|ed|ing)|invit(?:e|es|ed|ing)|submit(?:s|ted|ting)?|"
     r"phon(?:e|ed|ing)|dial(?:s|ed|ing)?|voicemails?|call(?:s|ed|ing)?\s+(?:(?:their|your|the|our|an|my|a)\s+)?(?:customer|client|lead|user|owner|vendor|people|someone|them)s?)\b",
     "sends something outward"),
    (r"\b(?:deploys?|deploying|deployed|ship to prod|push to prod|productions?|live site|"
     r"customer data|client data|"
     r"git\s+push(?!\s+--force)|push(?:es|ed|ing)?\s+to)\b",
     "touches production"),
    (r"\b(?:api[ _-]?keys?|credentials?|passwords?|tokens?|secrets?|rotates?|rotated|rotating|"
     r"oauth|logins?|sign[\s-]?ins?)\b",
     "touches credentials"),
    (r"\b(?:drop table|drop(?:\s+(?:the\s+)?)?database|deletes?|deleted|deleting|truncate|"
     r"migrate the db|rm\s+-(?:rf|fr|r(?:\s+-f)?)|git\s+push\s+--force|force[\s-]push|wipes?|"
     r"wiped|wiping|remov(?:e|es|ed|ing)|overwrit(?:e|es|ing|ten)|overwrote)\b",
     "destructive"),
)


def decide(plan, threshold: int = DEFAULT_THRESHOLD) -> Tuple[bool, str]:
    """Return (may_build, reason) for one plan.

    Three fields are read, in this order, and the first failure decides:
    `cheapness` (a whole number from 0 to 100), `stakes` (low, medium or high)
    and `action` (the text of the planned step). Every other field is ignored.
    A missing or malformed field fails, so the answer defaults to ask.
    """
    if not isinstance(plan, dict):
        plan = {}

    cheapness = plan.get("cheapness")
    if isinstance(cheapness, bool) or not isinstance(cheapness, int) or not 0 <= cheapness <= 100:
        return False, "no usable cheapness (expected a whole number from 0 to 100)"
    if cheapness < threshold:
        return False, "first version is not cheap enough (cheapness %d < %d)" % (cheapness, threshold)

    stakes = plan.get("stakes")
    stakes = stakes.lower() if isinstance(stakes, str) else None
    if stakes not in STAKES:
        return False, "no usable stakes (expected low, medium or high)"
    if stakes == "high":
        return False, "high stakes"

    action = plan.get("action")
    if not isinstance(action, str) or not action.strip():
        return False, "no planned action to screen"
    text = action.lower()
    for pattern, reason in FORBIDDEN:
        if re.search(pattern, text):
            return False, "planned action %s" % reason

    return True, "cheap first version (%d), %s stakes, no forbidden step in the planned action" % (
        cheapness, stakes)
