from legalrag.pipeline import plan

STORY = "سيدة من العائلة متزوجة منذ 29 سنة زوجها متقاعد سد عليها باب الدار ومنعها من الخروج ولا ينفق عليها ولها بنت عمرها 16 سنة فما الحل وماذا يقول القانون"


class Fake:
    def __init__(self, issues):
        self.issues, self.seen = issues, None

    def generate_json(self, req):
        self.seen = req
        return {"issues": self.issues}


def test_story_is_split_into_issues():
    f = Fake(["ما حكم منع الزوجة من مغادرة بيت الزوجية؟", "ما نفقة الزوجة على زوجها؟", "ما نفقة البنت القاصر؟", "ما أسباب التطليق للضرر؟"])
    out = plan.issues(f, STORY, None, limit=5)
    assert len(out) == 4 and f.seen.kind == "plan" and f.seen.user_fields == [STORY]


def test_short_question_is_not_planned():
    f = Fake(["a" * 10, "b" * 10])
    assert plan.issues(f, "ما هي مدة التقادم؟", None, limit=5) == [] and f.seen is None


def test_single_issue_or_error_keeps_normal_search():
    assert plan.issues(Fake(["ما نفقة الزوجة على زوجها؟"]), STORY, None, limit=5) == []

    class Boom:
        def generate_json(self, req):
            raise RuntimeError("down")

    assert plan.issues(Boom(), STORY, None, limit=5) == []
    assert plan.issues(None, STORY, None, limit=5) == []
