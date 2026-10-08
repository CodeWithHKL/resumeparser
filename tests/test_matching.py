from api_v1 import build_skill_pattern


def find(text, skills):
    p = build_skill_pattern(skills)
    return {" ".join(m.group(0).lower().split()) for m in p.finditer(text)}


def test_case_insensitive():
    assert find("PYTHON and Sql", ["python", "sql"]) == {"python", "sql"}


def test_multi_word_across_newline():
    assert find("Machine\nLearning engineer", ["machine learning"]) == {"machine learning"}


def test_symbol_skills():
    assert find("C++, C# and Node.js", ["c++", "c#", "node.js"]) == {"c++", "c#", "node.js"}


def test_whole_word_only():
    assert find("I write JavaScript and cpython", ["java", "c", "python"]) == set()


def test_short_skill_not_matched_inside_longer_symbol_skill():
    assert find("only C++ here", ["c"]) == set()


def test_duplicates_count_once():
    assert find("sql sql SQL", ["sql"]) == {"sql"}


def test_punctuation_boundaries():
    assert find("skills: python, (sql).", ["python", "sql"]) == {"python", "sql"}
