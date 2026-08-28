# コントリビューション

利用者向け文書とSkillは日本語を正本とし、Schema Key、ID、Path、API名、Argo CDの正式名称は英語を維持してください。変更は小さく分け、対応するCoverage、Claim、Source Lock、Lab、Evidence、移行影響、権利情報を同じPull Requestで更新します。生成Evidenceだけを手編集しません。

## 開発と検証

Pull Request前に次を実行してください。

```sh
atlas validate atlas.yaml sources.lock.yaml coverage.yaml skill.package.yaml
python3 scripts/validate_router_evals.py
python3 scripts/validate_legal.py
```

Labはローカル専用Kind Clusterで`setup`、`execute`、`verify`、`cleanup`まで再実行し、Source、Harness、Environment ManifestのDigestをEvidenceへ記録します。Completion Gateをすべて通過するまで`atlas.yaml`を`status: incomplete`のまま維持してください。

## DCO

すべてのCommitにDeveloper Certificate of Origin 1.1への同意を示す`Signed-off-by`行が必要です。

```text
Signed-off-by: Your Name <your.email@example.com>
```

`git commit -s`で追加できます。Sign-offにより、Contributorは自身が提出する権利を持つこと、または適切に許可されたContributionであり、このRepositoryのLicenseで配布できることを表明します。他者の素材を権利情報なしに提出しないでください。

## 第三者成果物と最終承認

第三者コード、文書、画像、Font、Icon、Dataset、Model、生成Artifact等を追加する場合は、出典、取得Version、License、Copyright Holder、変更有無、再配布条件、対象Fileを`third_party/manifest.yaml`へ記録します。権利者、License、再配布条件のいずれかが不明なものは提出・公開しません。

自動Gate通過だけではMergeしません。権利、商標、類似性、Security Labの公開危険度を確認し、Repository Owner `akaitigo`が最終承認します。GitHubへの公開、Push、Releaseは明示的な別承認が必要です。
