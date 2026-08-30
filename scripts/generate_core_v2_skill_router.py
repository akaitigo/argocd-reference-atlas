#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Nakayama Ryusei
# SPDX-License-Identifier: Apache-2.0
"""Project the existing Argo CD Skill Eval into the Core v2 router contract."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "evals" / "argocd-atlas-router.definitive-skill-eval.json"
OUTPUT = ROOT / "evals" / "definitive-skill-router.json"
BOUNDARIES = {
    "boundary.ambiguous",
    "boundary.unknown",
    "boundary.unauthorized-build",
    "boundary.human-authority-decision",
    "boundary.stale-relock",
}
CELL_KEYS = (
    "id", "status", "outcome", "surface", "mode", "query", "target_id", "target_set",
    "target_set_allowed", "coverage_state", "coverage_disposition", "required_deliverables",
    "required_output_fields", "mutation_policy", "mutation_status", "blocked_reasons",
    "stop_conditions", "expected", "assertions", "support_status", "result",
)


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def binding(path: Path, *, binding_id: str | None = None) -> dict:
    result = {
        "path": path.relative_to(ROOT).as_posix(),
        "digest": digest(path),
        "bytes": path.stat().st_size,
    }
    if binding_id is not None:
        result["id"] = binding_id
    return result


def project_cell(source: dict, boundary: bool = False) -> dict:
    cell = {key: source[key] for key in CELL_KEYS if key in source}
    if cell["mutation_policy"] == "read-only-unless-mutation-requested":
        # 現QueryはMutation要求を含まないため、Core契約ではread-onlyとして固定する。
        cell["mutation_policy"] = "read-only"
    if boundary and cell.get("status") == "blocked":
        # Authority/relock停止は権限の有無とは独立したfail-closed結果である。
        cell["mutation_status"] = "blocked"
    if not boundary:
        runtime = source["runtime_evidence_bindings"]
        cell["implementation_bindings"] = [
            {"id": item["id"], "path": item["harness_path"], "digest": item["harness_digest"]}
            for item in runtime
        ]
        cell["source_bindings"] = [
            {"source_id": item["id"], "url": item["url"], "digest": item["digest"]}
            for item in source["source_bindings"]
        ]
        cell["evidence_bindings"] = [
            {"id": item["id"], "path": item["record_path"], "digest": item["record_digest"]}
            for item in runtime
        ]
    return cell


def build() -> dict:
    source = json.loads(SOURCE.read_text())
    matrix = [project_cell(item) for item in source["matrix"]]
    boundaries = [project_cell(item, boundary=True) for item in source["boundary_cases"] if item["id"] in BOUNDARIES]
    summary = {
        "outcomes": 8,
        "surfaces": 14,
        "matrix_cells": len(matrix),
        "passed": sum(item["result"] == "pass" for item in matrix),
        "failed": sum(item["result"] != "pass" for item in matrix),
        "routed": sum(item.get("support_status") == "routed" for item in matrix),
        "mastery_routing_gaps": sum(item.get("support_status") != "routed" for item in matrix),
        "partial_coverage_cells": sum(item["coverage_state"] != "covered" for item in matrix),
        "boundary_cases": len(boundaries),
        "boundary_passed": sum(item["result"] == "pass" for item in boundaries),
        "boundary_failed": sum(item["result"] != "pass" for item in boundaries),
    }
    forward = source["independent_forward_eval"]
    source_files = {
        "projection_generator": Path(__file__).resolve(),
        "source_eval": SOURCE,
        "mastery": ROOT / "mastery.yaml",
        "coverage": ROOT / "coverage.yaml",
        "source_lock": ROOT / "sources.lock.yaml",
    }
    return {
        "schema_version": 1,
        "id": "argocd.definitive-skill-router.v1",
        "atlas_id": "argocd-reference-atlas",
        "generated_at": source["generated_at"],
        "status": "incomplete-mastery-routing-gaps" if summary["mastery_routing_gaps"] else "incomplete-partial-coverage",
        "semantic_scope": "既存の8 Outcome×14 Surface Argo CD Router結果をCore v2契約へ損失なく投影し、完成判定とは分離する。",
        "source_bindings": {key: binding(path) for key, path in source_files.items()},
        "summary": summary,
        "matrix": matrix,
        "boundary_cases": boundaries,
        "completion_limits": source["completion_limits"],
        "forward_eval": {
            "status": "completed",
            "cases": forward["summary"]["cases"],
            "passed": forward["summary"]["passed"],
            "failed": forward["summary"]["failed"],
            "artifact_path": forward["path"],
            "artifact_digest": forward["digest"],
        },
    }


def main() -> None:
    document = build()
    OUTPUT.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n")
    print(
        "Core v2 Skill Router generated: "
        f"cells={document['summary']['matrix_cells']} routed={document['summary']['routed']} "
        f"gaps={document['summary']['mastery_routing_gaps']} boundaries={document['summary']['boundary_cases']}"
    )


if __name__ == "__main__":
    main()
