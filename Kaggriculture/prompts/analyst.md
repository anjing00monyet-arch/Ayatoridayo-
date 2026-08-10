<!--
agents/analyst.py がこのテンプレートに以下を埋め込みます:
  {{ n_matches }}       -- 集計した試合数
  {{ aggregate_json }}  -- analysis/profit_breakdown.aggregate() の出力
  {{ top_failures }}    -- analysis/profit_breakdown._top_failures() の出力
  {{ action_stats }}    -- analysis/action_analysis.analyze_matches() の出力
-->

# Kaggriculture 敗因分析レポート作成

あなたはKaggriculture現行エージェントの分析担当です。{{ n_matches }}試合分の
集計データから、利益を損なっている要因を特定してください。

## 集計データ

```json
{{ aggregate_json }}
```

## 頻出する重大な失敗パターン

{{ top_failures }}

## 行動タイミング統計

```json
{{ action_stats }}
```

## 出力フォーマット（`reports/latest_analysis.md` にそのまま保存されます）

1. **サマリー**（現状の平均銀行残高・最悪シナリオ・クラッシュ有無を1〜2文で）
2. **利益を損なっている要因トップ3**（各要因について: 発生頻度、平均損失額、根拠データ）
3. **収益構造**（作物・畜産物ごとの実利益、コスト内訳の偏り）
4. **改善余地のある行動パターン**（遊休ターン、水やり・給餌の遅れ、売却タイミングなど）
5. **次の戦略立案エージェントへの申し送り事項**

数値の伴わない主観的な指摘は避け、必ず集計データの数値を引用してください。
