# Suunto Data Downloader 项目记忆

本项目是面向 Suunto（颂拓）中国版与国际版的全套数据提取与分析工具（MIT 许可证）。
包含两大部分：
1. **运动记录下载**（Workout Sync）：通过 `cloud-api.suunto.cn` 下载 FIT + JSON，并支持批量规范化重命名。
2. **全天候健康数据下载**（Health / Asko Timeline Sync）：通过 `247.suunto-operations.cn` 下载日常心率、步数、卡路里、身体电量（Resources）、压力、睡眠总览与分期、夜间高频 HRV，并支持转为 CSV 表格。

---

## 核心架构与端点速查

* **认证方式**：HTTP Header 自定义字段 `STTAuthorization: <sessionKey>`（非 Bearer）。
  * 提取来源：Root 手机 `/data/data/com.stt.android.suunto.china/databases/amer_app.db` 中 `user` 表的 `session` 字段。
  * 配置文件：根目录 `config.json`（已加入 `.gitignore`）。

* **运动数据端点（Workout API）**：
  * Base URL：`https://cloud-api.suunto.cn/apiserver/v1`
  * 列表：`/workouts/?limit={limit}&offset={offset}`（每页上限 200）
  * FIT 导出：`/workout/exportFit/{key}?autogeneraterecords=true&...`
  * JSON 导出：`/workouts/{key}/ultimatemanager`（SML DeviceLog 格式）

* **健康数据端点（Asko Timeline API）**：
  * Base URL：`https://247.suunto-operations.cn`（国际版为 `https://247.sports-tracker.com`）
  * 流式导出（NDJSON 响应，支持 `?since={timestamp_ms}`）：
    * `/v1/activity/export`：10分钟粒度心率（**Hz，乘 60 为 bpm**）、步数、活动能量（焦耳 J，除以 4184 为 kcal）
    * `/v1/recovery/export`：身体电量百分比（0.0~1.0）、压力状态枚举
    * `/v1/sleep/export`：每日睡眠时长、深睡、平均/最低心率、HRV均值、睡眠质量
    * `/v1/sleepstages/export`：睡眠分期时间片（LIGHT / DEEP / REM / AWAKE 及持续秒数）
    * `/v1/sleephrvsamples/export`：夜间连续毫秒级 HRV 采样点

---

## 核心脚本清单

| 脚本 | 职责 |
|------|------|
| `suunto_sync.py` | 运动数据增量同步（下载 FIT + JSON，自动校验 FIT 完整性） |
| `suunto_rename.py` | 运动数据规范重命名（workoutKey $\to$ `{Sport}_{DateTime}`） |
| `suunto_health_sync.py` | 全天候健康数据流式同步（支持增量与 `--full` 全量，按月落盘 `.ndjson`） |
| `convert_ndjson.py` | 健康数据转换工具（批量转为 CSV，自动完成 Hz $\to$ bpm 等物理量换算） |
| `scripts/extract_token.py` | 从 `amer_app.db` 提取 sessionKey 的辅助脚本 |

---

## 本地 SQLite 关键表结构（amer_app.db）

手机端本地 Jetpack Room 数据库同样存储着完整健康数据：
- `sleepsegments`：睡眠汇总（含 25 项详细指标）
- `sleep_stage_intervals`：睡眠分期明细
- `sleep_hrv_samples`：睡眠 HRV 采样序列
- `recoverydata`：恢复电量与压力
- `user`：用户身份与 session

---

## 操作规范与红线
1. **凭据请求不走代理**：带 `STTAuthorization` 的 API 请求严格走直连（失败即停，不回退本地代理）。
2. **保护正式目录**：绝对不要修改 `~/Documents/Workouts/` 目录；所有下载操作均在项目内的 `data/` 目录中完成。
3. **环境保持整洁**：依赖仅限标准库与可选的 `fitdecode`，禁止向宿主全局环境安装杂乱包。
