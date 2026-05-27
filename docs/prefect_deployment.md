# Prefect 部署实施步骤

Prefect Server 地址：`http://192.168.31.236:4200`  
API 地址：`http://192.168.31.236:4200/api`

本文档说明如何把 quant-ripper 打包并放到 Prefect 3 上运行。优先推荐 Docker work pool；如果部署机已经有稳定 Python 环境，也可以使用 Process work pool。

官方参考：

- Prefect deployments：<https://docs.prefect.io/v3/concepts/deployments>
- Prefect Docker work pool：<https://docs.prefect.io/v3/deploy/infrastructure-examples/docker>

## 1. 前置检查

1. TDX API 可访问：`http://192.168.31.236:9999/api/health`。
2. Redis 可访问：`192.168.31.99:6379`，DB `9`。
3. QuestDB 可访问：
   - Console：`http://<questdb-host>:9005`
   - PGWire：`<questdb-host>:8812`
   - ILP TCP：`<questdb-host>:9009`
4. Prefect Server 可访问：`http://192.168.31.236:4200`。

## 2. 本地开发环境

Windows PowerShell：

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
```

Linux/macOS：

```bash
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

结论：本地开发和 Process worker 推荐使用虚拟环境；Docker worker 不依赖宿主机虚拟环境。

## 3. 配置文件

复制示例配置：

```powershell
Copy-Item config/example.env .env
```

重点检查这些配置：

```dotenv
TDX_API_BASE_URL=http://192.168.31.236:9999
REDIS_HOST=192.168.31.99
REDIS_PORT=6379
REDIS_DB=9

QUESTDB_PG_HOST=<questdb-host>
QUESTDB_PG_PORT=8812
QUESTDB_ILP_HOST=<questdb-host>
QUESTDB_ILP_PORT=9009
QUESTDB_ILP_PROTOCOL=tcp

PREFECT_API_URL=http://192.168.31.236:4200/api
```

如果 QuestDB ILP 需要完整官方 client 配置，可设置：

```dotenv
QUESTDB_ILP_CONF=tcp::addr=<questdb-host>:9009;protocol_version=2;
```

## 4. 打包方式

### 4.1 Python 包安装

开发或 Process worker 使用：

```powershell
.\.venv\Scripts\python.exe -m pip install -e .[prefect]
```

安装后可直接运行：

```powershell
.\.venv\Scripts\quant-ripper.exe health --env-file .env
```

### 4.2 Docker 镜像

构建镜像：

```powershell
docker build -t quant-ripper:0.1.0 .
```

验证镜像能启动：

```powershell
docker run --rm --env-file .env quant-ripper:0.1.0 quant-ripper health
```

如果 Prefect Docker worker 在另一台机器上运行，需要把镜像推送到该机器能拉取的镜像仓库：

```powershell
docker tag quant-ripper:0.1.0 <registry>/quant-ripper:0.1.0
docker push <registry>/quant-ripper:0.1.0
```

## 5. 连接 Prefect Server

```powershell
.\.venv\Scripts\prefect.exe config set PREFECT_API_URL=http://192.168.31.236:4200/api
.\.venv\Scripts\prefect.exe work-pool ls
```

只需设置 `PREFECT_API_URL` 并确认能列出 work pool；Prefect Server 的数据库升级应由 Server 运维流程单独处理。

## 6. Process Work Pool 部署

适合单机部署或先跑通链路。

创建 work pool：

```powershell
.\.venv\Scripts\prefect.exe work-pool create quant-ripper-process --type process
```

启动 worker：

```powershell
.\.venv\Scripts\prefect.exe worker start --pool quant-ripper-process
```

创建 deployments：

```powershell
.\.venv\Scripts\prefect.exe deploy src/quant_ripper/pipelines/flows.py:pre_market_flow `
  --name daily-pre-market `
  --pool quant-ripper-process `
  --cron "30 8 * * 1-5" `
  --timezone Asia/Shanghai `
  --param env_file=".env"

