import csv
import json

import pytest

import client_v2 as c


def make(tmp_path, rel, content=b"x"):
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content)
    return p


def test_same_basename_in_two_folders_gets_unique_labels(tmp_path):
    make(tmp_path, "a/cv.pdf")
    make(tmp_path, "b/cv.pdf")
    files, _ = c.collect_files([str(tmp_path / "a"), str(tmp_path / "b")])
    labels = [l for l, _ in files]
    assert len(labels) == 2 and len(set(labels)) == 2


def test_skips_oversized_unsupported_and_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(c, "MAX_FILE_SIZE", 5)
    make(tmp_path, "ok.pdf", b"123")
    make(tmp_path, "big.pdf", b"1234567")
    make(tmp_path, "notes.txt")
    files, skipped = c.collect_files([str(tmp_path), str(tmp_path / "nope")])
    assert [l.split("/")[-1] for l, _ in files] == ["ok.pdf"]
    reasons = " ".join(w for _, w in skipped)
    assert "5MB" in reasons and "not found" in reasons


def test_recursive_and_duplicate_folders(tmp_path):
    make(tmp_path, "top.pdf")
    make(tmp_path, "sub/deep.docx")
    assert len(c.collect_files([str(tmp_path)])[0]) == 1
    assert len(c.collect_files([str(tmp_path)], recursive=True)[0]) == 2
    assert len(c.collect_files([str(tmp_path), str(tmp_path)], recursive=True)[0]) == 2


def test_chunked():
    assert list(c.chunked(list(range(5)), 2)) == [[0, 1], [2, 3], [4]]


def test_rank_orders_by_score_then_name_and_drops_errors():
    res = [
        {"status": "success", "filename": "b", "score": 2},
        {"status": "success", "filename": "a", "score": 2},
        {"status": "success", "filename": "c", "score": 3},
        {"status": "error", "filename": "d"},
    ]
    assert [r["filename"] for r in c.rank(res)] == ["c", "a", "b"]


def test_write_csv(tmp_path):
    res = [
        {"status": "success", "filename": "a.pdf", "score": 2, "matched_skills": ["x", "y"], "time_taken_sec": 0.1},
        {"status": "error", "filename": "b.pdf", "error": "bad"},
    ]
    out = tmp_path / "o.csv"
    c.write_csv(str(out), res)
    with open(out, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["rank"] == "1" and rows[0]["matched_skills"] == "x; y"
    assert rows[1]["status"] == "error" and rows[1]["error"] == "bad"


class FakeResp:
    text = ""

    def __init__(self, lines, status):
        self.lines, self.status_code = lines, status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass

    def iter_lines(self):
        return iter(self.lines)


class FakeSession:
    def __init__(self, status=200):
        self.calls, self.status = [], status

    def post(self, url, data, files, stream, timeout, headers=None):
        self.headers = headers
        names = [f[1][0] for f in files]
        self.calls.append((data, names, timeout))
        lines = [json.dumps({"status": "success", "filename": n, "score": 1,
                             "matched_skills": ["x"], "time_taken_sec": 0}).encode() for n in names]
        return FakeResp(lines, self.status)


def test_send_batch_sends_labels_and_closes_files(tmp_path):
    p = make(tmp_path, "a.pdf")
    s = FakeSession()
    out = list(c.send_batch("u", "python", [("dir/a.pdf", str(p))], (5, 10), session=s))
    assert out[0]["filename"] == "dir/a.pdf"
    assert s.calls[0][0] == {"skills": "python"}
    p.unlink()  # would fail on Windows if the handle were still open


def test_send_batch_raises_on_server_error(tmp_path):
    p = make(tmp_path, "a.pdf")
    with pytest.raises(RuntimeError):
        list(c.send_batch("u", "python", [("a.pdf", str(p))], (5, 10), session=FakeSession(status=400)))


def test_main_requires_keywords():
    assert c.main(["-k", " , ", "--no-pause"]) == 1


def test_api_key_header_sent(tmp_path):
    p = make(tmp_path, "a.pdf")
    s = FakeSession()
    list(c.send_batch("u", "python", [("a.pdf", str(p))], (5, 10), session=s, api_key="k"))
    assert s.headers == {"X-API-Key": "k"}
