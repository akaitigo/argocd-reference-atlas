# SBOM方針

この文書はRelease ArtifactのSoftware Bill of Materials（SBOM）を生成・検証・保存する運用方針です。SBOMはLicense判断の代替ではなく、依存物と配布Fileの追跡表として使います。

## 対象と形式

- Source Release、実行Binary、Container Image、配布するSkill BundleごとにSBOMを生成します。
- 機械可読なSPDX 2.3 JSONまたはCycloneDX 1.5以降のJSONを用い、形式とGenerator VersionをRelease Metadataへ記録します。
- 直接・推移Dependency、生成Binary、Container Base、同梱Asset、第三者成果物、配布File Inventoryを含めます。
- Repositoryに同梱しない一次資料のLinkは`sources.lock.yaml`で管理し、SBOM Componentとして再配布したように表現しません。

## 再現性と由来

- SBOM Generatorは固定VersionまたはDigestで実行し、生成Commandと設定を記録します。
- SBOMは正本Manifest、Lockfile、Build Output、`third_party/manifest.yaml`から生成し、手編集しません。
- Release Artifact DigestとSBOM自身のDigestを記録し、同じSource／Harness／Environmentから再生成できる状態にします。
- Generated Artifactには生成元、Generator、変更有無、License判定を残します。

## Release Gate

次のいずれかに該当する場合はReleaseを拒否します。

- SBOMがない、対象ArtifactとDigestが一致しない、または差分説明がない。
- DependencyまたはAssetのLicense、Copyright Holder、Version、出典、再配布条件が不明。
- `third_party/manifest.yaml`とSBOMの同梱Fileが一致しない。
- 既知のLicense義務、NOTICE、Source提供義務をRelease Artifactが満たさない。
- Secret、個人情報、内部URL、未承認のBinary／Assetを含む。

自動検査後も、商標、類似性、Dataset／Model Card、Security Labの公開危険度をHuman Gateで確認します。`atlas.yaml`が`status: incomplete`の間は、検査結果を完成証明や公開承認として扱いません。

## 保存

公開Releaseに対応するSBOM、Digest、Generator情報、検査結果をReleaseと同じ保持期間で保存します。第三者条件の変更や削除要請が発生した場合に、どのReleaseへ影響するか追跡できるようにします。
