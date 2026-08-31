#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Nakayama Ryusei
# SPDX-License-Identifier: Apache-2.0
"""固定一次資料から本文を保存しないraw anchor候補母集団を生成する。"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import subprocess
import tarfile
from pathlib import Path
from urllib.parse import urldefrag

import yaml


ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "authority" / "body-inventory.snapshot.json"
ARTIFACT_DIR = ROOT / "authority" / "body-inventory-draft"
BASELINE = ROOT / "baselines" / "authority-body-inventory-v1.json"
EXPECTED_COMMIT = "e258ee23c3e52266d407572f4bcdfe7d9ed36cb5"
RAW_PREFIX = "https://raw.githubusercontent.com/argoproj/argo-cd/v3.5.2/"
REFERENCE_COMMIT = "841ec2fa399606a10305021a8bcd396713b8cee5"
REFERENCE_FILES = [
    {"path": "scripts/lib/authority-body-inventory.ts", "sha256": "04f62a0b63981c62a7ab90f39637c71745642e84a3bdd4404ce715a0163ebe76"},
    {"path": "scripts/extract-authority-body-inventory.ts", "sha256": "1ce38aae8e9adf2c8095310bf54348eacc482cb19f5edbd7c013a4bf55e6d38c"},
    {"path": "scripts/verify-authority-body-inventory.ts", "sha256": "5ba278737bfedae54b3c3b92fdf16a9ecf6b914bcaf0ab2cd04ff0d6ef24884a"},
    {"path": "scripts/lib/authority-body-baseline.ts", "sha256": "0dc48dc9e62fdc9cd8493e9b5827b4cf5948c4b72df3374d5ebcc73ac344009c"},
    {"path": "scripts/verify-authority-body-baseline.ts", "sha256": "599d6dee6d34b10f8496309c68e5cd3b8752366238311ecfbda4e2a23a8be897"},
]
SELECTOR_CONTRACT = [
    "document-root",
    "git-tar-regular-file",
    "markdown-atx-heading-line",
    "yaml-mapping-key-line",
    "plain-nonempty-line",
]


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def canonical_digest(value: object) -> str:
    return sha256_bytes(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode())


def tool_digest() -> str:
    path = Path(__file__).resolve()
    return sha256_bytes(path.read_bytes())


def stable_id(prefix: str, *parts: object) -> str:
    digest = hashlib.sha256("\0".join(str(part) for part in parts).encode()).hexdigest()[:20]
    return f"{prefix}-{digest}"


def line_offsets(data: bytes) -> list[tuple[int, int, bytes]]:
    result: list[tuple[int, int, bytes]] = []
    start = 0
    for line in data.splitlines(keepends=True):
        end = start + len(line)
        result.append((start, end, line))
        start = end
    if start < len(data):
        result.append((start, len(data), data[start:]))
    return result


def anchor(document_id: str, selector: str, locator: str, start: int, end: int, payload: bytes,
           parent_anchor_id: str | None, label: bytes | None = None) -> dict[str, object]:
    context_digest = sha256_bytes(payload)
    return {
        "id": stable_id("anchor", document_id, selector, locator, start, end, context_digest),
        "locator": locator,
        "locator_kind": "document-root" if selector == "document-root" else ("source-member" if selector == "git-tar-regular-file" else "locked-body-offset"),
        "raw_selector": selector,
        "element_name": "document-root" if selector == "document-root" else ("entry" if selector == "git-tar-regular-file" else "line"),
        "parent_anchor_id": parent_anchor_id,
        "context_start": start,
        "context_end": end,
        "context_unit": "byte",
        "context_digest": context_digest,
        "label_digest": sha256_bytes(label) if label else None,
        "classification_status": "pending-human",
        "surface_ids": [],
    }


def raw_file_anchors(document_id: str, data: bytes, suffix: str) -> list[dict[str, object]]:
    root = anchor(document_id, "document-root", "document-root", 0, len(data), data, None)
    result = [root]
    for line_number, (start, end, raw_line) in enumerate(line_offsets(data), start=1):
        text = raw_line.decode("utf-8", errors="replace")
        selector = None
        label = None
        if suffix == ".md":
            match = re.match(r"^\s{0,3}(#{1,6})\s+(\S.*)$", text)
            if match:
                selector = "markdown-atx-heading-line"
                label = match.group(2).strip().encode()
        elif suffix in {".yaml", ".yml"}:
            match = re.match(r"^\s*(?:-\s*)?([A-Za-z0-9_.-]+)\s*:", text)
            if match:
                selector = "yaml-mapping-key-line"
                label = match.group(1).encode()
        elif text.strip():
            selector = "plain-nonempty-line"
            label = text.strip().encode()
        if selector:
            result.append(anchor(document_id, selector, f"line:{line_number}", start, end, raw_line, str(root["id"]), label))
    return result


def archive_anchors(document_id: str, archive: bytes) -> list[dict[str, object]]:
    root = anchor(document_id, "document-root", "document-root", 0, len(archive), archive, None)
    result = [root]
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as tar:
        members = sorted((member for member in tar.getmembers() if member.isfile()), key=lambda item: item.name)
        for member in members:
            stream = tar.extractfile(member)
            if stream is None:
                raise ValueError(f"git archive entryを読めません: {member.name}")
            data = stream.read()
            item = anchor(
                document_id,
                "git-tar-regular-file",
                f"tar-entry:{member.name}",
                member.offset_data,
                member.offset_data + member.size,
                data,
                str(root["id"]),
                member.name.encode(),
            )
            if member.size == 0:
                # Core v2は非空offset範囲を要求する。既存stable IDは空member identityで
                # 保持し、contextだけを直前のtar header byteへ強化する。
                context_start = max(0, member.offset_data - 1)
                item["context_start"] = context_start
                item["context_end"] = context_start + 1
                item["context_digest"] = sha256_bytes(archive[context_start:context_start + 1])
            result.append(item)
    return result


def source_payload(source: dict[str, object], source_tree: Path, archive: bytes) -> tuple[bytes, str, str]:
    if source["id"] == "argocd-source-tree":
        return archive, ".tar", "argocd-source-archive"
    url = str(source["url"])
    if not url.startswith(RAW_PREFIX):
        raise ValueError(f"source tree pathへ変換できないAuthorityです: {source['id']}")
    relative = url.removeprefix(RAW_PREFIX)
    path = source_tree / relative
    if not path.is_file():
        raise ValueError(f"固定Authority fileがありません: {relative}")
    family = "kubernetes-resource-schema" if relative.startswith("manifests/") else "argocd-documentation"
    return path.read_bytes(), path.suffix.lower(), family


def initialize_baseline(index: dict[str, object]) -> None:
    if BASELINE.exists():
        raise ValueError(f"baselineは既に存在します: {BASELINE.relative_to(ROOT)}")
    documents = []
    for record in index["documents"]:
        artifact = json.loads((ROOT / record["path"]).read_text(encoding="utf-8"))
        documents.append({
            "id": artifact["document_id"],
            "path": record["path"],
            "locked_body_digest": artifact["locked_body_digest"],
            "source_ids": artifact["source_ids"],
            "anchor_ids": sorted(item["id"] for item in artifact["anchors"]),
        })
    baseline = {
        "schema_version": 1,
        "id": "authority-body-inventory-v1-2026-08-28",
        "captured_at": "2026-08-28T00:00:00+09:00",
        "source_entries": index["summary"]["source_entries"],
        "unique_documents": index["summary"]["unique_documents"],
        "tool_digest": index["tool_digest"],
        "selector_contract": SELECTOR_CONTRACT,
        "documents": documents,
    }
    BASELINE.parent.mkdir(parents=True, exist_ok=True)
    BASELINE.write_text(json.dumps(baseline, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-tree", required=True, type=Path)
    parser.add_argument("--initialize-baseline", action="store_true")
    args = parser.parse_args()
    source_tree = args.source_tree.resolve()
    commit = subprocess.run(["git", "-C", str(source_tree), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    if commit != EXPECTED_COMMIT:
        raise ValueError(f"Argo CD source commitが不一致です: {commit}")
    archive = subprocess.run(["git", "-C", str(source_tree), "archive", "--format=tar", "HEAD"], check=True, capture_output=True).stdout
    lock = yaml.safe_load((ROOT / "sources.lock.yaml").read_text(encoding="utf-8"))
    sources = lock["sources"]
    normalized_urls = [urldefrag(str(source["url"]))[0] for source in sources]
    if len(normalized_urls) != len(set(normalized_urls)):
        raise ValueError("同じunique document URLに複数のSource lockがあります")

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    records = []
    counts: dict[str, int] = {}
    matched = 0
    for source in sorted(sources, key=lambda item: str(item["id"])):
        data, suffix, _family = source_payload(source, source_tree, archive)
        observed_digest = sha256_bytes(data)
        if observed_digest != source["digest"]:
            raise ValueError(f"固定Authority digestが不一致です: {source['id']}")
        matched += 1
        document_id = f"document-{source['id']}"
        anchors = archive_anchors(document_id, data) if suffix == ".tar" else raw_file_anchors(document_id, data, suffix)
        for item in anchors:
            counts[str(item["raw_selector"])] = counts.get(str(item["raw_selector"]), 0) + 1
        artifact = {
            "schema_version": 1,
            "document_id": document_id,
            "source_ids": [source["id"]],
            "fetch_url": source["url"],
            "locked_body_digest": source["digest"],
            "fetch": {
                "status": "matched",
                "fetched_digest": observed_digest,
                "locked_digest_match": True,
                "http_status": None,
                "final_url": source["url"],
                "content_type": "application/x-tar" if suffix == ".tar" else None,
                "fetched_bytes": len(data),
                "error_digest": None,
            },
            "extraction": {
                "method": "fixed-selector-raw-anchor-v1",
                "tool": "argocd-reference-atlas-authority-body-inventory-v1",
                "tool_digest": tool_digest(),
                "selector_contract": SELECTOR_CONTRACT,
                "selector_exhaustive_for_locked_body": True,
                "authority_semantics_exhaustive": False,
                "review_status": "automated-unreviewed",
                "body_storage": "digest-locator-and-offset-only",
            },
            "anchors": anchors,
        }
        path = ARTIFACT_DIR / f"{document_id}.json"
        path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        records.append({
            "id": document_id,
            "path": path.relative_to(ROOT).as_posix(),
            "digest": sha256_bytes(path.read_bytes()),
            "fetch_status": "matched",
            "source_entries": 1,
            "anchors": len(anchors),
            "anchors_by_selector": dict(sorted({key: sum(1 for item in anchors if item["raw_selector"] == key) for key in {str(item["raw_selector"]) for item in anchors}}.items())),
        })
    expected_files = {f"document-{source['id']}.json" for source in sources}
    for path in ARTIFACT_DIR.glob("*.json"):
        if path.name not in expected_files:
            raise ValueError(f"Source lock外のbody inventory artifactがあります: {path.name}")

    summary = {
        "source_entries": len(sources),
        "unique_documents": len(records),
        "matched_documents": matched,
        "stale_documents": 0,
        "failed_documents": 0,
        "selector_exhaustive_documents": matched,
        "raw_anchor_candidates": sum(record["anchors"] for record in records),
        "anchors_by_selector": dict(sorted(counts.items())),
        "classified_anchors": 0,
        "unclassified_anchors": sum(record["anchors"] for record in records),
        "pending_human_anchors": sum(record["anchors"] for record in records),
        "human_reviewed_anchors": 0,
        "promoted_surface_artifacts": 0,
        "authority_semantics_exhaustive": False,
    }
    index = {
        "schema_version": 1,
        "atlas_id": "argocd-reference-atlas",
        "generated_at": "2026-08-28T00:00:00+09:00",
        "status": "incomplete-human-review-required",
        "reference_design": {"repository": "frontend-behavior-atlas", "commit": REFERENCE_COMMIT, "absolute_counts_transplanted": False},
        "input_digest": canonical_digest({"commit": commit, "sources": [{key: source[key] for key in ("id", "url", "digest")} for source in sources], "selector_contract": SELECTOR_CONTRACT}),
        "tool_digest": tool_digest(),
        "body_storage": "digest-locator-and-offset-only",
        "selector_contract": SELECTOR_CONTRACT,
        "summary": summary,
        "documents": records,
    }
    INDEX.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.initialize_baseline:
        initialize_baseline(index)
    print(f"Authority body inventory: documents={len(records)} matched={matched} stale=0 anchors={summary['raw_anchor_candidates']} pending-human={summary['unclassified_anchors']} semantic-credit=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
