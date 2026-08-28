# セキュリティポリシー

このRepositoryはArgo CD v3.5.2の防御目的の技術実証を扱います。Argo CD本体の脆弱性受付窓口ではありません。上流製品の脆弱性は、対象Versionと公開可否を確認したうえでArgo Projectの公式Security Policyへ報告してください。

## 報告

公開Issue、Pull Request、Evidenceへ次を投稿しないでください。

- 実在するCredential、Token、Private Key、内部URL
- 個人情報、顧客情報、非公開の構成情報
- 未修正の第三者脆弱性を再現できる詳細
- 無許可の対象を識別できる情報や収集データ

このRepository固有の脆弱性は、GitHub Private Vulnerability Reportingが有効な場合はそこから報告してください。有効化前または利用できない場合は、公開詳細を作成せずRepository Ownerへ非公開の連絡方法を確認してください。秘密を新たな連絡文へコピーしないでください。

## Labの安全境界

- Security、Failure、Recovery LabはRepositoryが作成するローカル専用Kind Clusterだけを対象にします。
- 外部、共有、本番、顧客Clusterへの障害注入、Credential取得、回避操作は対象外です。
- Fixtureは無害なダミー値を使い、Evidence生成前に秘密・個人情報・内部識別子を除去します。
- 攻撃手順ではなく、防御上の拒否、隔離、検知、復旧のObservable Outcomeを残します。

Security修正を公開する時期は、影響、上流報告、利用者保護を優先してOwnerが判断します。自動Gate通過だけで公開可能とは扱いません。
