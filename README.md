# Fugle 分層掃描器（500 calls/day 版本）

這個專案實作一個適用於 Fugle API 限額（`500 calls/day`、`60 calls/min`）的「雙層掃描架構」，並整合 **v2/v3 + Pivot Points** 盤後評分。

## 架構重點

1. **一次性建立本地資料庫（滾動完成）**
   - 每天分批抓一部分股票歷史資料（例如 500 檔）
   - 3~4 天完成全市場初始化
2. **Layer 1 粗篩（流動性前 N 檔）**
   - 每日只更新成交值/成交量前 300~400 檔
3. **Layer 2 精篩（本地計算）**
   - 在本地資料上跑策略（v2 吸籌、v3 控盤突破、Pivot 低風險加分）
   - 不增加 API 呼叫

## 評分模型

### Pivot Points（以前一日高低收）

- `P = (High_prev + Low_prev + Close_prev) / 3`
- `R1 = 2*P - Low_prev`
- `S1 = 2*P - High_prev`
- `R2 = P + (High_prev - Low_prev)`
- `S2 = P - (High_prev - Low_prev)`

### v2（假跌破吸籌）

- `low_today < low_20d`
- `close_today > low_20d`
- `volume_today > avg_volume_5 * 1.5`
- 成立加 `30` 分

### v3（控盤/突破延續）

- `close_today > sma20 > sma60`
- `close_today >= high_20d`
- `volume_today > avg_volume_5`
- 核心成立加 `40` 分
- `low_today > low_3_days_ago` 再加 `10`
- 最近 5 日紅K >= 3 再加 `10`

### Pivot bonus

- `close_today <= S2` 加 `15`
- `close_today <= S1` 加 `10`
- `close_today > P` 加 `5`

### 總分與狀態

- `total_score = v2 + v3 + pivot_bonus`
- `total_score >= 70` ⇒ `Strong Candidate`
- 其他 ⇒ `Watch Only`

## 快速開始

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

設定環境變數：

```bash
export FUGLE_API_KEY="your_key"
export FUGLE_BASE_URL="https://api.fugle.tw"

# init-db only needs SCANNER_DB_PATH, no API key required
```

## 指令

### 1) 建立/更新資料庫

```bash
python -m scanner.main init-db
```

### 2) 分批初始化（每天跑一次）

```bash
python -m scanner.main bootstrap --symbols-file symbols.txt --batch-size 500 --offset 0
```

### 3) 每日分層掃描

```bash
python -m scanner.main daily-scan --top-liquidity 400 --top-candidates 50
```

輸出欄位：

```text
symbol  total_score  v2  v3  pivot_bonus  status
```

## symbols.txt 格式

每行一個股票代碼：

```text
2330
2317
2454
...
```

## 目錄

- `scanner/config.py`：設定管理
- `scanner/db.py`：SQLite schema 與資料寫入
- `scanner/rate_limiter.py`：60/min + 500/day 限流
- `scanner/fugle_client.py`：Fugle API 呼叫封裝
- `scanner/pipeline.py`：bootstrap + daily scan + v2/v3/pivot 評分
- `scanner/main.py`：CLI 入口（含 offset 分批初始化）

## 注意

- 實際 API path / 欄位命名可能需依 Fugle 帳號方案微調。
- `StrategyEngine` 目前實作為可直接替換的版本，便於你客製權重與門檻。
