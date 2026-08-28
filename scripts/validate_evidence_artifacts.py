#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Nakayama Ryusei
# SPDX-License-Identifier: Apache-2.0
"""Evidence recordが参照するGit内artifactのdigestとsizeを再検証する。"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RECORDS = ROOT / "evidence" / "records"
SHA256 = re.compile(r"^sha256:([a-f0-9]{64})$")


def fail(message: str) -> None:
    raise ValueError(message)


def artifact_fields(path: Path) -> dict[str, str]:
    fields: dict[str, str] = {}
    in_artifact = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line == "artifact:":
            in_artifact = True
            continue
        if in_artifact and line and not line.startswith("  "):
            break
        if not in_artifact:
            continue
        match = re.fullmatch(r"  ([a-z_]+):\s*(.*?)\s*", line)
        if match:
            value = match.group(2)
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            fields[match.group(1)] = value
    for required in ("uri", "digest", "media_type", "size_bytes"):
        if required not in fields:
            fail(f"{path.relative_to(ROOT)}のartifact.{required}がありません")
    return fields


def validate_record(path: Path) -> None:
    fields = artifact_fields(path)
    uri = Path(fields["uri"])
    if uri.is_absolute() or ".." in uri.parts:
        fail(f"{path.relative_to(ROOT)}のartifact.uriがRepository外を指します: {uri}")
    artifact = (ROOT / uri).resolve()
    if ROOT not in artifact.parents or not artifact.is_file():
        fail(f"artifactがRepository内に存在しません: {uri}")

    digest_match = SHA256.fullmatch(fields["digest"])
    if not digest_match:
        fail(f"{path.relative_to(ROOT)}のartifact.digest形式が不正です")
    content = artifact.read_bytes()
    actual_digest = hashlib.sha256(content).hexdigest()
    if digest_match.group(1) != actual_digest:
        fail(f"artifact digestが一致しません: {uri}")
    try:
        expected_size = int(fields["size_bytes"])
    except ValueError as error:
        raise ValueError(f"{path.relative_to(ROOT)}のsize_bytesが整数ではありません") from error
    if expected_size != len(content):
        fail(f"artifact sizeが一致しません: {uri}")
    if fields["media_type"] == "application/json":
        try:
            json.loads(content)
        except json.JSONDecodeError as error:
            raise ValueError(f"JSON artifactを解釈できません: {uri}: {error}") from error


def main() -> int:
    try:
        records = sorted(RECORDS.glob("*.evidence.yaml"))
        if not records:
            fail("Evidence recordがありません")
        for record in records:
            validate_record(record)
    except (OSError, ValueError) as error:
        print(f"エラー: {error}", file=sys.stderr)
        return 1
    print(f"検証済み: {len(records)} Evidence artifactのdigest、size、JSON構文")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
