from pathlib import Path

from estudent_mcp.parsers import (
    parse_exam_schedule,
    parse_grades,
    parse_subject_detail,
    parse_subject_search,
    parse_vacancy,
    parse_timetable,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text()


# --- grades (multi-table, term via preceding heading) ----------------------


def test_parse_grades_reads_all_entries_across_terms():
    report = parse_grades(_load("grades_sample.html"))
    assert len(report.entries) == 3
    by_code = {e.subject_code: e for e in report.entries}
    assert by_code["COMP1011"].grade == "A"
    assert by_code["COMP1011"].credits == 3.0
    assert by_code["COMP1011"].term == "2024/25 Semester 1"
    assert by_code["ELC1011"].term == "2024/25 Semester 2"
    assert by_code["ELC1011"].remark_code == "R"


def test_parse_grades_empty_html_is_empty_report():
    report = parse_grades("<html><body>no tables</body></html>")
    assert report.entries == []


# --- exam (dr-table.data-block; remark table ignored) ----------------------


def test_parse_exam_reads_main_table_only():
    exams = parse_exam_schedule(_load("exam_sample.html"))
    assert len(exams) == 1
    e = exams[0]
    assert e.subject_code == "AMA1602"
    assert e.exam_component == "Exam Paper 01"
    assert e.date == "30-Apr-2026"
    assert e.start_time == "15:15"
    assert e.venue == "SH1"
    assert e.seat == "Q22"


# --- timetable (dr-table.data-block; remark table ignored) -----------------


def test_parse_timetable_reads_main_table_only():
    slots = parse_timetable(_load("timetable_sample.html"))
    assert len(slots) == 1
    s = slots[0]
    assert s.subject_code == "AMA1602"
    assert s.component == "LEC001"
    assert s.day == "Mon"
    assert s.start_time == "12:30"
    assert s.end_time == "14:20"
    assert s.venue == "Z211"
    assert s.teaching_staff == "LEUNG, Zachary"
    assert s.weeks == "1-13"


# --- subject search (subject-level list) -----------------------------------


def test_parse_subject_search_lists_subjects():
    subjects = parse_subject_search(_load("subject_search_sample.html"))
    assert len(subjects) == 2
    by_code = {s.subject_code: s for s in subjects}
    assert by_code["COMP1011"].subject_title == "PROGRAMMING FUNDAMENTALS"
    assert by_code["COMP1011"].offering_department == "DEPARTMENT OF COMPUTING"
    assert by_code["COMP1011"].credits == 3.0
    assert by_code["COMP2012"].level == "2"
    # No drill-in => no groups, no vacancy.
    assert by_code["COMP1011"].groups == []
    assert by_code["COMP1011"].has_vacancy is False


# --- vacancy cell parsing --------------------------------------------------


def test_parse_vacancy_variants():
    assert parse_vacancy("5") == (5, False)
    assert parse_vacancy("0") == (0, False)
    assert parse_vacancy("(4)") == (4, True)  # reserved/held
    assert parse_vacancy("W=3 Top-up vac=2") == (2, False)
    assert parse_vacancy("") == (None, False)


# --- subject detail (groups + vacancy) -------------------------------------


def test_parse_subject_detail_reads_groups_and_vacancy():
    subj = parse_subject_detail(_load("subject_detail_sample.html"))
    assert subj.subject_code == "COMP1011"
    assert subj.subject_title == "PROGRAMMING FUNDAMENTALS"
    assert subj.credits == 3.0
    assert len(subj.groups) == 4
    g = {grp.group_code: grp for grp in subj.groups}
    # Open vacancy of 5 -> grabbable.
    assert g["1001"].vacancy == 5
    assert g["1001"].has_open_vacancy is True
    # Bracketed (4) -> reserved, NOT openly grabbable.
    assert g["1002"].vacancy == 4
    assert g["1002"].reserved is True
    assert g["1002"].has_open_vacancy is False
    # Zero vacancy.
    assert g["1003"].has_open_vacancy is False
    # Waitlist top-up of 2 is open.
    assert g["1004"].vacancy == 2
    assert g["1004"].has_open_vacancy is True
    # Subject-level has_vacancy true because at least one group is open.
    assert subj.has_vacancy is True
