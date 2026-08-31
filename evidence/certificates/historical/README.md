# Historical Completion Certificates

このDirectoryのCertificateは、記録された`commit`、Coverage Epoch、Authority Lock、Core Policy、Evidence Setに対する過去のbounded判定です。現在のDefinitive状態や現在の作業内容の完成を示しません。Core v2の標準履歴path `evidence/history/v0.1.0/completion-certificate.json`には同一byte列を保存します。

`v0.1.0-2026-08-28.completion-certificate.json`は、限定したv3.5.2 Fixture、21 covered Target、6 excluded Target、Core v1 Gateを固定した履歴です。Performance／Capacity、広域互換、実IdP、Host／Network RTO-RPO、Rollback Matrix、Trace／IncidentをDefinitive必須面として再分類したため、active Certificate pathから移しました。

検証する場合はCertificateの`commit`をcheckoutし、その時点のCore PolicyとArtifactを使用します。現在のHEADに対して再生成、上書き、Definitive根拠への流用をしません。
