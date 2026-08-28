# Evidence

EvidenceはLabの`verify`が成功した場合にだけ生成します。手書きのpass record、空artifact、Completion Certificateは配置しません。

- `raw/evidence.<area>.v3-5-2/result.json`: Application、workload、controller、source-server、destination側Secret metadataのraw capture。Secretの`data`は保存しません。
- `records/evidence.<area>.v3-5-2.evidence.yaml`: Core v1 `evidence.schema.json`準拠record。Source、Harness、Environment、ArtifactをSHA-256で束縛します。

`.runtime/`には取得したupstream manifest、ローカルGit source、capture途中ファイルを置きます。これはEvidence正本ではありません。
