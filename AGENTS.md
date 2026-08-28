# Repository instructions

このリポジトリは、固定したArgo CDリリースの公開Surface、実行可能Lab、Evidence、運用判断、Router Skillを所有するProduct Atlasです。

## Canonical sources

- 共通契約は`reference-atlas-core` commit `d5c0a6c`のSchema、Migration Contract、Mastery Contractを正本とする。
- `atlas.yaml`、`mastery.yaml`、`sources.lock.yaml`、`coverage.yaml`、`skill.package.yaml`を共通Manifestの正本とする。
- Argo CD固有のClaimとLab対応は`atlas/claims/`と`labs/`で保持し、共通Schemaへ製品固有項目を追加しない。

## Language and scope

- 利用者向け文書、Skill、CLIメッセージは日本語を正本とする。
- Schema Key、ID、Repository名、Path、API名、Argo CDの正式名称は英語表記を維持する。
- 対象はArgo CD v3.5.2。GitOps一般や外部製品の完全Coverageは含めない。
- Completion Gateをすべて通過するまで`atlas.yaml`の`status`は`incomplete`とする。

## Safety and publication

- Security／Failure Labはローカルの専用Kindクラスタだけを対象とする。
- GitHubへの作成、Push、Release、公開は明示的な別承認なしに行わない。
- 独自コードと文書はApache-2.0。第三者素材は`third_party/manifest.yaml`へ記録する。
- Credential、内部URL、個人情報、権利不明素材をEvidenceへ含めない。

## Change discipline

- Labはsetup、execute、verify、cleanupを再実行可能にし、EvidenceをSource／Harness／Environment digestへ束縛する。
- `covered` Coverage Targetには実在するClaimとEvidenceを必須とする。
- upstreamのfloating branchを実行入力に使わず、VersionまたはDigestを固定する。
- `complete`への変更前に`atlas audit <repository-root>`を通し、8 Outcomeと14 Surfaceを欠落させない。
