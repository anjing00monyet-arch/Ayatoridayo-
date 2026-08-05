<!--
agents/coder.py がこのテンプレートに以下を埋め込みます:
  {{ proposal_md }}   -- strategist が採用した1つの改善案（設計書）
  {{ baseline_src }}  -- submissions/baseline/main.py の内容
-->

# Kaggriculture 改善案の実装

あなたはKaggriculture現行エージェントのコーディング担当です。以下の設計書
どおりに `submissions/baseline/main.py` を書き換えてください。

## 採用された改善案

{{ proposal_md }}

## 現行コード

```python
{{ baseline_src }}
```

## 制約（厳守）

- 設計書の「変更してはいけない箇所」に書かれた項目は一切変更しないこと。
- `agent(observation, configuration)` のシグネチャと戻り値の形式は変えないこと。
- 設計書に書かれていない挙動を勝手に追加しないこと。
- 差分は最小限にすること。

## 出力

修正後の `main.py` の**全文**を、単一のPythonコードブロックとして出力してください。
説明文は不要です。コードブロックの前後に一切テキストを置かないでください。
