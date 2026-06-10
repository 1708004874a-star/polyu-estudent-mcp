from pathlib import Path

from estudent_mcp.parsers import parse_exam_schedule, parse_grades, parse_timetable

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
