#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Nakayama Ryusei
# SPDX-License-Identifier: Apache-2.0
"""固定Argo CD source treeから本文を保存しないAuthority locator artifactを生成する。"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from urllib.parse import urlparse

import yaml


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "authority" / "locators"
INDEX = ROOT / "authority" / "extraction.snapshot.json"
EXPECTED_COMMIT = "e258ee23c3e52266d407572f4bcdfe7d9ed36cb5"
RAW_PREFIX = "https://raw.githubusercontent.com/argoproj/argo-cd/v3.5.2/"
REFERENCE_COMMIT = "841ec2fa399606a10305021a8bcd396713b8cee5"
REFERENCE_FILES = [
    {"path": "scripts/lib/authority-extraction.ts", "sha256": "eea9e10495383ec3cf89b0d57511ba5438ef1b3ca2e27dbdf57558b1b821c594"},
    {"path": "scripts/extract-authority-surfaces.ts", "sha256": "786d8f671dbc556e50e832b0cbcfa520b034a3d0126a3138d9c01b9b194ad59b"},
    {"path": "scripts/verify-authority-extraction.ts", "sha256": "420acbe08bff848786c4a28febb4443c671afdd53ff1643413317a9ce175d9aa"},
    {"path": "authority/extraction.snapshot.json", "sha256": "ef3d324232f3378909544b5407769e94fc3cc5a1defec968adbb71cb1a947aa8"},
]


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def sha256_json(value: object) -> str:
    return sha256_bytes(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode())


def load_yaml(path: Path) -> dict:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Objectではありません: {path.relative_to(ROOT)}")
    return value


def inventory_items() -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for line in (ROOT / "definitive" / "surface-inventory.yaml").read_text(encoding="utf-8").splitlines():
        match = re.match(r"^  - \{(.+)}$", line)
        if not match:
            continue
        item: dict[str, str] = {}
        for pair in match.group(1).split(", "):
            key, value = pair.split(": ", 1)
            item[key] = value
        items.append(item)
    return items


def content_type(path: str) -> str:
    if path.endswith(".md"):
        return "text/markdown; charset=utf-8"
    if path.endswith((".yaml", ".yml")):
        return "application/yaml"
    return "text/plain; charset=utf-8"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-tree", required=True, type=Path)
    args = parser.parse_args()
    source_tree = args.source_tree.resolve()
    commit = subprocess.run(
        ["git", "-C", str(source_tree), "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    ).stdout.strip()
    if commit != EXPECTED_COMMIT:
        raise ValueError(f"Argo CD source commitが不一致です: {commit}")

    source_lock = load_yaml(ROOT / "sources.lock.yaml")
    sources = source_lock["sources"]
    raw_path_to_source = {
        source["url"].removeprefix(RAW_PREFIX): source["id"]
        for source in sources
        if source["url"].startswith(RAW_PREFIX)
    }
    items = inventory_items()
    authority_items = [item for item in items if not item["locator"].startswith(("definitive/", "labs/"))]
    non_authority_items = [item for item in items if item not in authority_items]
    edges_by_source: dict[str, list[dict[str, object]]] = {source["id"]: [] for source in sources}
    for item in authority_items:
        locator = item["locator"]
        path = source_tree / locator
        if not path.is_file():
            raise ValueError(f"Authority locator fileがありません: {locator}")
        data = path.read_bytes()
        source_id = raw_path_to_source.get(locator, "argocd-source-tree")
        metadata = {key: item[key] for key in ("id", "area", "kind", "target_id", "state")}
        edges_by_source[source_id].append(
            {
                "edge_id": f"edge.{item['id']}.{source_id}",
                "source_id": source_id,
                "inventory_item_id": item["id"],
                "area": item["area"],
                "target_id": item["target_id"],
                "locator": locator,
                "locator_status": "file-found",
                "context_digest": sha256_bytes(data),
                "context_start": 0,
                "context_end": len(data),
                "context_unit": "byte",
                "heading_digest": None,
                "classification_basis": "domain-inventory-projection-unreviewed",
                "domain_reference_metadata_digest": sha256_json(metadata),
                "classification": "candidate-included-unreviewed",
            }
        )
    for edges in edges_by_source.values():
        edges.sort(key=lambda item: str(item["edge_id"]))

    archive = subprocess.run(
        ["git", "-C", str(source_tree), "archive", "--format=tar", "HEAD"], check=True, capture_output=True
    ).stdout
    archive_digest = sha256_bytes(archive)
    source_tree_lock = next(source for source in sources if source["id"] == "argocd-source-tree")
    if archive_digest != source_tree_lock["digest"]:
        raise ValueError("Argo CD source tree archive digestがLockと一致しません")

    OUTPUT.mkdir(parents=True, exist_ok=True)
    artifacts: list[dict[str, object]] = []
    for source in sorted(sources, key=lambda item: item["id"]):
        if source["id"] == "argocd-source-tree":
            data = archive
            locator_kind = "git-archive-root"
            observed_type = "application/x-tar"
        else:
            locator = source["url"].removeprefix(RAW_PREFIX)
            if locator == source["url"]:
                raise ValueError(f"local source pathへ変換できません: {source['id']}")
            path = source_tree / locator
            if not path.is_file():
                raise ValueError(f"Locked source bodyがありません: {locator}")
            data = path.read_bytes()
            locator_kind = "file-root"
            observed_type = content_type(locator)
        observed_digest = sha256_bytes(data)
        if observed_digest != source["digest"]:
            raise ValueError(f"Locked source digestが一致しません: {source['id']}")
        artifact = {
            "schema_version": 1,
            "source_id": source["id"],
            "source_url": source["url"],
            "locked_source_digest": source["digest"],
            "fetch": {
                "status": "matched",
                "observed_digest": observed_digest,
                "locked_digest_match": True,
                "observed_bytes": len(data),
                "content_type": observed_type,
                "error_digest": None,
            },
            "extraction": {
                "method": "locked-body-file-locator-digest",
                "tool": "argocd-reference-atlas-authority-locator-v1",
                "review_status": "automated-unreviewed",
                "body_storage": "metadata-digest-locator-offset-only",
            },
            "document_locator": {
                "locator": "document-root",
                "locator_kind": locator_kind,
                "locator_status": "root-document",
                "context_digest": observed_digest,
                "context_start": 0,
                "context_end": len(data),
                "context_unit": "byte",
            },
            "candidate_surfaces": edges_by_source[source["id"]],
        }
        artifacts.append(artifact)
        (OUTPUT / f"{source['id']}.json").write_text(
            json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    candidate_count = sum(len(artifact["candidate_surfaces"]) for artifact in artifacts)
    input_digest = sha256_json(
        {
            "sources": [{key: source[key] for key in ("id", "url", "digest")} for source in sources],
            "authority_edges": [edge for source_id in sorted(edges_by_source) for edge in edges_by_source[source_id]],
            "non_authority_inventory_item_ids": sorted(item["id"] for item in non_authority_items),
        }
    )
    index_sources = []
    for artifact in artifacts:
        path = OUTPUT / f"{artifact['source_id']}.json"
        index_sources.append(
            {
                "id": artifact["source_id"],
                "path": path.relative_to(ROOT).as_posix(),
                "digest": sha256_bytes(path.read_bytes()),
                "locked_digest_match": True,
                "candidate_surfaces": len(artifact["candidate_surfaces"]),
                "locator_status": {"root-document": 1, "file-found": len(artifact["candidate_surfaces"])},
            }
        )
    index = {
        "schema_version": 1,
        "atlas_id": "argocd-reference-atlas",
        "generated_at": "2026-08-28T00:00:00+09:00",
        "status": "incomplete-human-review-and-exhaustive-inventory-required",
        "reference": {"repository": "frontend-behavior-atlas", "commit": REFERENCE_COMMIT, "files": REFERENCE_FILES},
        "input_digest": input_digest,
        "body_storage": "metadata-digest-locator-offset-only",
        "scope_separation": {
            "domain_inventory_source": "definitive/surface-inventory.yaml",
            "authority_reference_edge_classification": "candidate-included-unreviewed",
            "authority_text_exhaustive_inventory": "not-produced",
            "rule": "Domain inventoryから既知Source edgeを分類した件数をAuthority本文全体のexhaustive surface denominatorへ転用しない。",
        },
        "summary": {
            "locked_sources": len(sources),
            "matched_sources": len(sources),
            "stale_sources": 0,
            "fetch_failed": 0,
            "domain_inventory_items": len(items),
            "authority_reference_edges_classified": candidate_count,
            "non_authority_runtime_obligations": len(non_authority_items),
            "unclassified_authority_reference_edges": 0,
            "root_locators": len(sources),
            "file_locators_found": candidate_count,
            "file_locators_not_found": 0,
            "locator_evaluations_deferred": 0,
            "authority_text_surfaces_exhaustive": False,
            "authority_text_surface_denominator_closed": False,
            "human_reviewed_surfaces": 0,
            "core_v2_eligible_surfaces": 0,
        },
        "non_authority_inventory_item_ids": sorted(item["id"] for item in non_authority_items),
        "sources": index_sources,
    }
    INDEX.parent.mkdir(parents=True, exist_ok=True)
    INDEX.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"Authority locator snapshot: sources={len(sources)} matched={len(sources)} stale=0 deferred=0 "
        f"candidate_edges={candidate_count} human_reviewed=0 exhaustive=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
