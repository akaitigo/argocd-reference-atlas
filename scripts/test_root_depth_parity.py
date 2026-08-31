#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Nakayama Ryusei
# SPDX-License-Identifier: Apache-2.0
"""Negative fixtures for the fail-closed root depth parity contract."""

from __future__ import annotations

import json

from generate_root_depth_parity import OUTPUT, validate


def rejected(name: str, mutate) -> None:
    fixture = json.loads(OUTPUT.read_text(encoding="utf-8"))
    mutate(fixture)
    try:
        validate(fixture)
    except ValueError:
        return
    raise AssertionError(f"negative fixture accepted: {name}")


def main() -> None:
    document = json.loads(OUTPUT.read_text(encoding="utf-8"))
    validate(document)
    rejected("source-summary-forged", lambda value: value["source_depth_parity"].update(summary={"satisfied": 18, "partial": 0, "missing": 0}))
    rejected("open-axes-concealed", lambda value: value["source_depth_parity"].update(open_axes=[]))
    rejected("root-status-promoted", lambda value: value["root_depth_parity"].update(completion_status="parity"))
    rejected("reference-digest-drift", lambda value: value["root_depth_parity"].update(reference_digest="sha256:" + "0" * 64))
    rejected("policy-weakened", lambda value: value["policy"].update(authority_absolute_counts_transplant_forbidden=False))
    rejected("credit-forged", lambda value: value["credit"].update(runtime=1))
    print("Root Depth Parity fixtures passed: positive=1 negative=5")


if __name__ == "__main__":
    main()
