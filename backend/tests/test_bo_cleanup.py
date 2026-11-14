"""Automatic clean-up of a new Bulletin Officiel issue: words split by the PDF are joined, real word pairs are not."""
from __future__ import annotations

import collections

from legalrag.bo_update import cleanup


def test_split_words_are_joined_and_logged(tmp_path):
    vocab = collections.Counter({"عليها": 50, "السادس": 40, "يجوز": 30, "في": 900, "هذا": 300, "القانون": 200})
    md = tmp_path / "BO_7558_Ar.md"
    md.write_text("لا ي جوز في هذا القانون إلا ما نص عل يها الفصل ا لسادس\n", encoding="utf-8")
    done = cleanup.clean_issue(md, vocab)
    assert md.read_text(encoding="utf-8") == "لا يجوز في هذا القانون إلا ما نص عليها الفصل السادس\n"
    assert len(done) == 3
    assert (tmp_path / "raw" / "BO_7558_Ar.md").read_text(encoding="utf-8").startswith("لا ي جوز")
    assert "عل يها -> عليها" in (tmp_path / "raw" / "BO_7558_Ar.changes.txt").read_text(encoding="utf-8")


def test_clean_text_is_left_alone(tmp_path):
    vocab = collections.Counter({"في": 900, "هذا": 300, "القانون": 200, "فيهذا": 1})
    md = tmp_path / "BO_7559_Ar.md"
    md.write_text("في هذا القانون\n", encoding="utf-8")
    assert cleanup.clean_issue(md, vocab) == []
    assert not (tmp_path / "raw").exists()
