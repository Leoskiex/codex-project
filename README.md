# TW Top-Stock Scanner (yfinance)

這個專案使用 **yfinance**，不需要 API key，也不需要再處理 Fugle 的每日/每分鐘呼叫上限。

## 核心做法

1. 預設追蹤 `TOP_SYMBOLS`（20 檔台股高流動性權值股）
2. 每日更新這些股票的最新日 K
3. 在本地用 **v2/v3 + Pivot Points** 打分與排序

> 雖然不再受 Fugle 額度限制，仍建議先從熱門股開始，訊號品質與執行效率會更穩定。

## 評分模型（台股日掃）

- `v2` 假跌破吸籌：最高 30 分
- `v3` 趨勢/突破/量能 + 延續：最高 60 分
- `Pivot bonus`：支撐位低風險加分 + 趨勢確認：最高 20 分
- `total_score >= 70` ⇒ `Strong Candidate`

## 額外策略：Quality 90 日動能（月度再平衡）

你可以把它當成另一個 spectrum（中期趨勢）策略：

1. `momentum_90d = close_now / close_90d_ago - 1`
2. 篩選：`momentum_90d > 0.15`
3. 排名：依 `momentum_90d` 由高到低，取前 `top_n`
4. 進場：每月第一個交易日等權重買入
5. 出場：下個月再平衡（若跌破門檻，將被剔除）

## 安裝

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 環境變數

```bash
export SCANNER_DB_PATH="market.db"
# 可選：覆蓋預設熱門股清單（逗號分隔，yfinance ticker 格式）
export TOP_SYMBOLS="2330.TW,2317.TW,2454.TW"
```

## 指令

```bash
python -m scanner.main init-db
python -m scanner.main bootstrap --batch-size 20
python -m scanner.main daily-scan --top-liquidity 20 --top-candidates 10
```

如果你有自己的清單檔案：

```bash
python -m scanner.main bootstrap --symbols-file symbols.txt --batch-size 50 --offset 0
python -m scanner.main daily-scan --symbols-file symbols.txt --top-liquidity 30 --top-candidates 15
```

`symbols.txt` 一行一個 ticker（例如 `2330.TW`）。

## Quality 動能模擬

### 線上抓資料（需要可連外）

```bash
python -m scanner.main quality-sim \
  --symbols "NVDA,AAPL,MSFT,GOOGL,META,AMZN,AMD" \
  --lookback-days 90 \
  --threshold 0.15 \
  --top-n 3 \
  --period 3y
```

### 離線 CSV 模擬（本 repo 範例）

```bash
python -m scanner.main quality-sim \
  --symbols "NVDA,AAPL,MSFT,GOOGL,META,AMZN,AMD" \
  --prices-file examples/quality_demo_prices.csv \
  --lookback-days 90 \
  --threshold 0.15 \
  --top-n 3
```

CSV 欄位：`symbol,trade_date,close`

## Top-100 → Top-20/Top-30 Pipeline（離線可跑）

專案提供一份清單與示例資料：

- `examples/tw_top100_symbols.txt`：Top 100 symbols
- `examples/tw_top100_demo_prices.csv`：示例收盤價序列

執行：

```bash
python -m scanner.main quality-pipeline \
  --symbols-file examples/tw_top100_symbols.txt \
  --prices-file examples/tw_top100_demo_prices.csv \
  --top-core 20 \
  --top-quality 20 \
  --lookback-days 90 \
  --threshold 0.15
```

輸出包含：

1. Core basket（前 20）
2. Quality picks（90 日動能門檻後取前 20）
3. Top 30 momentum spectrum（7/14/21/30/60/90 日）與狀態：
   - `Increasing`：短天期動能 > 長天期動能（加速）
   - `Dropping Off`：短天期動能 < 長天期動能（降速）
   - `Mixed`：其餘型態

## 輸出欄位

```text
symbol  total_score  v2  v3  pivot_bonus  status
```
