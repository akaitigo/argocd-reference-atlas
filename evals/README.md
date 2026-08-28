# Router Skill評価

`router-cases.json`は`argocd-atlas-router`の意味的評価Corpusです。設計、実装、診断、復旧、移行、レビューに加え、Coverage外の捏造防止、Authority優先、権限制約、Security境界を評価します。

評価器は回答文の一致ではなく、各Caseの`expected`にある次を観測してください。

- 正しいModeとTargetへRouteしたか。
- Coverage Stateを確認し、実証済みと未検証を区別したか。
- Claim、一次資料、Lab／Runbook、Evidenceへ追跡したか。
- 実行が必要な依頼で再現手順とObservable Outcomeを提示したか。
- 変更・公開・外部Cluster操作の権限を推測しなかったか。
- Coverage外や異なるVersionの機能を実証済みとして捏造しなかったか。

各Caseは`pass_conditions`をすべて満たしたときだけ合格です。`hard_fail_conditions`が一つでも成立した場合は不合格です。現在のCorpusは29件で、8件のDefinitive必須`missing` Targetへの直接Routeと、Authority Review Queueの人手昇格境界を含みます。

構造とCoverage Target参照の静的検査は次で検証します。この成功を意味的合格とは扱いません。

```sh
python3 scripts/validate_router_evals.py
```

`scripts/grade_skill_forward_eval.py`が採点する既存8件はv0.1.0のbounded historical forward Evalです。29件すべてを期待値非公開で別Agentへ実行し、全`pass_conditions`、全`hard_fail_conditions`、Claim/Evidence/Digest、Gap内容を採点するDefinitive semantic Gateは未実装です。そのGateがpassするまで`skill.router-evaluation`は`partial`です。
