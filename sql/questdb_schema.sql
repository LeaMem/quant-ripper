-- QuestDB schema for TDX market data landing.
-- Unit convention:
--   price fields: li, 1 yuan = 1000 li
--   amount fields: li
--   quantity/volume fields: shares
-- Source convention:
--   source = tdx / ths / manual / exchange / broker / akshare
--
-- QuestDB dedup convention:
--   The designated timestamp column must be included in DEDUP UPSERT KEYS.

CREATE TABLE IF NOT EXISTS instrument (
  ts TIMESTAMP,
  code SYMBOL,
  exchange SYMBOL,
  asset_type SYMBOL,
  name STRING,
  listed_date SYMBOL,
  delisted_date SYMBOL,
  status SYMBOL,
  last_price LONG,
  source SYMBOL
) TIMESTAMP(ts) PARTITION BY MONTH WAL
DEDUP UPSERT KEYS(ts, code, asset_type, source);

CREATE TABLE IF NOT EXISTS instrument_daily_snapshot (
  ts TIMESTAMP,
  trade_date SYMBOL,
  code SYMBOL,
  exchange SYMBOL,
  asset_type SYMBOL,
  name STRING,
  listed_date SYMBOL,
  delisted_date SYMBOL,
  status SYMBOL,
  last_price LONG,
  source SYMBOL
) TIMESTAMP(ts) PARTITION BY MONTH WAL
DEDUP UPSERT KEYS(ts, code, asset_type, source);

CREATE TABLE IF NOT EXISTS trading_calendar (
  ts TIMESTAMP,
  date_numeric SYMBOL,
  is_trading_day BOOLEAN,
  source SYMBOL
) TIMESTAMP(ts) PARTITION BY YEAR WAL
DEDUP UPSERT KEYS(ts, date_numeric, source);

CREATE TABLE IF NOT EXISTS quote_snapshot_1m (
  ts TIMESTAMP,
  trade_date SYMBOL,
  collected_at TIMESTAMP,
  server_ts TIMESTAMP,
  code SYMBOL,
  exchange SYMBOL,
  asset_type SYMBOL,
  prev_close LONG,
  open_price LONG,
  high_price LONG,
  low_price LONG,
  last_price LONG,
  total_volume LONG,
  current_volume LONG,
  amount LONG,
  inside_volume LONG,
  outside_volume LONG,
  rate DOUBLE,
  bid1_price LONG,
  bid1_qty LONG,
  bid2_price LONG,
  bid2_qty LONG,
  bid3_price LONG,
  bid3_qty LONG,
  bid4_price LONG,
  bid4_qty LONG,
  bid5_price LONG,
  bid5_qty LONG,
  ask1_price LONG,
  ask1_qty LONG,
  ask2_price LONG,
  ask2_qty LONG,
  ask3_price LONG,
  ask3_qty LONG,
  ask4_price LONG,
  ask4_qty LONG,
  ask5_price LONG,
  ask5_qty LONG,
  source SYMBOL
) TIMESTAMP(ts) PARTITION BY DAY WAL
DEDUP UPSERT KEYS(ts, code, source);

CREATE TABLE IF NOT EXISTS orderbook_feature_1m (
  ts TIMESTAMP,
  trade_date SYMBOL,
  code SYMBOL,
  asset_type SYMBOL,
  first_last_price LONG,
  last_last_price LONG,
  last_price LONG,
  spread LONG,
  avg_spread DOUBLE,
  max_spread LONG,
  mid_price LONG,
  bid_depth_5 LONG,
  ask_depth_5 LONG,
  depth_imbalance DOUBLE,
  avg_depth_imbalance DOUBLE,
  max_depth_imbalance DOUBLE,
  last_depth_imbalance DOUBLE,
  active_buy_ratio DOUBLE,
  order_pressure DOUBLE,
  sample_count INT,
  quote_count INT,
  source SYMBOL
) TIMESTAMP(ts) PARTITION BY DAY WAL
DEDUP UPSERT KEYS(ts, code, source);

CREATE TABLE IF NOT EXISTS bar_intraday (
  ts TIMESTAMP,
  trade_date SYMBOL,
  code SYMBOL,
  asset_type SYMBOL,
  bar_type SYMBOL,
  adjustment SYMBOL,
  open_price LONG,
  high_price LONG,
  low_price LONG,
  close_price LONG,
  prev_close LONG,
  volume LONG,
  amount LONG,
  source SYMBOL
) TIMESTAMP(ts) PARTITION BY MONTH WAL
DEDUP UPSERT KEYS(ts, code, bar_type, adjustment, source);

CREATE TABLE IF NOT EXISTS bar_eod (
  ts TIMESTAMP,
  code SYMBOL,
  asset_type SYMBOL,
  bar_type SYMBOL,
  adjustment SYMBOL,
  open_price LONG,
  high_price LONG,
  low_price LONG,
  close_price LONG,
  prev_close LONG,
  volume LONG,
  amount LONG,
  up_count INT,
  down_count INT,
  source SYMBOL
) TIMESTAMP(ts) PARTITION BY YEAR WAL
DEDUP UPSERT KEYS(ts, code, bar_type, adjustment, source);

CREATE TABLE IF NOT EXISTS adjust_factor (
  updated_at TIMESTAMP,
  code SYMBOL,
  ex_date SYMBOL,
  factor DOUBLE,
  source SYMBOL
) TIMESTAMP(updated_at) PARTITION BY YEAR WAL
DEDUP UPSERT KEYS(updated_at, code, ex_date, source);

CREATE TABLE IF NOT EXISTS minute_trend (
  ts TIMESTAMP,
  trade_date SYMBOL,
  actual_date SYMBOL,
  code SYMBOL,
  asset_type SYMBOL,
  price LONG,
  volume LONG,
  source SYMBOL
) TIMESTAMP(ts) PARTITION BY DAY WAL
DEDUP UPSERT KEYS(ts, code, source);

CREATE TABLE IF NOT EXISTS trade_print (
  ts TIMESTAMP,
  trade_date SYMBOL,
  code SYMBOL,
  asset_type SYMBOL,
  price LONG,
  volume LONG,
  side INT,
  trade_count INT,
  source SYMBOL
) TIMESTAMP(ts) PARTITION BY DAY WAL;

CREATE TABLE IF NOT EXISTS api_ingestion_log (
  ts TIMESTAMP,
  source SYMBOL,
  endpoint SYMBOL,
  request_key STRING,
  status SYMBOL,
  latency_ms LONG,
  row_count LONG,
  error_message STRING
) TIMESTAMP(ts) PARTITION BY MONTH WAL;

CREATE TABLE IF NOT EXISTS ingestion_checkpoint (
  ts TIMESTAMP,
  source SYMBOL,
  endpoint SYMBOL,
  code SYMBOL,
  asset_type SYMBOL,
  data_type SYMBOL,
  bar_type SYMBOL,
  adjustment SYMBOL,
  last_success_ts TIMESTAMP,
  last_success_trade_date SYMBOL,
  status SYMBOL
) TIMESTAMP(ts) PARTITION BY MONTH WAL
DEDUP UPSERT KEYS(ts, source, endpoint, code, data_type, bar_type, adjustment);
