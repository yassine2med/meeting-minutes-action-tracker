import json
from datetime import date
from pathlib import Path

import pytest

from minutes.__main__ import main
from minutes.parser import attendees, meeting_date, overdue, parse_date, parse_minutes, problems

EX = Path(__file__).resolve().parent.parent / "examples"
WED = date(2026, 11, 18)


@pytest.fixture(scope="module")
def items():
    text = (EX / "minutes_2026-11-18.txt").read_text()
    return parse_minutes(text, meeting_date(text))


def by_id(items, id_):
    return next(i for i in items if i.id == id_)


def test_meeting_date_from_header():
    assert meeting_date("Date: 2026-11-18\n") == WED


def test_meeting_date_missing_needs_fallback():
    with pytest.raises(ValueError):
        meeting_date("no header")
    assert meeting_date("no header", WED) == WED


def test_item_count(items):
    assert len(items) == 8


def test_action_marker_owner_and_weekday(items):
    first = by_id(items, "A1")
    assert (first.owner, first.due, first.task) == ("Sam Ortiz", date(2026, 11, 20), "Get two quotes for the seal")


def test_owner_in_brackets_and_iso_due(items):
    second = by_id(items, "A2")
    assert second.owner == "Dana Reyes" and second.due == date(2026, 11, 25)


def test_checkbox_slash_date(items):
    assert by_id(items, "A3").due == date(2026, 12, 2)


def test_checked_box_is_done(items):
    assert by_id(items, "A4").done and not by_id(items, "A3").done


def test_two_owners_and_next_friday(items):
    item = by_id(items, "A5")
    assert item.owner == "Dana Reyes, Leo Brandt" and item.due == date(2026, 11, 27)


def test_sentence_with_will_and_before(items):
    item = by_id(items, "A6")
    assert item.owner == "Priya Nair" and item.due == date(2026, 12, 4)


def test_at_owner_and_end_of_week(items):
    item = by_id(items, "A7")
    assert item.owner == "Leo Brandt" and item.due == date(2026, 11, 20)


def test_unassigned_item(items):
    assert by_id(items, "A8").owner == "(unassigned)"


def test_markers_only_skips_sentences():
    text = (EX / "minutes_2026-11-18.txt").read_text()
    assert all("budget summary" not in i.task for i in parse_minutes(text, WED, markers_only=True))


def test_problems_lists_unassigned(items):
    assert len(problems(items)) == 2


def test_overdue_skips_done_items():
    text = (EX / "minutes_2026-11-04.txt").read_text()
    late = overdue(parse_minutes(text, date(2026, 11, 4)), date(2026, 11, 20))
    assert [i.owner for i in late] == ["Sam Ortiz", "Dana Reyes"]


@pytest.mark.parametrize("phrase,expected", [
    ("tomorrow", date(2026, 11, 19)),
    ("Friday", date(2026, 11, 20)),
    ("next Friday", date(2026, 11, 27)),
    ("Wednesday", date(2026, 11, 25)),
    ("Dec 5", date(2026, 12, 5)),
    ("December 5, 2027", date(2027, 12, 5)),
    ("1/5", date(2027, 1, 5)),
    ("eom", date(2026, 11, 30)),
    ("next week", date(2026, 11, 27)),
])
def test_parse_date_phrases(phrase, expected):
    assert parse_date(phrase, WED) == expected


def test_parse_date_rejects_impossible():
    assert parse_date("2/31", WED) is None


def test_attendees_first_name_map_skips_duplicates():
    text = "Attendees: Sam Ortiz, Sam Lee, Dana Reyes\n"
    assert attendees(text) == {"dana": "Dana Reyes"}


def test_cli(capsys, tmp_path):
    f = str(EX / "minutes_2026-11-18.txt")
    assert main(["extract", f]) == 0
    assert main(["extract", f, "--format", "json"]) == 0
    assert main(["overdue", f, "--today", "2026-12-10"]) == 1
    assert main(["overdue", f, "--today", "2026-11-18"]) == 0
    assert main(["check", f]) == 1
    assert main(["owners", f]) == 0
    assert main(["extract", str(tmp_path / "none.txt")]) == 2
    bare = tmp_path / "m.txt"
    bare.write_text("ACTION: Sam to fix it by Friday\n")
    assert main(["extract", str(bare)]) == 2
    assert main(["extract", str(bare), "--meeting-date", "2026-11-18"]) == 0


def test_json_output_parses(capsys):
    main(["extract", str(EX / "minutes_2026-11-18.txt"), "--format", "json"])
    data = json.loads(capsys.readouterr().out)
    assert data[0]["id"] == "A1" and data[0]["due"] == "2026-11-20"
