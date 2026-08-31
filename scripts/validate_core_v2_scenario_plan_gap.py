#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Nakayama Ryusei
# SPDX-License-Identifier: Apache-2.0
"""Validate the current Core v2 Scenario Plan gap artifact against live inputs."""

from __future__ import annotations

import json

from generate_core_v2_scenario_plan_gap import OUTPUT, build


def main() -> None:
    document = json.loads(OUTPUT.read_text(encoding="utf-8"))
    expected = build()
    if document != expected:
        raise ValueError("Core v2 Scenario Plan gap artifactが現在入力からの導出値と一致しません")
    print(
        "Core v2 Scenario Plan gap validated: "
        f"rows={document['denominator']['rows']} runtime_remaining={document['denominator']['runtime_execution_remaining_rows']} "
        f"completion_remaining={document['denominator']['completion_remaining_rows']} "
        f"inputs={len(document['inputs'])}"
    )


if __name__ == "__main__":
    main()