.\.venv\Scripts\prefect.exe deploy src/quant_ripper/pipelines/flows.py:watchlist_flush_flow `
  --name intraday-watchlist-flush `
  --pool quant-ripper-process `
  --cron "* 9-15 * * 1-5" `
  --timezone Asia/Shanghai `
  --param env_file=".env"
```

手动触发验证：

```powershell
.\.venv\Scripts\prefect.exe deployment run tdx-pre-market/daily-pre-market
```

## 7. Docker Work Pool 部署

适合生产隔离运行。Prefect 官方建议通过 work pool + worker 执行容器化 flow run。

创建 Docker work pool：

```powershell
.\.venv\Scripts\prefect.exe work-pool create quant-ripper-docker --type docker
```

启动 Docker worker：

```powershell
.\.venv\Scripts\prefect.exe worker start --pool quant-ripper-docker
```

部署时指定镜像和环境变量：

```powershell
.\.venv\Scripts\prefect.exe deploy src/quant_ripper/pipelines/flows.py:pre_market_flow `
  --name daily-pre-market `
  --pool quant-ripper-docker `
  --cron "30 8 * * 1-5" `
  --timezone Asia/Shanghai `
  --job-variable image=quant-ripper:0.1.0 `
  --job-variable "{""env"":{""PREFECT_API_URL"":""http://192.168.31.236:4200/api""}}"
```

如果容器里不挂载 `.env`，应把生产连接信息写入 `--job-variable` 的 `env` JSON，或配置到 Docker worker 的基础 job template 中。

## 8. 推荐调度

| Deployment | Flow | 建议计划 | 说明 |
|---|---|---|---|
| `daily-pre-market` | `tdx-pre-market` | 交易日 08:30 | 初始化表结构、刷新主数据。 |
| `intraday-quotes-1m` | `tdx-quotes-once` | 交易时段每分钟 | 参数传入全市场批次代码；大市场需要拆批。 |
| `watchlist-sample-3s` | `tdx-watchlist-sample` | 交易时段每 3 秒 | 只跑自选池或重点监控池。 |
| `watchlist-flush-1m` | `tdx-watchlist-flush` | 交易时段每分钟 | 聚合 Redis 样本并写 QuestDB。 |
| `daily-minute-backfill` | `tdx-minute-backfill` | 收盘后 | 补全分时走势。 |
| `daily-trade-backfill` | `tdx-trade-backfill` | 收盘后 | 成交明细按日覆盖写入。 |
| `daily-kline-backfill` | `tdx-kline-backfill` | 收盘后 | 更新 raw/qfq K 线。 |

## 9. 上线检查清单

- `python -m pytest -q` 全部通过。
- `quant-ripper health --env-file .env` 能看到 TDX、Redis、QuestDB SQL 均为 ok。
- `quant-ripper init-schema --env-file .env` 可以创建 QuestDB 表。
- `quant-ripper collect-quotes --codes 000001 --env-file .env` 可以写入 `quote_snapshot_1m`。
- Prefect UI 中能看到 deployment、worker online、flow run 日志。
- QuestDB Console 中能查询到 `api_ingestion_log` 和对应事实表新增行。

## 10. 故障处理

- Prefect UI 没有 flow run：检查 deployment 是否启用、schedule 时区是否为 `Asia/Shanghai`、worker 是否 online。
- Worker 拉不到代码：Process worker 检查虚拟环境是否安装 `-e .[prefect]`；Docker worker 检查镜像是否存在并能访问。
- QuestDB 写入失败：检查 `QUESTDB_ILP_CONF` 或 `QUESTDB_ILP_HOST/PORT`，以及 ILP TCP `9009` 是否开放。
- DELETE 失败：检查 PGWire `8812`、账号密码和 `QUESTDB_PGWIRE_REQUIRED`。
- Redis key 不删除：确认 `flush_watchlist` 未使用 `--keep-keys`，并检查 QuestDB 写入是否成功。
