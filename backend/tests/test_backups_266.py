"""Backups, verification, sanitized dev snapshots and the off-host uploader
(#266, #270). Temp databases with the real ORM schema; mocked HTTP only. No
test touches the corpus, a bucket or the network.
"""

import hashlib
import importlib.util
import json
import os
import sqlite3
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine

from app.db.orm_models import Base
from app.ops import sqlite_tools
from app.ops.sqlite_tools import VerificationError, backup_copy, make_dev_snapshot, verify_database

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
REAL_EMAIL = "jane.realperson@gmail-like.test"
HOSTNAME = "DESKTOP-SECRET42"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _article(i: int) -> tuple:
    return (f"rss_walla_{i:04d}", "walla_sport", "וואלה", f"https://sports.walla.co.il/item/{i}",
            f"כותרת {i}", "he", "2026-10-13T10:00:00+00:00", "basketball", "[]", "news",
            "medium", 0.8, "[]")


def make_corpus(path: Path, *, wal: bool = True) -> Path:
    engine = create_engine(f"sqlite:///{path.as_posix()}")
    Base.metadata.create_all(engine)
    engine.dispose()
    conn = sqlite3.connect(path)
    if wal:
        conn.execute("PRAGMA journal_mode=WAL")
    conn.executemany(
        "INSERT INTO articles (id, source, source_display_name, url, title, language, published_at, "
        "sport, entities, event_type, importance, confidence, tags) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [_article(i) for i in range(5)])
    conn.execute("INSERT INTO users (id, email, password_hash, role, created_at, last_login_at) "
                 "VALUES ('usr_real', ?, '$argon2id$v=19$m=65536,t=3,p=4$secrethash', 'admin', "
                 "'2026-07-01T00:00:00+00:00', '2026-10-12T00:00:00+00:00')", (REAL_EMAIL,))
    conn.execute("INSERT INTO users (id, email, password_hash, role, created_at) "
                 "VALUES ('guy', NULL, NULL, 'demo', '2026-07-01T00:00:00+00:00')")
    for uid, name in (("usr_real", "jane.realperson"), ("guy", "Guy")):
        conn.execute("INSERT INTO profiles (user_id, display_name, language, profile_type, topics, "
                     "muted_topics, muted_sources, followed_entities) VALUES (?, ?, 'he', 'custom', "
                     "'[]', '[]', '[]', '[]')", (uid, name))
    conn.execute("INSERT INTO auth_sessions (token_hash, user_id, created_at, expires_at, user_agent) "
                 "VALUES ('tokhash', 'usr_real', '2026-10-12', '2026-11-12', 'Mozilla/5.0 (Phone)')")
    conn.execute("INSERT INTO feedback_events (id, user_id, article_id, action, created_at, retracted) "
                 "VALUES ('fb_1', 'usr_real', 'rss_walla_0001', 'more_like_this', '2026-10-12', 0)")
    conn.execute("INSERT INTO calibration_responses (user_id, item_id, rating, dataset_version, created_at) "
                 "VALUES ('usr_real', 'cal_001', 'very_interesting', 2, '2026-07-02')")
    conn.execute("INSERT INTO scheduler_cycles (id, trigger, requested_at, status, process_identity) "
                 "VALUES ('cycle_1', 'scheduled', '2026-10-12', 'succeeded', ?)", (f"pid=7 host={HOSTNAME}",))
    conn.execute("INSERT INTO worker_status (id, last_seen_at, state, owner) VALUES (1, '2026-10-12', 'idle', ?)",
                 (f"pid=7 host={HOSTNAME}",))
    conn.execute("INSERT INTO scheduler_lease (id, active_cycle_id, heartbeat_at, owner) VALUES (1, NULL, NULL, ?)",
                 (f"pid=7 host={HOSTNAME}",))
    conn.commit()
    conn.close()
    return path


@pytest.fixture
def corpus(tmp_path):
    (tmp_path / "live").mkdir()
    return make_corpus(tmp_path / "live" / "signal_sports.db")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ── backup_copy / verify ─────────────────────────────────────────────────────

def test_backup_includes_rows_still_in_the_wal(corpus, tmp_path):
    writer = sqlite3.connect(corpus)
    writer.execute("INSERT INTO articles (id, source, source_display_name, url, title, language, published_at, "
                   "sport, entities, event_type, importance, confidence, tags) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   _article(99))
    writer.commit()  # committed, but still in -wal: the writer stays open, no checkpoint
    assert Path(str(corpus) + "-wal").stat().st_size > 0
    report = backup_copy(corpus, tmp_path / "out" / "b.db")
    writer.close()
    assert report["counts"]["articles"] == 6
    assert report["integrity_ok"] and report["foreign_key_violations"] == 0
    assert not Path(str(tmp_path / "out" / "b.db") + "-wal").exists()   # one self-contained file


def test_backup_never_changes_the_source_and_never_overwrites(corpus, tmp_path):
    before = _sha(corpus)
    dest = tmp_path / "b.db"
    backup_copy(corpus, dest)
    assert _sha(corpus) == before
    with pytest.raises(VerificationError, match="refusing to overwrite"):
        backup_copy(corpus, dest)
    if os.name == "posix":
        assert (dest.stat().st_mode & 0o777) == 0o600


def test_verify_rejects_garbage_and_foreign_key_violations(tmp_path):
    junk = tmp_path / "junk.db"
    junk.write_bytes(b"not a database" * 100)
    with pytest.raises(VerificationError):
        verify_database(junk)
    bad = make_corpus(tmp_path / "bad.db", wal=False)
    conn = sqlite3.connect(bad)
    conn.execute("INSERT INTO auth_sessions (token_hash, user_id, created_at, expires_at) "
                 "VALUES ('orphan', 'usr_missing', 'x', 'y')")  # foreign_keys is off by default
    conn.commit()
    conn.close()
    report = verify_database(bad)
    assert report["foreign_key_violations"] == 1
    with pytest.raises(VerificationError, match="foreign key"):
        sqlite_tools.require_healthy(report)


def test_verify_creates_no_sidecar_files(corpus, tmp_path):
    copy = tmp_path / "c.db"
    backup_copy(corpus, copy)
    verify_database(copy)
    assert sorted(p.name for p in tmp_path.iterdir() if p.name.startswith("c.db")) == ["c.db"]


# ── Dev snapshot ─────────────────────────────────────────────────────────────

def test_dev_snapshot_sanitizes_and_keeps_ids(corpus, tmp_path):
    out = tmp_path / "snap" / "dev.db"
    report = make_dev_snapshot(corpus, out)
    conn = sqlite3.connect(out)
    users = dict(conn.execute("SELECT id, email FROM users").fetchall())
    assert users == {"usr_real": "user-usr_real@example.invalid", "guy": None}
    assert conn.execute("SELECT COUNT(*) FROM users WHERE password_hash IS NOT NULL").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM users WHERE last_login_at IS NOT NULL").fetchone()[0] == 0
    for table in ("auth_sessions", "scheduler_lease", "worker_status"):
        assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
    names = dict(conn.execute("SELECT user_id, display_name FROM profiles").fetchall())
    assert names == {"usr_real": "user-usr_real", "guy": "Guy"}             # demo profile kept
    assert conn.execute("SELECT user_id FROM feedback_events").fetchone()[0] == "usr_real"   # relation kept
    assert conn.execute("SELECT user_id FROM calibration_responses").fetchone()[0] == "usr_real"
    assert conn.execute("SELECT process_identity FROM scheduler_cycles").fetchone()[0] is None
    assert conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0] == 5
    conn.close()
    raw = out.read_bytes()
    for secret in (REAL_EMAIL.encode(), HOSTNAME.encode(), b"secrethash", b"Mozilla/5.0 (Phone)"):
        assert secret not in raw
    assert report["emails_rewritten"] == 1
    assert report["counts"]["articles"] == 5


def test_dev_snapshot_failure_leaves_no_file(corpus, tmp_path, monkeypatch):
    # Drop the email rewrite: verification must catch the leak and remove the output.
    monkeypatch.setattr(sqlite_tools, "_SANITIZE_SQL",
                        tuple(s for s in sqlite_tools._SANITIZE_SQL if not s.startswith("UPDATE users")))
    out = tmp_path / "dev.db"
    with pytest.raises(VerificationError, match="emails outside|original email"):
        make_dev_snapshot(corpus, out)
    assert not out.exists()


def test_dev_snapshot_refuses_overwrite(corpus, tmp_path):
    out = tmp_path / "dev.db"
    out.write_bytes(b"x")
    with pytest.raises(VerificationError, match="refusing to overwrite"):
        make_dev_snapshot(corpus, out)
    assert out.read_bytes() == b"x"


# ── CLIs ─────────────────────────────────────────────────────────────────────

def test_backup_cli_writes_a_verified_copy_and_manifest(corpus, tmp_path, capsys):
    cli = _load(BACKEND / "scripts" / "backup_db.py", "backup_db_cli")
    dest = tmp_path / "backups" / "backup_x.db"
    assert cli.main([str(dest), "--src", str(corpus), "--manifest"]) == 0
    manifest = json.loads((tmp_path / "backups" / "backup_x.db.manifest.json").read_text())
    assert manifest["sha256"] == _sha(dest)
    assert manifest["counts"]["articles"] == 5
    assert "integrity=ok" in capsys.readouterr().out


def test_backup_cli_quiescent_mode_fails_on_drift(corpus, tmp_path, monkeypatch):
    cli = _load(BACKEND / "scripts" / "backup_db.py", "backup_db_cli2")
    real = cli.backup_copy

    def drifting(src, dest):
        report = real(src, dest)
        report["source_counts_after"] = {**report["counts"], "articles": report["counts"]["articles"] + 1}
        return report

    monkeypatch.setattr(cli, "backup_copy", drifting)
    assert cli.main([str(tmp_path / "a.db"), "--src", str(corpus)]) == 0          # live: a note
    assert cli.main([str(tmp_path / "b.db"), "--src", str(corpus), "--expect-quiescent"]) == 1


def test_verify_cli_compares_with_a_manifest(corpus, tmp_path):
    backup = _load(BACKEND / "scripts" / "backup_db.py", "backup_db_cli3")
    verify = _load(BACKEND / "scripts" / "verify_db.py", "verify_db_cli")
    dest = tmp_path / "b.db"
    assert backup.main([str(dest), "--src", str(corpus), "--manifest"]) == 0
    manifest = tmp_path / "b.db.manifest.json"
    assert verify.main([str(dest), "--expect", str(manifest)]) == 0
    other = tmp_path / "other.db"
    backup.main([str(other), "--src", str(make_corpus(tmp_path / "other_src.db", wal=False))])
    conn = sqlite3.connect(other)
    conn.execute("DELETE FROM articles WHERE id = 'rss_walla_0000'")
    conn.commit()
    conn.close()
    assert verify.main([str(other), "--expect", str(manifest)]) == 1


def test_snapshot_cli(corpus, tmp_path):
    cli = _load(BACKEND / "scripts" / "make_dev_snapshot.py", "devsnap_cli")
    assert cli.main(["--src", str(corpus), "--out", str(tmp_path / "s.db"), "--manifest"]) == 0
    assert (tmp_path / "s.db.manifest.json").exists()
    with pytest.raises(SystemExit):
        cli.main(["--src", str(corpus), "--out", str(corpus)])


# ── Off-host uploader (deploy/offsite_upload.py) ─────────────────────────────

@pytest.fixture
def up():
    return _load(REPO / "deploy" / "offsite_upload.py", "offsite_upload_under_test")


@pytest.fixture
def blob(tmp_path):
    path = tmp_path / "signal_x.db.gz.age"
    path.write_bytes(b"age-encryption.org/v1\n" + os.urandom(2048))
    return path


V3_AUTH = {
    "accountId": "acc",
    "authorizationToken": "TOKEN-SECRET",
    "apiInfo": {"storageApi": {
        "apiUrl": "https://api005.b2.test",
        "allowed": {"buckets": [{"id": "bkt1", "name": "signal-backup"}],
                    "capabilities": ["writeFiles"], "namePrefix": None},
    }},
}


def test_refuses_unencrypted_files_and_bad_names(up, tmp_path, blob):
    plain = tmp_path / "backup.db"
    plain.write_bytes(b"SQLite format 3\x00")
    assert up.main(["--file", str(plain), "--name", "prod/daily/x.db", "--target", "local:" + str(tmp_path)]) == 2
    assert up.main(["--file", str(blob), "--name", "../x.age", "--target", "local:" + str(tmp_path)]) == 2
    assert up.main(["--file", str(blob), "--name", "x.age", "--target", "s3:bucket"]) == 2


def test_b2_needs_credentials(up, blob, monkeypatch):
    monkeypatch.delenv("B2_APPLICATION_KEY_ID", raising=False)
    monkeypatch.delenv("B2_APPLICATION_KEY", raising=False)
    assert up.main(["--file", str(blob), "--name", "prod/daily/x.age", "--target", "b2:signal-backup"]) == 2


def test_local_target_copies_verifies_and_never_overwrites(up, blob, tmp_path, capsys):
    root = tmp_path / "second-disk"
    argv = ["--file", str(blob), "--name", "prod/daily/x.age", "--target", f"local:{root}"]
    assert up.main(argv) == 0
    result = json.loads(capsys.readouterr().out)
    assert (root / "prod" / "daily" / "x.age").read_bytes() == blob.read_bytes()
    assert result["sha1"] == hashlib.sha1(blob.read_bytes()).hexdigest()
    assert up.main(argv) == 1          # exists: refuse


@pytest.mark.parametrize("allowed,needle", [
    ({"buckets": [{"id": "b", "name": "signal-backup"}], "capabilities": ["writeFiles", "deleteFiles"]}, "deleteFiles"),
    ({"buckets": [{"id": "b", "name": "signal-backup"}], "capabilities": ["writeFiles", "bypassGovernance"]}, "bypassGovernance"),
    ({"buckets": [{"id": "b", "name": "x"}, {"id": "c", "name": "y"}], "capabilities": ["writeFiles"]}, "exactly one bucket"),
    ({"buckets": [{"id": "b", "name": "other"}], "capabilities": ["writeFiles"]}, "not 'signal-backup'"),
    ({"buckets": [{"id": "b", "name": "signal-backup"}], "capabilities": ["listFiles"]}, "lacks"),
    ({"buckets": [{"id": "b", "name": "signal-backup"}], "capabilities": ["writeFiles"], "namePrefix": "other/"}, "prefix"),
])
def test_key_least_privilege(up, allowed, needle):
    auth = {"token": "t", "api_url": "https://a", "buckets": allowed["buckets"],
            "capabilities": set(allowed["capabilities"]), "name_prefix": allowed.get("namePrefix")}
    problems = up.check_key(auth, "signal-backup", "prod/daily/x.age")
    assert any(needle in p for p in problems), problems


def test_authorize_normalizes_v2_and_v3(up, monkeypatch):
    monkeypatch.setattr(up, "_request", lambda url, **k: V3_AUTH)
    v3 = up.authorize_b2("id", "key")
    assert v3["api_url"] == "https://api005.b2.test" and v3["buckets"][0]["id"] == "bkt1"
    v2 = {"authorizationToken": "t", "apiUrl": "https://api002.b2.test",
          "allowed": {"bucketId": "b2id", "bucketName": "signal-backup", "capabilities": ["writeFiles"]}}
    monkeypatch.setattr(up, "_request", lambda url, **k: v2)
    assert up.authorize_b2("id", "key")["buckets"] == [{"id": "b2id", "name": "signal-backup"}]


class _B2:
    """Scripted B2 endpoints for _request."""

    def __init__(self, up, blob, upload_errors=0, confirm_sha1=None):
        self.up, self.calls, self.upload_errors = up, [], upload_errors
        self.sha1 = confirm_sha1 or hashlib.sha1(blob.read_bytes()).hexdigest()
        self.size = blob.stat().st_size

    def __call__(self, url, *, data=None, headers=None, method=None):
        self.calls.append({"url": url, "headers": headers or {}, "method": method})
        if url.endswith("b2_authorize_account"):
            return V3_AUTH
        if url.endswith("b2_get_upload_url"):
            assert json.loads(data) == {"bucketId": "bkt1"}
            return {"uploadUrl": "https://pod.b2.test/upload", "authorizationToken": "UPLOAD-TOKEN"}
        if self.upload_errors:
            self.upload_errors -= 1
            raise self.up.UploadError("HTTP 503 service_unavailable")
        return {"fileId": "4_z123", "contentSha1": self.sha1, "contentLength": self.size}


def _b2_env(monkeypatch):
    monkeypatch.setenv("B2_APPLICATION_KEY_ID", "keyid-SECRET")
    monkeypatch.setenv("B2_APPLICATION_KEY", "appkey-SECRET")


def test_b2_upload_happy_path(up, blob, monkeypatch, capsys):
    _b2_env(monkeypatch)
    fake = _B2(up, blob)
    monkeypatch.setattr(up, "_request", fake)
    assert up.main(["--file", str(blob), "--name", "prod/weekly/signal 1.db.gz.age", "--target", "b2:signal-backup"]) == 0
    out = capsys.readouterr()
    result = json.loads(out.out)
    assert result["ok"] and result["file_id"] == "4_z123" and result["attempts"] == 1
    upload = fake.calls[-1]["headers"]
    assert upload["X-Bz-Content-Sha1"] == fake.sha1
    assert upload["X-Bz-File-Name"] == "prod/weekly/signal%201.db.gz.age"
    assert "Basic " in fake.calls[0]["headers"]["Authorization"]
    for secret in ("SECRET", "TOKEN"):
        assert secret not in out.out and secret not in out.err


def test_b2_transient_errors_are_bounded(up, blob, monkeypatch):
    _b2_env(monkeypatch)
    monkeypatch.setattr(up.time, "sleep", lambda s: None)
    fake = _B2(up, blob, upload_errors=1)
    monkeypatch.setattr(up, "_request", fake)
    assert up.main(["--file", str(blob), "--name", "prod/daily/x.age", "--target", "b2:signal-backup"]) == 0
    fake = _B2(up, blob, upload_errors=10)
    monkeypatch.setattr(up, "_request", fake)
    assert up.main(["--file", str(blob), "--name", "prod/daily/x.age", "--target", "b2:signal-backup"]) == 1
    assert sum(1 for c in fake.calls if c["url"].endswith("/upload")) == up.MAX_ATTEMPTS


def test_b2_wrong_confirmation_fails(up, blob, monkeypatch):
    _b2_env(monkeypatch)
    monkeypatch.setattr(up, "_request", _B2(up, blob, confirm_sha1="0" * 40))
    assert up.main(["--file", str(blob), "--name", "prod/daily/x.age", "--target", "b2:signal-backup"]) == 1


def test_b2_over_privileged_key_is_refused_before_upload(up, blob, monkeypatch):
    _b2_env(monkeypatch)
    auth = json.loads(json.dumps(V3_AUTH))
    auth["apiInfo"]["storageApi"]["allowed"]["capabilities"] = ["writeFiles", "deleteFiles", "listFiles"]
    calls = []

    def fake(url, **kwargs):
        calls.append(url)
        return auth

    monkeypatch.setattr(up, "_request", fake)
    assert up.main(["--file", str(blob), "--name", "prod/daily/x.age", "--target", "b2:signal-backup"]) == 2
    assert len(calls) == 1      # authorize only; no upload URL, no upload


def test_dry_run_sends_nothing(up, blob, monkeypatch, capsys):
    _b2_env(monkeypatch)

    def no_network(*a, **k):
        raise AssertionError("dry run must not call B2")

    monkeypatch.setattr(up, "_request", no_network)
    assert up.main(["--file", str(blob), "--name", "prod/daily/x.age", "--target", "b2:signal-backup", "--dry-run"]) == 0
    assert json.loads(capsys.readouterr().out)["dry_run"] is True
