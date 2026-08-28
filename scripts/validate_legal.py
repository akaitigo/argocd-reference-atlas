#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Nakayama Ryusei
# SPDX-License-Identifier: Apache-2.0
"""権利、出典、秘密、BinaryのPublication前静的Gate。"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_FILES = (
    "LICENSE",
    "NOTICE",
    "SECURITY.md",
    "CONTRIBUTING.md",
    "docs/SBOM_POLICY.md",
    "sbom.spdx.json",
    "third_party/manifest.yaml",
    "third_party/manifest.schema.json",
)
TEXT_EXTENSIONS_REQUIRING_SPDX = {".py", ".sh"}
IGNORED_PARTS = {".git", ".atlas-core", ".cache", ".runtime", "__pycache__"}
SUSPICIOUS_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".jks", ".kubeconfig"}
ARTIFACT_KINDS = {
    "source", "snippet", "documentation", "image", "texture", "video", "audio",
    "font", "icon", "dataset", "model", "weight", "three-dimensional-model", "cad",
    "board-design", "generated-artifact", "other",
}
ARTIFACT_ID = re.compile(r"^[a-z0-9]+(?:[.-][a-z0-9]+)*$")
DATE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
SHA256 = re.compile(r"^sha256:[a-f0-9]{64}$")
SECRET_PATTERNS = {
    "private key": re.compile(b"-----BEGIN [A-Z0-9 ]*PRIV" + b"ATE KEY-----"),
    "AWS access key": re.compile(b"A" + b"KIA[0-9A-Z]{16}"),
    "GitHub token": re.compile(b"g" + b"h[opsu]_[A-Za-z0-9]{30,}"),
    "Slack token": re.compile(b"x" + b"ox[baprs]-[A-Za-z0-9-]{20,}"),
    "Google API key": re.compile(b"AI" + b"za[0-9A-Za-z_-]{35}"),
}


class GateError(ValueError):
    pass


def fail(message: str) -> None:
    raise GateError(message)


def repository_files() -> list[Path]:
    result: list[Path] = []
    for directory, names, files in os.walk(ROOT):
        names[:] = sorted(name for name in names if name not in IGNORED_PARTS)
        base = Path(directory)
        result.extend(base / name for name in sorted(files))
    return sorted(result)


def load_manifest() -> dict[str, object]:
    path = ROOT / "third_party" / "manifest.yaml"
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        fail(f"third_party/manifest.yamlはJSON互換YAMLとして読める必要があります: {error}")
    if not isinstance(manifest, dict) or set(manifest) != {"schema_version", "artifacts"}:
        fail("第三者ManifestのRoot Keyはschema_versionとartifactsだけです")
    if manifest.get("schema_version") != 1:
        fail("第三者Manifestのschema_versionは1である必要があります")
    if not isinstance(manifest.get("artifacts"), list):
        fail("第三者ManifestのartifactsはArrayである必要があります")
    return manifest


def validate_required_documents() -> None:
    missing = [path for path in REQUIRED_FILES if not (ROOT / path).is_file()]
    if missing:
        fail(f"権利・公開に必要なFileがありません: {', '.join(missing)}")
    license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    for marker in ("Apache License", "Version 2.0, January 2004", "END OF TERMS AND CONDITIONS"):
        if marker not in license_text:
            fail(f"LICENSEにApache-2.0の必須節がありません: {marker}")
    notice = (ROOT / "NOTICE").read_text(encoding="utf-8")
    if "公式、認定、提携製品ではありません" not in notice or "third_party/manifest.yaml" not in notice:
        fail("NOTICEには非提携の商標境界と第三者Manifest参照が必要です")
    contributing = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    if "Developer Certificate of Origin" not in contributing or "Signed-off-by" not in contributing:
        fail("CONTRIBUTING.mdにDCOとSigned-off-by手順がありません")
    if "akaitigo" not in contributing or "最終承認" not in contributing:
        fail("CONTRIBUTING.mdにRepository Ownerの最終承認Gateがありません")
    sbom = (ROOT / "docs" / "SBOM_POLICY.md").read_text(encoding="utf-8")
    for marker in ("SPDX", "CycloneDX", "Release Gate", "third_party/manifest.yaml"):
        if marker not in sbom:
            fail(f"SBOM方針に必須項目がありません: {marker}")


def validate_third_party(manifest: dict[str, object]) -> dict[str, dict[str, object]]:
    required = {
        "id", "name", "kind", "source_url", "version", "retrieved_at", "license",
        "copyright_holder", "redistribution", "modified", "files", "digest", "size_bytes",
    }
    allowed_optional = {"notes"}
    allowed_redistribution = {"allowed", "source-offer-required"}
    seen_ids: set[str] = set()
    registered: dict[str, dict[str, object]] = {}
    artifacts = manifest["artifacts"]
    assert isinstance(artifacts, list)
    for index, artifact in enumerate(artifacts):
        if not isinstance(artifact, dict):
            fail(f"artifacts[{index}]はObjectである必要があります")
        missing = required - set(artifact)
        unknown = set(artifact) - required - allowed_optional
        if missing or unknown:
            fail(f"artifacts[{index}]のKeyが不正です (missing={sorted(missing)}, unknown={sorted(unknown)})")
        artifact_id = artifact["id"]
        if not isinstance(artifact_id, str) or not ARTIFACT_ID.fullmatch(artifact_id):
            fail(f"artifacts[{index}].idが不正です")
        if artifact_id in seen_ids:
            fail(f"第三者Artifact IDが重複しています: {artifact_id}")
        seen_ids.add(artifact_id)
        for field in ("name", "version", "license", "copyright_holder"):
            value = artifact[field]
            if not isinstance(value, str) or not value.strip() or value.lower() in {"unknown", "noassertion", "tbd"}:
                fail(f"{artifact_id}.{field}が不明です")
        if not isinstance(artifact["source_url"], str):
            fail(f"{artifact_id}.source_urlは文字列である必要があります")
        parsed = urlparse(artifact["source_url"])
        if parsed.scheme != "https" or not parsed.netloc:
            fail(f"{artifact_id}.source_urlはhttpsの取得元である必要があります")
        if not isinstance(artifact["kind"], str) or artifact["kind"] not in ARTIFACT_KINDS:
            fail(f"{artifact_id}.kindが不正です")
        if not isinstance(artifact["retrieved_at"], str) or not DATE.fullmatch(artifact["retrieved_at"]):
            fail(f"{artifact_id}.retrieved_atはYYYY-MM-DDである必要があります")
        if not isinstance(artifact["redistribution"], str) or artifact["redistribution"] not in allowed_redistribution:
            fail(f"{artifact_id}は公開可能な再配布条件を確定できていません")
        if not isinstance(artifact["modified"], bool):
            fail(f"{artifact_id}.modifiedはBooleanである必要があります")
        if not isinstance(artifact["digest"], str) or not SHA256.fullmatch(artifact["digest"]):
            fail(f"{artifact_id}.digestはsha256である必要があります")
        if not isinstance(artifact["size_bytes"], int) or artifact["size_bytes"] < 0:
            fail(f"{artifact_id}.size_bytesが不正です")
        if "notes" in artifact and not isinstance(artifact["notes"], str):
            fail(f"{artifact_id}.notesは文字列である必要があります")
        files = artifact["files"]
        if not isinstance(files, list) or len(files) != 1:
            fail(f"{artifact_id}.filesはDigestとSizeを束縛する1 Fileだけを指定します")
        for relative in files:
            if not isinstance(relative, str):
                fail(f"{artifact_id}.filesにはPath文字列だけを指定します")
            path = Path(relative)
            if path.is_absolute() or ".." in path.parts:
                fail(f"{artifact_id}が安全でないPathを参照しています: {relative}")
            target = ROOT / path
            if not target.is_file():
                fail(f"{artifact_id}が存在しないFileを参照しています: {relative}")
            if relative in registered:
                fail(f"第三者Fileが複数Artifactへ登録されています: {relative}")
            registered[relative] = artifact

        target = ROOT / str(files[0])
        actual_digest = "sha256:" + hashlib.sha256(target.read_bytes()).hexdigest()
        if actual_digest != artifact["digest"] or target.stat().st_size != artifact["size_bytes"]:
            fail(f"{artifact_id}のDigestまたはSizeが実Fileと一致しません")
    return registered


def validate_files(registered: dict[str, dict[str, object]]) -> None:
    for path in repository_files():
        relative = path.relative_to(ROOT).as_posix()
        data = path.read_bytes()
        if path.suffix.lower() in SUSPICIOUS_SUFFIXES or path.name == ".env":
            fail(f"Credentialを含み得るFileはRepositoryへ保存できません: {relative}")
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(data):
                fail(f"{relative}から{label}形式の秘密候補を検出しました")
        is_binary = b"\x00" in data[:8192]
        if (is_binary or len(data) > 5 * 1024 * 1024) and relative not in registered:
            fail(f"Binaryまたは5MiB超のFileが第三者Manifestへ未登録です: {relative}")
        if path.name.startswith("validate_") and path.suffix.lower() in TEXT_EXTENSIONS_REQUIRING_SPDX:
            text = data.decode("utf-8", errors="replace")
            if "SPDX-License-Identifier: Apache-2.0" not in text:
                fail(f"Source FileにSPDX License Identifierがありません: {relative}")


def main() -> int:
    try:
        validate_required_documents()
        manifest = load_manifest()
        registered = validate_third_party(manifest)
        validate_files(registered)
    except GateError as error:
        print(f"エラー: {error}", file=sys.stderr)
        return 1
    print("検証済み: License、NOTICE、第三者成果物、秘密、Binary、SBOM方針")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
