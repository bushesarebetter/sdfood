"""fetch_sdfood.py without the network: a pull checkpoints to its own partial file, only a complete
pull replaces the last one (with a dated backup and its sha256), a refusal is kept on record in
PULL_REFUSED.json and no later run pulls while it is there, an HTML page where JSON belongs counts as
a refusal, and --resume continues."""
import gzip
import json

import pytest

import fetch_sdfood as f


@pytest.fixture()
def data(tmp_path, monkeypatch):
    d = tmp_path / "data"
    d.mkdir()
    for name, value in (("DATA", d), ("RAW", d / "sd_businesses.json"), ("PULL", d / "pull_meta.json"),
                        ("WORK", d / "sd_businesses.partial.json"), ("WORK_META", d / "pull_meta.partial.json"),
                        ("REFUSED", d / "PULL_REFUSED.json"), ("BACKUPS", d / "pulls")):
        monkeypatch.setattr(f, name, value)
    monkeypatch.setattr(f, "PAGE", 2)
    return d


def pages(total, per=2, refuse_at=None):
    ids = [f"B{i}" for i in range(total)]
    calls = []

    def page(n):
        calls.append(n)
        if refuse_at == n:
            raise f.Refused(403, n, "403")
        chunk = ids[(n - 1) * per: n * per]
        return {"total_count": total, "result": [{"business_id": i, "name": i} for i in chunk]}
    page.calls = calls
    return page


def last_complete(data):
    f.save([{"business_id": "OLD"}], f.RAW)
    f.save({"started": "2026-09-23", "complete": True}, f.PULL)


def test_a_complete_pull_replaces_the_last_one_and_keeps_a_dated_backup(data):
    last_complete(data)
    biz, total = f.run_pull(pages(5), {}, "2026-09-29", sleep=lambda s: None, log=lambda m: None)
    assert total == 5 and len(biz) == 5
    assert json.loads(f.RAW.read_text()) == [{"business_id": "OLD"}], "the last pull is untouched until promotion"
    assert json.loads(f.WORK_META.read_text())["complete"] is False
    meta = f.promote(list(biz.values()), "2026-09-29", total)
    assert meta["complete"] and meta["businesses"] == 5 and meta["sha256"] == f.sha256_file(f.RAW)
    with gzip.open(meta["backup"], "rt") as g:
        assert json.load(g) == json.loads(f.RAW.read_text())
    assert not f.WORK.exists() and not f.WORK_META.exists()
    import export_site as es                       # the exporter finds this backup's meta and verifies it
    side = es.pull_meta_for(meta["backup"])
    assert side is not None and json.loads(side.read_text())["sha256"] == es.sha256_pull(meta["backup"]) == meta["sha256"]


def test_a_refusal_is_recorded_stops_for_good_and_leaves_the_last_pull(data):
    last_complete(data)
    page = pages(10, refuse_at=3)
    with pytest.raises(f.Refused):
        f.run_pull(page, {}, "2026-09-29", sleep=lambda s: None, log=lambda m: None)
    assert page.calls == [1, 2, 3], "no retry after a refusal"
    meta = json.loads(f.WORK_META.read_text())
    assert meta["refused"]["status"] == 403 and meta["refused"]["page"] == 3 and meta["businesses"] == 4
    assert json.loads(f.RAW.read_text()) == [{"business_id": "OLD"}]
    assert json.loads(f.PULL.read_text())["complete"] is True


@pytest.mark.parametrize("status, ctype, body, refused", [
    (403, "text/html", "<html>", True), (429, "application/json", "{}", True), (401, "", "", True),
    (200, "text/html; charset=utf-8", "<!doctype html>", True), (200, "application/json", "  <html>", True),
    (200, "application/json", '{"total_count": 1}', False), (500, "text/html", "<html>", False)])
def test_what_counts_as_a_refusal(status, ctype, body, refused):
    assert (f.refusal(status, ctype, body) is not None) is refused


def test_resume_continues_from_the_partial_checkpoint(data):
    f.save([{"business_id": f"B{i}"} for i in range(4)], f.WORK)
    f.save({"started": "2026-09-28", "complete": False}, f.WORK_META)
    biz, started = f.load_checkpoint(resume=True)
    assert len(biz) == 4 and started == "2026-09-28"
    page = pages(6)
    biz, total = f.run_pull(page, biz, started, sleep=lambda s: None, log=lambda m: None)
    assert page.calls == [3] and len(biz) == 6


def test_resume_picks_up_a_pull_started_before_partial_files_existed(data):
    f.save([{"business_id": "B0"}, {"business_id": "B1"}], f.RAW)
    f.save({"started": "2026-09-29", "complete": False}, f.PULL)
    biz, started = f.load_checkpoint(resume=True)
    assert set(biz) == {"B0", "B1"} and started == "2026-09-29"


