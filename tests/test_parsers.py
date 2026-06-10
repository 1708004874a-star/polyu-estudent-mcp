from pathlib import Path

from estudent_mcp.parsers import parse_grades, parse_subject_search

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text()


def test_parse_grades_reads_all_entries():
    report = parse_grades(_load("grades_sample.html"))
    assert len(report.entries) == 3
    first = report.entries[0]
    assert first.subject_code == "COMP1011"
    assert first.subject_title == "Programming Fundamentals"
    assert first.credits == 3.0
    assert first.grade == "A"
    assert first.term == "2024-25 Sem 1"


def test_parse_grades_empty_html_is_empty_report():
    report = parse_grades("<html><body>no table here</body></html>")
    assert report.entries == []


def test_parse_subjects_reads_vacancy():
    offerings = parse_subject_search(_load("subjects_sample.html"))
    assert len(offerings) == 2
    full, open_ = offerings
    assert full.subject_code == "COMP2011"
    assert full.vacancy == 0
    assert full.has_vacancy is False
    assert open_.vacancy == 5
    assert open_.has_vacancy is True


def test_parse_subjects_derives_vacancy_when_missing():
    html = """
    <table><tr><th>Subject Code</th><th>Capacity</th><th>Enrolled</th></tr>
    <tr><td>X1001</td><td>30</td><td>28</td></tr></table>
    """
    offerings = parse_subject_search(html)
    assert offerings[0].vacancy == 2
