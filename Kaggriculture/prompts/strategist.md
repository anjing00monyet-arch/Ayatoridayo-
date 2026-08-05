<!--
agents/strategist.py がこのテンプレートに以下を埋め込みます:
  {{ analysis_md }}    -- reports/latest_analysis.md の内容
  {{ baseline_src }}   -- submissions/baseline/main.py の内容
-->

# Kaggriculture 改善案（設計書）作成

あなたはKaggriculture現行エージェントの戦略立案担当です。以下の分析結果と
現行コードを踏まえ、改善案を**コードを書く前に**設計書として提示してください。
コードは次工程（コーディングエージェント）が書きます。ここでは方針だけを決めます。

## 分析結果

{{ analysis_md }}

## 現行コード（submissions/baseline/main.py）

```python
{{ baseline_src }}
```

## 出力フォーマット（改善案ごとに以下を全て埋めること。複数案があれば案ごとに区切る）

```
## 改善案: <一言タイトル>

### 根拠
<分析結果のどの数値が根拠か。例: 25日目以降に行われた投資のうち31%が回収不能。平均損失は1試合あたり8,420。>

### 変更箇所
<関数名・モジュール名を具体的に。例: choose_action(), evaluate_purchase(), evaluate_planting()>

### 数式・ロジック
<変更後のロジックを疑似コードか数式で。例:
expected_profit = expected_revenue - purchase_cost - worker_cost - maintenance_cost - opportunity_cost>

### 採用条件
<evaluation/acceptance_gate.py のどの閾値をどれだけ上回れば採用か>

### 変更してはいけない箇所
- 公式API（agent(observation, configuration) のシグネチャ）
- 観測データ形式
- アクション返却形式
```

複数案を出す場合は根拠が強い順に並べてください。
