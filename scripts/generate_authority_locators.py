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
OUTPUT = ROOT / "authority" / "surfaces-draft"
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


def tool_digest() -> str:
    return sha256_bytes(Path(__file__).read_bytes())


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


def surface_ids(item: dict[str, str]) -> list[str]:
    result = {"provenance-rights"}
    area = item["area"]
    kind = item["kind"]
    if "docs" in kind:
        result.add("orientation-scope")
    if any(marker in kind for marker in ("source", "crd", "api", "cli")):
        result.add("implementation-construction")
    if area in {"architecture", "ha", "connection"}:
        result.add("architecture-design")
    if area in {"failure", "recovery", "drift"}:
        result.add("failure-recovery")
    if area in {"operations", "observability", "notification"}:
        result.add("operations-observability")
    if area in {"auth", "security", "secret-boundary"}:
        result.add("security-privacy-safety")
    if area == "performance":
        result.add("performance-capacity-cost")
    if area in {"compatibility", "extension"}:
        result.add("compatibility-integration")
    if area == "migration":
        result.add("migration-evolution-deprecation")
    if area == "skill":
        result.add("agent-skill")
    return sorted(result)


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
    coverage = load_yaml(ROOT / "coverage.yaml")
    claim_index = load_yaml(ROOT / "atlas/claims/index.yaml")
    claims = {item["id"]: item for item in claim_index["claims"]}
    targets = {item["id"]: item for item in coverage["targets"]}
    authority_items = [item for item in items if not item["locator"].startswith(("definitive/", "labs/"))]
    non_authority_items = [item for item in items if item not in authority_items]
    edges_by_source: dict[str, list[dict[str, object]]] = {source["id"]: [] for source in sources}
    unclassified_items: list[str] = []
    for item in authority_items:
        locator = item["locator"]
        path = source_tree / locator
        if not path.is_file():
            raise ValueError(f"Authority locator fileがありません: {locator}")
        source_id = raw_path_to_source.get(locator, "argocd-source-tree")
        claim_ids = targets[item["target_id"]].get("claim_ids", [])
        if not claim_ids:
            unclassified_items.append(item["id"])
            continue
        claim = claims[claim_ids[0]]
        metadata = {key: item[key] for key in ("id", "area", "kind", "target_id", "state")}
        edges_by_source[source_id].append(
            {
                "edge_id": f"edge.{item['id']}.{source_id}",
                "source_id": source_id,
                "reference_url": next(source["url"] for source in sources if source["id"] == source_id),
                "locator": "document-root",
                "pattern_id": f"{item['area']}/{re.sub(r'[^a-z0-9-]+', '-', item['id']).strip('-')}",
                "pattern_kind": "atomic",
                "candidate_behavior_id": f"candidate.{item['id']}.{source_id}",
                "capability_id": claim["capability_id"],
                "target_id": item["target_id"],
                "claim_id": claim["id"],
                "variant_ids": [f"variant.{item['id']}.argocd-v3-5-2"],
                "surface_ids": surface_ids(item),
                "classification_basis": "domain-contract-projection-unreviewed",
                "domain_reference_metadata_digest": sha256_json(metadata),
                "locator_status": "root-document",
                "context_digest": None,
                "context_start": None,
                "context_end": None,
                "context_unit": "utf16-code-unit",
                "heading_digest": None,
                "classification": "candidate-included-unreviewed",
            }
        )
    target_by_claim = {
        claim_id: target["id"]
        for target in coverage["targets"]
        for claim_id in target.get("claim_ids", [])
    }
    for source in sources:
        if edges_by_source[source["id"]]:
            continue
        source_claims = sorted(
            (claim for claim in claims.values() if source["id"] in claim["source_ids"]),
            key=lambda item: item["id"],
        )
        if not source_claims:
            raise ValueError(f"Source lockをDomain Claimへ接続できません: {source['id']}")
        claim = source_claims[0]
        metadata = {"source_id": source["id"], "claim_id": claim["id"], "projection": "source-level-provenance-candidate"}
        edges_by_source[source["id"]].append({
            "edge_id": f"edge.source.{source['id']}.{claim['id']}",
            "source_id": source["id"],
            "reference_url": source["url"],
            "locator": "document-root",
            "pattern_id": f"authority/{source['id'].replace('.', '-')}",
            "pattern_kind": "atomic",
            "candidate_behavior_id": f"candidate.source.{source['id']}.{claim['id']}",
            "capability_id": claim["capability_id"],
            "target_id": target_by_claim[claim["id"]],
            "claim_id": claim["id"],
            "variant_ids": [f"variant.source.{source['id']}.argocd-v3-5-2"],
            "surface_ids": ["provenance-rights"],
            "classification_basis": "domain-contract-projection-unreviewed",
            "domain_reference_metadata_digest": sha256_json(metadata),
            "locator_status": "root-document",
            "context_digest": None,
            "context_start": None,
            "context_end": None,
            "context_unit": "utf16-code-unit",
            "heading_digest": None,
            "classification": "candidate-included-unreviewed",
        })
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
        candidates = []
        context_end = max(1, len(data.decode("utf-8", errors="replace").encode("utf-16-le")) // 2)
        for candidate in edges_by_source[source["id"]]:
            candidate = dict(candidate)
            candidate.update({"context_digest": observed_digest, "context_start": 0, "context_end": context_end})
            candidates.append(candidate)
        artifact = {
            "schema_version": 1,
            "source_id": source["id"],
            "source_url": source["url"],
            "locked_source_digest": source["digest"],
            "fetch": {
                "status": "matched",
                "fetched_digest": observed_digest,
                "locked_digest_match": True,
                "http_status": None,
                "final_url": source["url"],
                "content_type": observed_type,
                "fetched_bytes": len(data),
                "error_digest": None,
            },
            "extraction": {
                "method": "locked-body-locator-context-digest",
                "tool": "argocd-reference-atlas-authority-locator-v1",
                "tool_digest": tool_digest(),
                "review_status": "automated-unreviewed",
                "body_storage": "digest-and-locator-context-digest-only",
            },
            "candidate_surfaces": candidates,
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
                "locator_status": {"root-document": max(1, len(artifact["candidate_surfaces"]))},
            }
        )
    index = {
        "schema_version": 1,
        "atlas_id": "argocd-reference-atlas",
        "generated_at": "2026-08-28T00:00:00+09:00",
        "status": "incomplete-human-review-required",
        "input_digest": input_digest,
        "tool_digest": tool_digest(),
        "body_storage": "digest-and-locator-context-digest-only",
        "summary": {
            "locked_sources": len(sources),
            "fetched_digest_matched": len(sources),
            "fetched_digest_stale": 0,
            "fetch_failed": 0,
            "candidate_surfaces": candidate_count,
            "root_locators": candidate_count,
            "fragments_found": 0,
            "fragments_not_found": 0,
            "locator_evaluations_deferred": 0,
            "reference_edges_classified": candidate_count,
            "unclassified_reference_edges": 0,
            "authority_text_surfaces_exhaustive": False,
            "human_reviewed_surfaces": 0,
            "core_v2_eligible_surfaces": 0,
        },
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
