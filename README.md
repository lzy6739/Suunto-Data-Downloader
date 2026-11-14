# Suunto 运动数据下载器

从 Suunto 云服务器批量下载运动数据（FIT + JSON 文件）到本地电脑的工具。

## 功能特性

- **增量同步** — 只下载缺失的文件，已下载的自动跳过
- **双格式支持** — 同时下载 FIT（ Garmin 通用格式）和 JSON（SML DeviceLog 原始数据）
- **FIT 完整性验证** — 下载后自动校验数据完整性（需安装 fitdecode）
- **批量重命名** — 将 workoutKey 文件名转为可读的 `{运动类型}_{日期时间}` 格式
- **中国版 / 国际版** — 默认中国版 API，可切换国际版

## 快速开始

### 1. 安装依赖

```bash
# 创建虚拟环境（推荐）
python3 -m venv .venv
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

> `fitdecode` 是可选依赖。如果不安装，同步仍可正常工作，只是不会进行 FIT 文件验证。

### 2. 获取 Session Token

本工具通过 Suunto 云 API 下载数据，需要一个有效的 session key 进行认证。

Token 存储在手机端 Suunto APP 的本地数据库中，需要通过 ADB 提取。

**简要步骤：**

1. 在 Android 手机上安装 Suunto 中国版 APP（`com.stt.android.suunto.china`）
2. 登录账号并同步运动数据
3. 开启 USB 调试，连接电脑
4. 通过 ADB + root 权限复制 `amer_app.db` 数据库文件
5. 使用辅助脚本提取 session key

**详细指南请阅读 [docs/TOKEN_ACQUISITION.md](docs/TOKEN_ACQUISITION.md)**

### 3. 配置

```bash
cp config.example.json config.json
```

编辑 `config.json`，填入你的 session key：

```json
{
  "session_key": "你提取到的session_key",
  "api_base_url": "https://cloud-api.suunto.cn/apiserver/v1",
  "output": {
    "fit_dir": "./data/fit",
    "json_dir": "./data/json"
  },
  "sync": {
    "page_size": 200,
    "download_delay": 0.3,
    "validate_fit": true
  }
}
```

### 4. 运行同步

```bash
# 增量同步所有 FIT + JSON 文件
python3 suunto_sync.py

# 预览模式：查看缺失文件，不实际下载
python3 suunto_sync.py --dry-run

# 只同步 FIT 文件
python3 suunto_sync.py --fit-only

# 只同步 JSON 文件
python3 suunto_sync.py --json-only

# 列出所有运动及下载状态
python3 suunto_sync.py --list
```

### 5. 批量重命名（可选）

同步完成后，可将文件从 workoutKey 格式重命名为可读格式：

```bash
# 预览重命名结果
python3 suunto_rename.py --dry-run

# 执行重命名
python3 suunto_rename.py
```

重命名规则：
- FIT: `{运动类型}_{YYYY-MM-DD}T{HH_mm_ss}.fit`（留在 `data/fit/` 目录）
- JSON: `{运动类型}_{YYYY-MM-DD}T{HH_mm_ss}.json`（按年份归入 `data/json/{年份}/` 子目录）

## 配置说明

| 字段 | 说明 | 默认值 |
|------|------|--------|
| `session_key` | Suunto 云 API 认证 token（必填） | 空 |
| `api_base_url` | API 基础 URL | `https://cloud-api.suunto.cn/apiserver/v1` |
| `output.fit_dir` | FIT 文件保存路径 | `./data/fit` |
| `output.json_dir` | JSON 文件保存路径 | `./data/json` |
| `sync.page_size` | 分页大小（API 最大 200） | `200` |
| `sync.download_delay` | 下载间隔秒数（避免限流） | `0.3` |
| `sync.validate_fit` | 下载后是否验证 FIT 文件 | `true` |

路径支持相对路径（以脚本所在目录为基准）和绝对路径。

## 命令行参数

### suunto_sync.py

| 参数 | 说明 |
|------|------|
| `--config PATH` | 指定配置文件路径（默认: `config.json`） |
| `--dry-run` | 仅显示缺失文件，不执行下载 |
| `--fit-only` | 只同步 FIT 文件 |
| `--json-only` | 只同步 JSON 文件 |
| `--list` | 列出所有运动及下载状态 |

