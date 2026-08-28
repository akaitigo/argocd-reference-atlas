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
- Notification controllerからlocal receiverへの正常配信、HTTP 503による6回の試行、receiver回復後の配信、trigger／delivery metric
- 3 node上のHA replica、Application Controller/repo-server/Redis master Pod UID交代、Controller復旧後Drift再収束、repo-server復旧後Hard Refresh、Redis障害窓中read/metrics、Replica回復
- v3.4.8からv3.5.2への実Upgrade、主要CR spec、Application Sync／Health維持
- 1 Router Skillの8件bounded historical forward Eval
- 8 Outcome × 14 Surfaceの112セルRouter契約、7境界Case、全30 Target state、10件独立Forward Eval（Matrix／Forward passはCompletionへ算入しない）
- 10 Scenarioのoffline Evidence integration Auditと、現行100 Surface × 10 Scenarioの1,000専用Proof row。20行はRuntime／全Component identityまで完結、156行は直接Artifactとidentity gap、824行はBehavior固有gap。単一Topology Runtime成功とCompletion eligibleはいずれも0

各結果は`evidence/raw/`のJSONと`evidence/records/`のCore Evidence recordへ保存しています。RecordはSource、Harness、Environment Manifest、ArtifactのSHA-256を保持し、CIはArtifact digest、size、JSON構文を再計算します。`coverage.yaml`が`partial`または`missing`とするTargetは、ここに固定Fixtureのpass EvidenceがあってもTarget全体がclosedであることを意味しません。

## 実行中に反証されたHarness仮定

- ApplicationSetの`CreateNamespace`にはAppProjectのcluster-scoped Namespace許可が必要だった。
- namespace限定Cluster registrationでもArgo CD cache用のnamespaced read権限が必要だった。
- v3.5.2のHook resultはphaseを`hookPhase`、種類を`hookType`へ記録した。
- OIDC provider outageはEndpointだけでなくprovider Pod消失まで待たないとraceした。
- RBAC deny判定のCLI exit code 1は期待する拒否として明示的に扱う必要があった。
- 公式HA manifestの3-way anti-affinityには3つのschedulable nodeが必要だった。
- shell文字列の`\n`はNotification ConfigMapで改行として解釈されず、YAMLを実改行で生成する必要があった。
- v3.5.2 runtime decoderは公式文書例の`1s`をretry durationとして受理せず、nanosecond整数値を受理した。

これらはHarnessを修正し、同じLabを再実行して合格した後にEvidence化しました。

## 非保証範囲

- 単一Mac／Docker host自体の障害耐性、network partition、RTO／RPOはHA Evidenceの対象外です。
- Access Boundaryは固定Fixture Identity、RBAC、OIDC discovery／outageを対象とし、実IdPとの対話Login、MFA、Group変更は未実施です。
- Upgradeは固定Fixtureのv3.4.8からv3.5.2への正方向実行です。Rollback判断点は記録しましたが、全Version／ExtensionのRollback Matrixではありません。
- Performance、Capacity、Cost、複数Kubernetes Version、全Generator／Plugin互換性は未証明です。
- Notification EvidenceはApplication annotationとlocal webhook serviceに限定されます。global subscription、外部provider認証、rate limit、controller再起動時のdeduplication、全Notification Serviceは未証明です。
- GitHub Repositoryとv0.1.0 Completion Certificateは公開済みですが、限定FixtureとCore v1 Gateに対するbounded historical recordであり、Definitive完成を証明しません。
