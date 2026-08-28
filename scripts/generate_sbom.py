#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Nakayama Ryusei
# SPDX-License-Identifier: Apache-2.0
"""Repository source releaseの決定論的SPDX 2.3 SBOMを生成・検査する。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "sbom.spdx.json"
IGNORED_DIRECTORIES = {".git", ".runtime", ".cache", "__pycache__"}
IGNORED_FILES = {
    "sbom.spdx.json",
    "provenance.yaml",
    "evidence/completion-certificate.json",
    ".DS_Store",
}


def source_files() -> list[Path]:
    result: list[Path] = []
    for directory, names, files in os.walk(ROOT):
        names[:] = sorted(name for name in names if name not in IGNORED_DIRECTORIES)
        base = Path(directory)
        for name in sorted(files):
            path = base / name
            if path.relative_to(ROOT).as_posix() not in IGNORED_FILES:
                result.append(path)
    return sorted(result)


def digest(path: Path, algorithm: str) -> str:
    checksum = hashlib.new(algorithm)
    checksum.update(path.read_bytes())
    return checksum.hexdigest()


def build_document() -> dict[str, object]:
    files: list[dict[str, object]] = []
    relationships: list[dict[str, str]] = [
        {
            "spdxElementId": "SPDXRef-DOCUMENT",
            "relationshipType": "DESCRIBES",
            "relatedSpdxElement": "SPDXRef-Package-argocd-reference-atlas",
        }
    ]
    verification_parts: list[str] = []
    for path in source_files():
        relative = path.relative_to(ROOT).as_posix()
        sha1 = digest(path, "sha1")
        sha256 = digest(path, "sha256")
        file_id = "SPDXRef-File-" + hashlib.sha256(relative.encode("utf-8")).hexdigest()[:24]
        files.append(
            {
                "SPDXID": file_id,
                "fileName": f"./{relative}",
                "checksums": [
                    {"algorithm": "SHA1", "checksumValue": sha1},
                    {"algorithm": "SHA256", "checksumValue": sha256},
                ],
                "licenseConcluded": "Apache-2.0",
                "licenseInfoInFiles": ["Apache-2.0"],
                "copyrightText": "Copyright 2026 Nakayama Ryusei",
            }
        )
        relationships.append(
            {
                "spdxElementId": "SPDXRef-Package-argocd-reference-atlas",
                "relationshipType": "CONTAINS",
                "relatedSpdxElement": file_id,
            }
        )
        verification_parts.append(sha1)

    verification_code = hashlib.sha1("".join(sorted(verification_parts)).encode("ascii")).hexdigest()
    namespace = (
        "https://github.com/akaitigo/argocd-reference-atlas/spdx/"
        f"v0.1.0/{verification_code}"
    )
    return {
        "SPDXID": "SPDXRef-DOCUMENT",
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "name": "argocd-reference-atlas-v0.1.0",
        "documentNamespace": namespace,
        "creationInfo": {
            "created": "2026-08-28T00:00:00Z",
            "creators": ["Tool: argocd-reference-atlas/scripts/generate_sbom.py"],
            "licenseListVersion": "3.27.0",
        },
        "packages": [
            {
                "SPDXID": "SPDXRef-Package-argocd-reference-atlas",
                "name": "argocd-reference-atlas",
                "versionInfo": "0.1.0",
                "downloadLocation": "NOASSERTION",
                "filesAnalyzed": True,
                "packageVerificationCode": {"packageVerificationCodeValue": verification_code},
                "licenseConcluded": "Apache-2.0",
                "licenseDeclared": "Apache-2.0",
                "copyrightText": "Copyright 2026 Nakayama Ryusei",
                "supplier": "Person: Nakayama Ryusei (akaitigo)",
            }
        ],
        "files": files,
        "relationships": relationships,
    }


def serialized() -> str:
    return json.dumps(build_document(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="既存SBOMが再生成結果と一致するか検査する")
    args = parser.parse_args()
    expected = serialized()
    if args.check:
        if not OUTPUT.is_file() or OUTPUT.read_text(encoding="utf-8") != expected:
            print("エラー: sbom.spdx.jsonが現在のRepository File Inventoryと一致しません", file=sys.stderr)
            return 1
        print("検証済み: 決定論的SPDX 2.3 SBOM")
        return 0
    OUTPUT.write_text(expected, encoding="utf-8")
    print(f"生成済み: {OUTPUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