### suunto_rename.py

| 参数 | 说明 |
|------|------|
| `--config PATH` | 指定配置文件路径（默认: `config.json`） |
| `--dry-run` | 预览重命名结果，不实际执行 |

## 运动类型映射

重命名脚本使用以下映射将 API 的 `ActivityType` 转为运动名称：

| ActivityType | 运动名称 |
|:---:|---|
| 2 | Multisport |
| 3 | Running |
| 4 | Cycling / Walking* |
| 5 | MountainBiking |
| 6 | Swimming |
| 12 | Walking / Running* / Hiking* |
| 17 | IndoorCycling |
| 18 | CircuitTraining |
| 23 | Gym |
| 25 | Soccer |
| 27 | Volleyball |
| 35 | TableTennis |
| 43 | TrackRunning |
| 75 | Orienteering |
| 82 | TrailRunning |
| 93 | Treadmill |
| 96 | Hiking / Walking* |
| 100 | Chores |
| 105 | E-Biking |

> \* 标记的运动类型存在歧义，通过 API 返回的 `activityId` 进行消歧。

## 切换国际版 API

如果你使用的是 Suunto 国际版 APP（非中国版），可以尝试修改 `config.json`：

```json
{
  "api_base_url": "https://cloud-api.suunto.com/apiserver/v1"
}
```

> 注意：国际版 API 的认证方式和端点可能有所不同，如遇到问题请提交 Issue。

## 故障排除

### 认证失败 (HTTP 401/403)

Session key 已过期。请重新从手机提取 `amer_app.db` 并更新 `config.json`。

### 配置文件不存在

```bash
cp config.example.json config.json
# 编辑 config.json 填入 session_key
```

### JSON 文件下载失败

手动导入的运动（非手表自动记录）无法通过 API 导出 JSON 文件（服务器返回 HTTP 500）。这是 Suunto 服务端的限制，FIT 文件仍可正常下载。

### FIT 文件验证警告

- `peak_epoc 为浮点数` / `estimated_vo2_max 为浮点数` — 服务端数据格式问题，不影响使用
- `max_speed 字段缺失` — 部分运动类型（如泳池游泳）可能不含此字段
- `结束时间异常` — 运动中可能有长时间暂停

更多问题请参考 [docs/TOKEN_ACQUISITION.md](docs/TOKEN_ACQUISITION.md) 和 [docs/API_REFERENCE.md](docs/API_REFERENCE.md)。

## 技术背景

本工具通过逆向 Suunto 中国版 Android APP 发现了其云 API 接口。关键发现过程：

1. Suunto APP 使用 SSL Certificate Pinning，无法通过常规中间人抓包
2. 通过反编译 APK（使用 jadx）找到了 API 端点和认证方式
3. 认证使用自定义 HTTP 头 `STTAuthorization`，token 存储在 APP 本地 SQLite 数据库中
4. 主要涉及的代码类：`AuthProviderImpl`（认证）、`DownloadWorkoutAsFile`（文件下载 URL 构造）、`WorkoutRestApi`（REST 接口定义）

详细 API 文档见 [docs/API_REFERENCE.md](docs/API_REFERENCE.md)。

## 许可证

[MIT License](LICENSE)


## 全天候健康数据下载 (Health Data)

除运动记录外，本工具现已支持下载全天候健康数据（心率、步数、卡路里、身体电量、压力、睡眠总览与分期、夜间高频 HRV）：

### 1. 同步健康数据
```bash
# 全量同步所有大类（首次使用）
python3 suunto_health_sync.py --full

# 增量同步（日常使用，仅拉取新记录）
python3 suunto_health_sync.py

# 仅同步指定大类
python3 suunto_health_sync.py --category sleep
python3 suunto_health_sync.py --category activity
```
数据保存在 `data/health/{类别}/{YYYY-MM}.ndjson`，与 Suunto 国际区官方 GDPR 导出格式完全一致。

### 2. 一键转换为 CSV 表格
```bash
python3 convert_ndjson.py -i data/health -o data/health_csv
```
工具会自动进行物理量换算（心率 Hz 转 bpm，能量焦耳转千卡，睡眠秒数转小时），生成的 CSV 位于 `data/health_csv/`。
