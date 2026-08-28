# ローカル実行報告

## 実行範囲

2026-08-28に、Argo CD v3.5.2の通常manifest、公式HA manifest、Argo CD v3.4.8からv3.5.2へのUpgradeを、Repositoryが作成する専用Kind clusterだけで実行しました。実GKE contextでは読取を含むLab操作を行っていません。

通常Labは`kind-argocd-atlas-v3-5-2`、HA Labは3 nodeの`kind-argocd-atlas-ha-v3-5-2`、Upgrade Labは`kind-argocd-atlas-upgrade-v3-4-8`で実行しました。各clusterはEvidence生成後に削除し、元のkubectl contextへ復元しました。

## 固定FixtureでpassしたEvidence

- Application、ApplicationSet、Repository／Cluster connection
- Reconciliation、Sync、Hook／Wave、Diff、Health、Promotion、Drift、Automated self-heal
- Secret boundary、Fixture Identity、RBAC、ローカルOIDC discoveryとprovider outage
- Dependency failure、Control Plane state restore、Operations export／import
- Controller／API Server／Repository ServerのMetricとLog
- 3 node上のHA replica、Redis leader削除、障害窓中read、Replica回復
- v3.4.8からv3.5.2への実Upgrade、主要CR spec、Application Sync／Health維持
- 1 Router Skillの独立forward Eval

各結果は`evidence/raw/`のJSONと`evidence/records/`のCore Evidence recordへ保存しています。RecordはSource、Harness、Environment Manifest、ArtifactのSHA-256を保持し、CIはArtifact digest、size、JSON構文を再計算します。`coverage.yaml`が`partial`または`missing`とするTargetは、ここに固定Fixtureのpass EvidenceがあってもTarget全体がclosedであることを意味しません。

## 実行中に反証されたHarness仮定

- ApplicationSetの`CreateNamespace`にはAppProjectのcluster-scoped Namespace許可が必要だった。
- namespace限定Cluster registrationでもArgo CD cache用のnamespaced read権限が必要だった。
- v3.5.2のHook resultはphaseを`hookPhase`、種類を`hookType`へ記録した。
- OIDC provider outageはEndpointだけでなくprovider Pod消失まで待たないとraceした。
- RBAC deny判定のCLI exit code 1は期待する拒否として明示的に扱う必要があった。
- 公式HA manifestの3-way anti-affinityには3つのschedulable nodeが必要だった。

これらはHarnessを修正し、同じLabを再実行して合格した後にEvidence化しました。

## 非保証範囲

- 単一Mac／Docker host自体の障害耐性、network partition、RTO／RPOはHA Evidenceの対象外です。
- Access Boundaryは固定Fixture Identity、RBAC、OIDC discovery／outageを対象とし、実IdPとの対話Login、MFA、Group変更は未実施です。
- Upgradeは固定Fixtureのv3.4.8からv3.5.2への正方向実行です。Rollback判断点は記録しましたが、全Version／ExtensionのRollback Matrixではありません。
- Performance、Capacity、Cost、複数Kubernetes Version、全Generator／Plugin互換性は未証明です。
- GitHub Repositoryとv0.1.0 Completion Certificateは公開済みですが、限定FixtureとCore v1 Gateに対するbounded historical recordであり、Definitive完成を証明しません。
