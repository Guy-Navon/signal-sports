#!/usr/bin/env python3
"""Upload ONE already-encrypted backup off the host (#266). Standard library only,
so the host's system python3 runs it (no venv, no container).

    offsite_upload.py --file <x.age> --name <prefix/tier/x.age> --target b2:<bucket>
    offsite_upload.py --file <x.age> --name <...> --target local:/mnt/second-disk/signal
    offsite_upload.py ... --dry-run      # check the file and the config, send nothing

The upload is the last of three separate steps (copy, encrypt, upload; see
deploy/backup.sh). It refuses anything that does not end in ".age": only
encrypted files leave the host.

Backblaze B2 (native API v3):
- Credentials come from the environment, never from arguments:
  B2_APPLICATION_KEY_ID and B2_APPLICATION_KEY (deploy/backup.env.example).
- The key must be restricted to exactly one bucket, the named one, and must
  have writeFiles. It is REFUSED when it carries capabilities a backup writer
  never needs and that could destroy or rewrite history: deleteFiles,
  bypassGovernance, writeFileRetentions, writeFileLegalHolds, writeBuckets,
  deleteBuckets, writeBucketRetentions, writeKeys, deleteKeys,
  writeBucketEncryption, writeBucketReplications.
- Note: writeFiles still allows HIDING a file (b2_hide_file) and uploading a
  newer version of the same name [A: B2 docs]. Unique names, bucket Object Lock
  and lifecycle rules set by the owner (docs/DEPLOYMENT.md) are what protect
  history; a write-only key alone does not make deletion impossible.
- The upload carries the file's SHA-1; B2 verifies it on receipt, and the
  answer's sha1 and length are checked again here.
- Transient failures (connection errors, 408, 429, 5xx) get a fresh upload URL
  and at most 3 attempts in total. Then it gives up with exit 1.

Success means exit 0 and one JSON line on stdout; only then may the caller
report the off-host backup as done. Nothing here ever prints a key or token.
Exit codes: 0 uploaded (or dry-run ok); 1 failed; 2 usage/config.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

B2_AUTH_URL = "https://api.backblazeb2.com/b2api/v3/b2_authorize_account"
REQUIRED_CAPABILITIES = frozenset({"writeFiles"})
FORBIDDEN_CAPABILITIES = frozenset({
    "deleteFiles", "bypassGovernance", "writeFileRetentions", "writeFileLegalHolds",
    "writeBuckets", "deleteBuckets", "writeBucketRetentions", "writeKeys", "deleteKeys",
    "writeBucketEncryption", "writeBucketReplications",
})
MAX_ATTEMPTS = 3
TIMEOUT_SECONDS = 120


class UploadError(RuntimeError):
    pass


class ConfigError(RuntimeError):
    pass


def sha1_of(path: Path) -> str:
    digest = hashlib.sha1()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _request(url: str, *, data: bytes | None = None, headers: dict | None = None,
             method: str | None = None) -> dict:
    """One HTTP call; returns parsed JSON. Errors carry status and B2 code only."""
    request = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        code = ""
        try:
            code = json.loads(exc.read().decode("utf-8")).get("code", "")
        except Exception:  # noqa: BLE001
            pass
        raise UploadError(f"HTTP {exc.code} {code}".strip()) from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise UploadError(f"network: {type(exc).__name__}") from None


def _transient(error: UploadError) -> bool:
    text = str(error)
    return text.startswith("network") or any(
        text.startswith(f"HTTP {code}") for code in ("408", "429", "500", "502", "503", "504"))


def authorize_b2(key_id: str, key: str) -> dict:
    """Authorize and normalize the v3 (or v2-shaped) answer."""
    basic = base64.b64encode(f"{key_id}:{key}".encode("utf-8")).decode("ascii")
    answer = _request(B2_AUTH_URL, headers={"Authorization": f"Basic {basic}"})
    storage = (answer.get("apiInfo") or {}).get("storageApi") or answer
    allowed = storage.get("allowed") or answer.get("allowed") or {}
    buckets = allowed.get("buckets")
    if buckets is None and allowed.get("bucketId"):
        buckets = [{"id": allowed.get("bucketId"), "name": allowed.get("bucketName")}]
    return {
        "token": answer.get("authorizationToken"),
        "api_url": storage.get("apiUrl"),
        "buckets": buckets or [],
        "capabilities": set(allowed.get("capabilities") or []),
        "name_prefix": allowed.get("namePrefix"),
    }


def check_key(auth: dict, bucket: str, name: str) -> list[str]:
    """Least-privilege checks. Returns problems; empty means acceptable."""
    problems = []
    if not auth.get("token") or not auth.get("api_url"):
        problems.append("authorization answer is missing a token or apiUrl")
    names = [b.get("name") for b in auth["buckets"]]
    if len(auth["buckets"]) != 1:
        problems.append(f"the key must be restricted to exactly one bucket (it allows {len(names)})")
    elif names[0] != bucket:
        problems.append(f"the key is restricted to bucket {names[0]!r}, not {bucket!r}")
    missing = REQUIRED_CAPABILITIES - auth["capabilities"]
    if missing:
        problems.append(f"the key lacks {sorted(missing)}")
    excess = auth["capabilities"] & FORBIDDEN_CAPABILITIES
    if excess:
        problems.append(f"the key has capabilities a backup writer must not have: {sorted(excess)}")
    prefix = auth.get("name_prefix")
    if prefix and not name.startswith(prefix):
        problems.append(f"object name must start with the key's prefix {prefix!r}")
    return problems


def upload_b2(path: Path, name: str, bucket: str, key_id: str, key: str) -> dict:
    auth = authorize_b2(key_id, key)
    problems = check_key(auth, bucket, name)
    if problems:
        raise ConfigError("; ".join(problems))
    bucket_id = auth["buckets"][0]["id"]
    sha1 = sha1_of(path)
    size = path.stat().st_size
    last_error: UploadError | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            target = _request(
                f"{auth['api_url']}/b2api/v3/b2_get_upload_url",
                data=json.dumps({"bucketId": bucket_id}).encode("utf-8"),
                headers={"Authorization": auth["token"], "Content-Type": "application/json"},
                method="POST",
            )
            with open(path, "rb") as fh:
                body = fh.read()
            answer = _request(
                target["uploadUrl"],
                data=body,
                headers={
                    "Authorization": target["authorizationToken"],
                    "X-Bz-File-Name": urllib.parse.quote(name, safe="/"),
                    "Content-Type": "application/octet-stream",
                    "Content-Length": str(size),
                    "X-Bz-Content-Sha1": sha1,
                },
                method="POST",
            )
        except UploadError as exc:
            last_error = exc
            if attempt < MAX_ATTEMPTS and _transient(exc):
                time.sleep(5 * attempt)
                continue
            raise
        if answer.get("contentSha1") not in (sha1, f"unverified:{sha1}") or answer.get("contentLength") != size:
            raise UploadError("B2 confirmed a different sha1 or length than was sent")
        return {"ok": True, "target": "b2", "bucket": bucket, "name": name,
                "file_id": answer.get("fileId"), "sha1": sha1, "bytes": size, "attempts": attempt}
    raise last_error or UploadError("upload failed")  # pragma: no cover


def upload_local(path: Path, name: str, root: Path) -> dict:
    """Copy to another mounted disk (or a rehearsal directory). Never overwrites."""
    dest = (root / name).resolve()
    if root.resolve() not in dest.parents:
        raise ConfigError("object name escapes the local target root")
    if dest.exists():
        raise UploadError(f"refusing to overwrite {dest}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".partial")
    shutil.copyfile(path, tmp)
    if sha1_of(tmp) != sha1_of(path):
        tmp.unlink(missing_ok=True)
        raise UploadError("local copy checksum mismatch")
    os.replace(tmp, dest)
    os.chmod(dest, 0o600)
    return {"ok": True, "target": "local", "name": name, "path": str(dest),
            "sha1": sha1_of(dest), "bytes": dest.stat().st_size, "attempts": 1}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--file", type=Path, required=True)
    parser.add_argument("--name", required=True, help="object name, e.g. prod/daily/signal_<UTC>.db.gz.age")
    parser.add_argument("--target", required=True, help="b2:<bucket> or local:<directory>")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    try:
        if not args.file.is_file():
            raise ConfigError(f"no such file: {args.file}")
        if not args.file.name.endswith(".age") or not args.name.endswith(".age"):
            raise ConfigError("only age-encrypted files (*.age) may leave the host")
        if args.name.startswith("/") or ".." in args.name.split("/"):
            raise ConfigError("object name must be relative and must not contain '..'")
        kind, _, value = args.target.partition(":")
        if kind not in ("b2", "local") or not value:
            raise ConfigError("--target must be b2:<bucket> or local:<directory>")
        if kind == "b2":
            key_id = os.environ.get("B2_APPLICATION_KEY_ID", "").strip()
            key = os.environ.get("B2_APPLICATION_KEY", "").strip()
            if not key_id or not key:
                raise ConfigError("B2_APPLICATION_KEY_ID and B2_APPLICATION_KEY must be set")
        if args.dry_run:
            print(json.dumps({"ok": True, "dry_run": True, "target": kind, "name": args.name,
                              "sha1": sha1_of(args.file), "bytes": args.file.stat().st_size}))
            return 0
        if kind == "b2":
            result = upload_b2(args.file, args.name, value, key_id, key)
        else:
            result = upload_local(args.file, args.name, Path(value))
    except ConfigError as exc:
        print(f"UPLOAD REFUSED: {exc}", file=sys.stderr)
        return 2
    except (UploadError, OSError) as exc:
        print(f"UPLOAD FAILED: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
