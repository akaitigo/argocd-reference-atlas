# Evidence

EvidenceはLabの`verify`が成功した場合にだけ生成します。手書きのpass record、空artifact、active Completion Certificateは`raw/`や`records/`へ配置しません。

`certificates/historical/`は過去commitのbounded completionを保存するimmutable archiveです。current HEADの完成判定には使わず、active Certificateは`atlas.yaml`が`status: complete`になり全Gateを通過したときだけ`evidence/completion-certificate.json`へ発行します。

- `raw/evidence.<area>.v3-5-2/result.json`: Application、workload、controller、source-server、destination側Secret metadataのraw capture。Secretの`data`は保存しません。
- `records/evidence.<area>.v3-5-2.evidence.yaml`: Core v1 `evidence.schema.json`準拠record。Source、Harness、Environment、ArtifactをSHA-256で束縛します。

`.runtime/`には取得したupstream manifest、ローカルGit source、capture途中ファイルを置きます。これはEvidence正本ではありません。
