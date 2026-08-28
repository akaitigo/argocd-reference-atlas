# Definitive closure

このdirectoryはArgo CD v3.5.2の一次資料SurfaceとScenario Evidenceのclosureを追跡する作業正本です。文書数やpass済みFixture数は完成条件に使用しません。

- `surface-inventory.yaml`: 公式CRD、CLI、API、Docs、Sourceから抽出した細粒度Surface。
- `gap-ledger.yaml`: `partial`／`missing`を閉じるために必要な正常、境界、拒否、障害、回復、移行、運用、性能、互換Scenario。
- `fe-parity-matrix.json`: AuthorityからArtifactまでの証拠鎖、統合Reference System、比較、Skill Eval、Core v2を含む20軸の完成条件。
- `argocd-depth-parity.json`: FE Depth Referenceの18軸をArgo CD固有denominatorと専用Proof単位へ写像した機械可読な監査結果。FEの絶対件数は閾値として使用しません。
- `../authority/extraction.snapshot.json`: 26固定Sourceの本文を保存しないdigest／locator監査。83件の既知Source edge分類とAuthority本文全体のexhaustive抽出を分離し、後者は未完了です。
- `../authority/body-inventory.snapshot.json`: 26 unique documentから固定selectorで列挙した63,889件の本文非保存raw anchor候補。全件`pending-human`で、Semantic Surface／Depth達成へは0件を算入します。
- `../baselines/authority-body-inventory-v1.json`: raw anchorのstable ID、Source digest、document floorを固定する専用非後退baseline。置換は`../migrations/authority-body-inventory-v1.json`のMappingとEvidenceを要求します。
- `../baselines/public-main-v0.1.0.non-regression.json`: 公開mainのTest／Lab／Target／Claim／Proof／Evidence／Source／Skill Eval／CI非後退条件。

`evidence/certificates/historical/`のCore v1 Certificateは過去commitのbounded recordです。このdirectoryのrequired itemが閉じ、Core v2のdomain-neutral contractへ適合し、active Certificateが再発行されるまでDefinitiveは`incomplete`です。

## Core v2 integration blocker

2026-08-28時点のCore v2 draftは`definitive.yaml`の`area`をKotlin固有の列挙へ、runtime platformを`jvm/js/wasm/native/host-tooling`へ限定しています。Kubernetes、Argo CD component、CLI/API、IdP、repository、clusterを正確に表せないため、偽の値へ対応付けません。またdraft CLI、Makefile Gate、Certificate生成器は未完成です。Inventory自体はdomain-nativeな正本として先行し、Core側がdomain-neutralになったcommitへ固定してから`definitive.yaml`へ移行します。
