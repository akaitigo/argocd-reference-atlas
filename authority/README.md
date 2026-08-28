# Authority locator監査

`extraction.snapshot.json`と`locators/`は、`sources.lock.yaml`の26固定SourceについてURL、metadata、digest、byte offsetだけを保持します。第三者本文、抜粋、見出し文字列は保存しません。83件の`candidate-included-unreviewed`は`definitive/surface-inventory.yaml`から既知のAuthority fileへ接続したedgeで、17件のlocal runtime／benchmark／comparison obligationと分離しています。これは既存Feature／Source edgeの分類であり、Authority本文全体のdenominatorではありません。

`body-inventory.snapshot.json`と`body-inventory-draft/`は、26 unique documentを固定selectorで走査したraw anchor候補母集団です。Argo CD source archiveは全5,405 tracked regular file、Markdownは293 ATX heading行、Kubernetes manifest／CRDは58,164 YAML mapping key行、Version fileは1 nonempty行、各documentはroot anchorを保持します。合計63,889 anchorはすべて`pending-human`、`surface_ids: []`で、human reviewed、Controller／behavior Surfaceへの昇格、Semantic Surface credit、Depth axis creditはいずれも0です。selector内の列挙完了はAuthority意味論の網羅を意味しません。

`baselines/authority-body-inventory-v1.json`は初回26 document／63,889 stable anchor IDを固定します。削除や置換は`migrations/authority-body-inventory-v1.json`の旧ID→新ID Mapping、実行Proof、Migration Evidence、理由なしではGateを通りません。Source lockと異なるdigestは`stale`としてanchor生成・昇格を止め、別Epochと人手Reviewを要求します。

再生成にはArgo CD v3.5.2 commit `e258ee23c3e52266d407572f4bcdfe7d9ed36cb5`のsource treeが必要です。CIは両Artifact集合をexact-keyで検査し、本文field、Source欠落、digest drift、未Review状態の隠蔽、baseline縮小を拒否します。現在値はmatched 26、stale 0、failed 0、deferred 0、human reviewed 0、Authority semantics exhaustive falseです。
