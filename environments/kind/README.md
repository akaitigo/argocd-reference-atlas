# Kind実行環境

`argocd-atlas-v3-5-2`という専用Kindクラスタだけを対象にします。すべての変更操作は、現在のcontextが`kind-argocd-atlas-v3-5-2`と一致することを確認してから実行します。

Argo CDのinstall manifestと`VERSION`はv3.5.2のURLとSHA-256を固定しています。Git sourceは固定時刻・固定authorでローカル生成し、Kind nodeへread-only mountしてクラスタ内HTTPサービスから参照します。外部Git、実在クラスタ、実Credentialは使いません。

Kind nodeと補助HTTP server imageはtagとlinux/arm64 digestを固定しています。実行時に取得されたimage IDもraw artifactへ保存され、Evidenceの`environment.manifest_digest`から追跡できます。