def test_backups_keep_only_the_newest(data, monkeypatch):
    f.BACKUPS.mkdir()
    for day in range(1, 11):
        (f.BACKUPS / f"sd_businesses.2026-09-{day:02d}.json.gz").write_bytes(b"")
    f.promote([{"business_id": "B0"}], "2026-09-29", 1)
    kept = sorted(p.name for p in f.BACKUPS.glob("sd_businesses.*.json.gz"))
    assert len(kept) == f.KEEP_PULLS and kept[0] == "sd_businesses.2026-09-04.json.gz"


def test_main_exit_codes(data, monkeypatch):
    monkeypatch.setenv("SDFOOD_CONTACT", "test@example.org")
    monkeypatch.setattr(f, "make_client", lambda contact: (None, pages(10, refuse_at=2)))
    assert f.main([]) == f.EXIT_REFUSED
    f.REFUSED.unlink()                  # the County's written OK (docs/RUNBOOK.md)
    f.WORK_META.unlink()

    def short(n):                       # the pages run out before every business appears
        return {"total_count": 9, "result": [{"business_id": f"B{n}"}] if n < 3 else []}
    monkeypatch.setattr(f, "make_client", lambda contact: (None, short))
    monkeypatch.setattr(f.time, "sleep", lambda s: None)
    assert f.main([]) == f.EXIT_INCOMPLETE and not f.RAW.exists() and f.WORK.exists()
    monkeypatch.delenv("SDFOOD_CONTACT")
    with pytest.raises(SystemExit):
        f.main([])


def _client_never_called(contact):
    raise AssertionError("no request may be made while a refusal is on record")


def test_a_refusal_at_the_search_page_is_kept_on_record_and_blocks_every_later_run(data, monkeypatch):
    """make_client raises before anything is saved: the refusal still stays on record, and the next
    run (a scheduled one, or --resume) stops before any request."""
    monkeypatch.setenv("SDFOOD_CONTACT", "test@example.org")

    def refused(contact):
        raise f.Refused(403, 0, "the search page")
    monkeypatch.setattr(f, "make_client", refused)
    assert f.main([]) == f.EXIT_REFUSED
    rec = json.loads(f.REFUSED.read_text())
    assert rec["status"] == 403 and rec["page"] == 0 and rec["detail"] == "the search page" and rec["at"]
    monkeypatch.setattr(f, "make_client", _client_never_called)
    assert f.main([]) == f.EXIT_REFUSED
    assert f.main(["--resume"]) == f.EXIT_REFUSED
    assert json.loads(f.REFUSED.read_text()) == rec, "the first refusal is kept, never overwritten"


def test_a_refusal_mid_pull_is_kept_on_record_too(data):
    with pytest.raises(f.Refused):
        f.run_pull(pages(10, refuse_at=2), {}, "2026-09-29", sleep=lambda s: None, log=lambda m: None)
    assert json.loads(f.REFUSED.read_text())["page"] == 2
    f.record_refusal({"status": 429, "page": 7})
    assert json.loads(f.REFUSED.read_text())["page"] == 2, "never overwritten"


@pytest.mark.parametrize("meta_name", ["pull_meta.partial.json", "pull_meta.partial.json.stale-20260901T060000"])
def test_a_refusal_in_a_partial_meta_blocks_the_pull_even_after_it_was_set_aside(data, monkeypatch, meta_name):
    """A refusal recorded before PULL_REFUSED.json existed lives in the partial meta; setting a stale
    partial aside must not turn it into permission to pull again."""
    monkeypatch.setenv("SDFOOD_CONTACT", "test@example.org")
    monkeypatch.setattr(f, "make_client", _client_never_called)
    f.save({"started": "2026-09-01", "complete": False, "refused": {"status": 403, "page": 5, "detail": "403"}},
           data / meta_name)
    assert f.main([]) == f.EXIT_REFUSED
    rec = json.loads(f.REFUSED.read_text())
    assert rec["status"] == 403 and rec["page"] == 5 and rec["from"] == meta_name, "copied into the lasting record"
    assert (data / meta_name).exists(), "the partial meta itself is left as it was"


def test_a_hand_made_refusal_file_blocks_the_pull_and_the_csv_rebuild_still_runs(data, monkeypatch):
    """The County's written request to stop is recorded by hand; any content, even none, counts."""
    monkeypatch.setenv("SDFOOD_CONTACT", "test@example.org")
    monkeypatch.setattr(f, "make_client", _client_never_called)
    f.REFUSED.write_text("")
    assert f.main([]) == f.EXIT_REFUSED
    f.REFUSED.write_text(json.dumps({"detail": "written request"}))
    assert f.refusal_on_record() == {"detail": "written request"}
    rebuilt = []
    monkeypatch.setattr(f, "write_csv", lambda biz: rebuilt.append(len(biz)))
    f.save([{"business_id": "B0"}], f.RAW)
    assert f.main(["--csv-only"]) == 0 and rebuilt == [1], "--csv-only makes no request, so a refusal does not stop it"


def test_no_refusal_on_record_lets_the_pull_run(data):
    f.save({"started": "2026-09-28", "complete": False}, f.WORK_META)
    assert f.refusal_on_record() is None and not f.REFUSED.exists()
