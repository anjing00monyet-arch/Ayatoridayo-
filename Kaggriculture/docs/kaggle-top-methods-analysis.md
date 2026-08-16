# Kaggle上位者手法アナリシス — Kaggriculture改善への示唆

作成日: 2026-08-16
対象リクエスト: https://kaggle.farid.one/ にまとまっているKaggle上位者の情報・手法を解析し、Kaggriculture（`agents/` `harness/` `replay_analyzer/` `experiments/` `results/` `tools/` `docs/` 構成）の改善に役立てる。

## 0. 調査方法と制約（重要）

このセッションのネットワークegressポリシーにより、`kaggle.farid.one` および `www.kaggle.com` への直接アクセスはブロックされています（組織ポリシーによる403denyで、回避せず報告する運用ルール）。そのため以下の2段構えで調査しました。

1. **実データ**: `kaggle.farid.one` の情報源である公開GitHubリポジトリ [`faridrashidi/kaggle-solutions`](https://github.com/faridrashidi/kaggle-solutions) を clone し、`data/competitions.yml`（713コンペ分のタイトル・種別・順位・解法リンクのインデックス）を直接解析。これは実際にサイトが描画しているデータそのものです。
2. **一般知識による補完**: 解法本文（`kaggle.com/.../writeups/...` や `discussion/...`）自体は同ポリシーでブロックされているため本文は読めていません。そのため、同系統（マルチエージェント／自己対戦シミュレーション）のKaggleコンペで繰り返し観測されてきた勝者パターンを、学習済み知識から整理しています。**個別の解法を引用しているのではなく、傾向の一般化**である点に留意してください。

なお、インデックス内に「Kaggriculture」という名前のコンペは見つかりませんでした。以下は近縁コンペ（自己対戦・マルチエージェント・探索/RL系）を代理指標として使っています。

## 1. 参考にした近縁コンペ（インデックスより実データ）

Kaggriculture のフォルダ構成（`agents/` = ボット実装、`harness/` = 評価環境、`replay_analyzer/` = リプレイ解析）は、Kaggleの「シミュレーション/マルチエージェント」系コンペの典型的な参加者リポジトリ構成と一致します。近い性質のコンペとその上位解法タイトル（本文未読・タイトルのみ）:

| コンペ | 年 | 種別 | 概要 | 上位解法タイトルから読める傾向 |
|---|---|---|---|---|
| [Orbit Wars](https://www.kaggle.com/c/orbit-wars) | 2026 | Featured | 連続2D空間での惑星争奪RTS（2〜4人） | 1位「scaling reinforcement learning」、6位「RL league + search + custom edge attention」、9位「end-to-end JAX PPO」、48位「critic-free RL for adversarial games」、49位「imitation learning」 |
| [Maze Crawler](https://www.kaggle.com/c/maze-crawler) | 2026 | Playground | fog-of-warありの無限迷路1v1 | 7位「Hungarian matching によるグローバルタスク最適化」、5位「ほぼ探索なしのルールベースbot」 |
| [The 2026 NeuroGolf Championship](https://www.kaggle.com/c/neurogolf-2026) | 2026 | Research | ARC-AGI変換を解く最小ニューラルネット設計 | 1位「kaggle agent」、多数が「LLMエージェント + 検証ループ」系のタイトル（例:「guarded agent loop」「representation collapse」） |
| [FIDE & Google Efficient Chess AI Challenge](https://www.kaggle.com/c/fide-google-efficiency-chess-ai-challenge) | 2025 | Featured | リソース制約下でのチェスAI | 「efficient」を掲げる通り、探索深さ・推論コストのトレードオフが主戦場 |
| [LLM 20 Questions](https://www.kaggle.com/c/llm-20-questions) | 2024 | Featured | LLM同士の協調・推理ゲーム | エージェント同士の対戦評価・プロンプト設計・堅牢性が主題 |
| [UM - Game-Playing Strength of MCTS Variants](https://www.kaggle.com/c/um-game-playing-strength-of-mcts-variants) | 2024 | Research | MCTS変種の強さ予測（数百種のボードゲーム） | 探索ハイパーパラメータはゲーム特性に強く依存、という前提そのものが出題テーマ |
| [Google Research Football](https://www.kaggle.com/c/google-football) | 2020 | Featured | サッカーAIエージェント訓練 | self-play RL + 模倣学習 + ルールベース補助の組み合わせが定番だった世代 |

（本文はブロックのため未読。タイトルと構成から抽出できる範囲の情報です。リンクはユーザー側で開けば本文を確認できます。）

## 2. マルチエージェント/シミュレーション系Kaggleコンペで繰り返し observed される勝者パターン

Halite, Lux AI, kore-2022, Hungry Geese, Connect X, Google Football など過去のシミュレーション系コンペ全般で共通して報告されてきたパターンを、上記の近縁コンペのタイトルからも裏付けが取れる範囲で整理します。

### 2.1 評価基盤（harness）への先行投資が最大の差別化要因
- 上位勢は「まずKaggleに提出して待つ」のではなく、**ローカルで高速に自己対戦できる環境**を最初に作る。提出→結果待ちのループはボトルネックになりやすい。
- 自前のレーティング（Elo / TrueSkill的な相対強さ指標）で、エージェントのバージョン間比較をリーダーボード提出なしに行う。
- 並列化されたトーナメント実行（多コアでの大量自己対戦）で統計的に意味のある勝率差を素早く検出する。
- 1手あたりの思考時間制限に対する計測・ロギングを組み込み、タイムアウト＝即敗北のリスクを可視化する。

### 2.2 ベースラインは「弱くていいから早く」、その後に段階的差し替え
- 初手はルールベース／貪欲法の単純なエージェントで土台を作り、harness・提出パイプライン・リプレイ確認の一連の流れを先に確立する。
- そこから「ヒューリスティック → 探索（MCTS/minimax）→ 学習（RL/模倣学習）」の順に段階的に高度化するのが典型的な成功パターン。Maze Crawlerの5位「ほぼ探索なしのルールベースbot」が上位に食い込んでいるのも、シンプルな解が侮れないことの実例。

### 2.3 探索ベース（MCTS/minimax）は推論コスト制約下で強い
- 完全情報・決定的なゲームでは、手番あたりの計算予算内で回せる探索＋評価関数が、学習コストの高いRLより短期間で強くなりやすい。
- FIDEチェスAIコンペのように「efficient」を掲げる出題では、探索深さと計算コストのトレードオフ設計そのものが勝敗を分ける。
- Maze Crawler 7位の「Hungarian matching によるグローバルタスク最適化」のように、局所探索ではなく大域最適化（割当問題として定式化）で殻を破るケースもある。

### 2.4 RL（自己対戦強化学習）で勝つための定石
- 疎な勝敗報酬だけでは学習が遅すぎるため、序盤は補助報酬（資源獲得量・生存時間・領土支配など）で shaping し、終盤にかけて本来の目的（勝敗）に比重を戻すアニーリングが定番。
- 弱い/スクリプト化された相手からの curriculum → 自己対戦、という順序で学習を安定させる。いきなり自己対戦から始めると縮退解に陥りやすい。
- 過去チェックポイントのプールを保持し多様な相手と対戦させる（PFSP的な発想）ことで、自己対戦特有の「堂々巡り」による弱点固定化を防ぐ。
- Orbit Wars 9位「end-to-end JAX PPO」、48位「critic-free RL」など、学習の高速化（JAX等での並列シミュレーション）とアルゴリズムの単純化（critic省略）はいずれも「1イテレーションを速く回す」ことを重視した選択と読める。

### 2.5 状態表現とアクションマスキング
- 盤面をエージェント視点（egocentric）でチャンネル化してCNN/Transformerに入力するのが定番。
- 合法手のみを選択肢に絞る action masking を入れないと、学習シグナルの大半が不正手のペナルティ学習に浪費される。

### 2.6 模倣学習・アンサンブル・フェーズ別戦略
- 公開されている上位リプレイからの模倣学習（imitation learning）で立ち上がりを速める手法は複数コンペで安定して上位に入る（Orbit Wars 49位も該当）。
- 単一方策ではなく、ゲームフェーズ（序盤/中盤/終盤）やユニット役割ごとに専用の方策・ヒューリスティックを切り替える設計もRTS系では頻出。

### 2.7 「メタへの過学習」は終盤で裏目に出る
- リーダーボード上の見えている上位bot群だけに最適化すると、締切間際のメタ変化やプライベート評価で崩れるリスクがある。多様な戦略への頑健性を検証データとして重視する。

### 2.8 実験管理と統計的健全性
- 自己対戦RL/探索チューニングは乱数シード間分散が大きいため、複数シード（3〜5以上）の平均で比較しないと「たまたま勝った」変更を採用してしまう。
- 何を変えて何が効いたかを都度ドキュメント化する運用（Kaggleのwriteup文化そのもの）を、社内実験でも継続することが再現性・引き継ぎ性を高める。

### 2.9 2025〜2026年の新潮流: LLMエージェント + 検証ガード層
- NeuroGolf 2026の解法タイトル群（「kaggle agent」「guarded agent loop」「representation collapse」）から読み取れるように、program synthesis / ARC-AGI系タスクではLLMエージェントに探索・検証レイヤーを組み合わせる設計が主流になりつつある。
- LLMエージェントを行動決定に使う場合、(a) 出力を有効なアクション文法に制約する、(b) 不正・幻覚出力をharness側で弾くガード層を用意する、(c) 全エージェント思考過程をログしてreplay_analyzerで事後検証できるようにする、の3点が定石化している。

## 3. Kaggriculture構成への具体的なマッピング

| フォルダ | 現状 | 上記知見からの改善提案 |
|---|---|---|
| `harness/` | 空 | ①ローカル高速自己対戦ランナー ②簡易Elo/レーティング集計 ③並列トーナメント実行 ④手番あたりの思考時間・メモリ計測とタイムアウト検知のロギング ⑤決定的な乱数シード管理 |
| `agents/` | 空 | ①まずルールベース/貪欲法のベースラインを1本用意し harness を先に通す ②探索ベース(MCTS/minimax)エージェントを次段として実装 ③学習ベース(RL/模倣学習)は最後、報酬shaping・action masking・curriculumを設計 ④例外時に必ず合法手を返すフェイルセーフ実装 |
| `replay_analyzer/` | 空 | ①リプレイをステップ実行できるビューア ②2バージョンのエージェントのリプレイを手ごとに diff する仕組み ③（もし公開リプレイが手に入るなら）上位bot挙動の模倣学習用データ抽出 ④LLMエージェントを使う場合は思考過程ログも解析対象に含める |
| `experiments/` | 空 | ①設定(config)と結果を1対1で紐付ける構造 ②複数シード実行を前提にした比較テンプレート ③ablationの記録フォーマット |
| `results/` | 空 | ①対戦相手別勝率・Elo推移・シード間分散を含む統一ロギングスキーマ |
| `tools/` | 空 | ①思考時間/メモリのプロファイラ ②合法手検証ツール ③config差分ツール |
| `docs/` | 本ファイルのみ | 継続的にwriteup文化（何を変えて何が効いたか）をここに残す運用を推奨 |

## 4. 優先アクション（提案）

1. **harness最優先**: 何より先にローカル自己対戦＋簡易レーティングの仕組みを作る。これがないと以降の改善サイクルが全て「提出して待つ」になり遅くなる。
2. **弱くてよいのでベースラインagentを1本通す**: ルールベースで良いのでagents/harness/replay_analyzerの一連のパイプラインを早期に通し、以降は差し替え式で強化する。
3. **replay diffツールを早期に用意**: エージェント変更のたびに「何が変わったか」を人間が見て検証できないと、シード分散に埋もれた偽陽性の改善を採用してしまうリスクが高い。
4. **実験は複数シード前提で設計**: experiments/results のフォーマットを最初から複数シード集計前提にしておく。
5. **対象コンペの具体的なルール（手番制限・観測情報・報酬/評価指標）が分かれば、上記の一般論をそのコンペ固有の設計（探索 vs RL の選択、報酬shapingの中身など）に落とし込める。**

## 5. 出典・参考情報

- サイト情報源（実データ）: [faridrashidi/kaggle-solutions (GitHub)](https://github.com/faridrashidi/kaggle-solutions) — `data/competitions.yml`
- サイト概要: [kaggle.farid.one について - 検索結果より](https://farid.one/kaggle-solutions/)（このセッションからは直接アクセス不可、Web検索結果を参照）
- 個別解法の本文は `www.kaggle.com` がこのセッションのネットワークポリシーでブロックされているため未読。上記URLは今後アクセス可能な環境で参照する用のリンクとして記載。
