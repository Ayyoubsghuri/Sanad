import collections

from legalrag.text.cleanup import Cleaner


def _c():
    v = collections.Counter({"المادة": 500, "الأمر": 200, "يتفق": 40, "القاضي": 90, "في": 9000, "هذا": 800, "القانون": 700, "عليها": 60,
                             "والمحكمة": 50, "على": 5000, "الاستغلال": 80, "لاستغلال": 9})
    v["x" * 3] = 60_000  # bulk so the vocabulary counts as usable
    return Cleaner(v)


def test_repairs_only_safe_damage():
    c = _c()
    new, ch = c.clean("تنص املادة 5 على أن األمر يتف ق مع القاض ي في هذا القانون عل يها واملحكمة")
    assert new == "تنص المادة 5 على أن الأمر يتفق مع القاضي في هذا القانون عليها والمحكمة", (new, ch)
    assert c.usable()


def test_never_touches_known_words_numbers_or_two_real_words():
    c = _c()
    s = "في هذا القانون المادة 12-3 على"
    assert c.clean(s) == (s, [])


def test_clean_file_keeps_the_original(tmp_path):
    c = _c()
    f = tmp_path / "BO_1.md"
    f.write_text("## املادة 1\nنص", encoding="utf-8")
    ch = c.clean_file(f, raw_dir=tmp_path / "raw")
    assert ch and f.read_text(encoding="utf-8").startswith("## المادة 1")
    assert (tmp_path / "raw" / "BO_1.md").read_text(encoding="utf-8").startswith("## املادة")


def test_lost_alef_of_the_ligature():
    c = _c()
    assert c.clean("رخصة الستغلال")[0] == "رخصة الاستغلال"
