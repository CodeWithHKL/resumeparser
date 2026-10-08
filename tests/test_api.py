import json

import pytest
from fastapi.testclient import TestClient

import api_v1

client = TestClient(api_v1.app)


@pytest.fixture(autouse=True)
def inline_executor(monkeypatch):
    """Run work in-process: faster and avoids spawning workers inside tests."""
    class Inline:
        def submit(self, fn, *a, **k):
            from concurrent.futures import Future
            f = Future()
            f.set_result(fn(*a, **k))
            return f
    monkeypatch.setattr(api_v1, "executor", Inline())


def post(files, skills="python,sql"):
    return client.post("/rank-resumes", data={"skills": skills}, files=files)


def lines(resp):
    return [json.loads(l) for l in resp.text.splitlines() if l]


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_valid_upload(make_docx):
    r = post([("files", ("a.docx", make_docx(["Python and SQL"])))])
    assert r.status_code == 200
    (res,) = lines(r)
    assert res["status"] == "success" and res["score"] == 2
    assert {"filename", "matched_skills", "time_taken_sec"} <= res.keys()


def test_blank_skills_rejected(make_docx):
    r = post([("files", ("a.docx", make_docx(["x"])))], skills=" , ")
    assert r.status_code == 400


def test_too_many_files(make_docx):
    data = make_docx(["x"])
    files = [("files", (f"{i}.docx", data)) for i in range(api_v1.MAX_RESUME_COUNT + 1)]
    assert post(files).status_code == 400


def test_oversized_file(monkeypatch, make_docx):
    monkeypatch.setattr(api_v1, "MAX_FILE_SIZE", 10)
    r = post([("files", ("a.docx", make_docx(["Python"])))])
    assert r.status_code == 413 or lines(r)[0]["status"] == "error"


def test_mixed_batch(make_docx):
    r = post([
        ("files", ("good.docx", make_docx(["Python"]))),
        ("files", ("bad.pdf", b"garbage")),
    ])
    by_name = {x["filename"]: x for x in lines(r)}
    assert by_name["good.docx"]["status"] == "success"
    assert by_name["bad.pdf"]["status"] == "error"
