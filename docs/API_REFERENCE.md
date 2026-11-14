# Suunto Cloud API 参考

本文档记录通过逆向 Suunto 中国版 Android APP 发现的云 API 接口。

## 基础信息

| 项目 | 值 |
|------|-----|
| 中国版 Base URL | `https://cloud-api.suunto.cn/apiserver/v1` |
| 国际版 Base URL | `https://cloud-api.suunto.com/apiserver/v1`（待验证） |
| 认证方式 | HTTP 自定义头 `STTAuthorization: <sessionKey>` |
| 数据格式 | JSON（API 响应）、FIT / JSON（文件导出） |

## 认证

所有 API 请求需要在 HTTP 头中携带 session key：

```
STTAuthorization: <your_session_key>
```

这不是标准的 `Bearer` token，而是 Suunto 自定义的认证方案。Session key 存储在手机 APP 的本地 SQLite 数据库 `amer_app.db` 中。

认证失败时服务器返回 HTTP 401 或 403。

## API 端点

### 获取运动列表

```
GET /workouts/?limit={limit}&offset={offset}
```

**参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| `limit` | int | 每页数量，最大 200 |
| `offset` | int | 偏移量，从 0 开始 |

**响应示例：**

```json
{
  "payload": [
    {
      "key": "b20hs01c5v1e2rgp",
      "startTime": 1697443320000,
      "totalDistance": 5230,
      "totalDuration": 1560000,
      "activityId": 1,
      "name": "Running"
    }
  ]
}
```

**字段说明：**

| 字段 | 说明 |
|------|------|
| `key` | 运动唯一标识（workoutKey），用于后续下载 |
| `startTime` | 开始时间（Unix 毫秒时间戳） |
| `totalDistance` | 总距离（米），无距离的运动可能为 null |
| `totalDuration` | 总时长（毫秒） |
| `activityId` | 运动类型 ID（用于消歧 ActivityType） |

**分页逻辑：** 每次请求最多返回 200 条。当返回数量小于 `limit` 时，说明已到最后一页。

### 获取单条运动详情

```
GET /workouts/{workoutKey}
```

返回单条运动的完整摘要信息。

### 导出 FIT 文件

```
GET /workout/exportFit/{workoutKey}?autogeneraterecords=true&generatefillerlaps=true&removesinglelocation=true&removerecordsduringpauses=true&reducepoolswimminglaptypes=true
```

**响应：** FIT 文件二进制数据（`Content-Type: application/octet-stream`）

**查询参数：**

| 参数 | 说明 |
|------|------|
| `autogeneraterecords` | 自动生成缺失的记录点 |
| `generatefillerlaps` | 生成填充圈（如暂停期间的圈） |
| `removesinglelocation` | 移除单点定位记录 |
| `removerecordsduringpauses` | 移除暂停期间的记录 |
| `reducepoolswimminglaptypes` | 简化泳池游泳的圈类型 |

这些参数与 APP 导出行为一致，建议全部保留。

**FIT 文件格式：** Garmin FIT（Flexible and Interoperable Data Transfer），一种二进制格式，广泛用于运动手表和码表。可用 `fitdecode`（Python）或 Garmin FIT SDK 解析。

### 导出 JSON 文件（SML DeviceLog）

```
GET /workouts/{workoutKey}/ultimatemanager
```

**响应：** JSON 格式的 SML DeviceLog 数据

**数据结构：**

```json
{
  "DeviceLog": {
    "Header": {
      "DateTime": "2026-10-15T20:02:00.510+08:00",
      "ActivityType": 3,
      "Distance": 5230,
      "Duration": 1560000,
      "AvgHeartRate": 145,
      "MaxHeartRate": 178,
      "Calories": 420
    },
    "Samples": [
      {
        "DateTime": "2026-10-15T20:02:01.000+08:00",
        "Latitude": 30.123456,
        "Longitude": 120.654321,
        "Altitude": 15.2,
        "HeartRate": 120,
        "Speed": 3.5,
        "Cadence": 82
      }
    ],
    "Windows": [...],
    "Device": {
      "Name": "Suunto Race 3S",
      "Serial": "XXXXXXXX",
      "SwVersion": "..."
    }
  }
}
```

**字段说明：**

- **Header** — 运动摘要：时间、类型、距离、时长、心率、卡路里等
- **Samples** — 时间序列采样数据：GPS 坐标、海拔、心率、速度、步频等（可达数千条）
- **Windows** — 窗口聚合数据（按时间段的心率统计等）
- **Device** — 记录设备信息：名称、序列号、固件版本

## 已知限制

1. **手动导入的运动无法导出 JSON** — 通过 APP 手动导入（而非手表同步）的运动，调用 JSON 导出接口会返回 HTTP 500。FIT 文件不受影响，可正常导出。

2. **分页上限** — 每页最多 200 条记录。

3. **FIT 文件数据差异** — API 导出的 FIT 文件与 APP 手动导出的 FIT 文件在极少数情况下存在细微差异：
   - `peak_epoc` 和 `estimated_vo2_max` 字段可能存在 10 倍的单位差异（浮点数 vs 整数）
   - 这些差异不影响实际使用，数据本质相同

## 逆向来源

以下信息通过反编译 Suunto 中国版 Android APK 获得：

| 类名 | 功能 |
|------|------|
| `AuthProviderImpl` | 认证逻辑，发现 `STTAuthorization` 自定义头 |
| `DownloadWorkoutAsFile` | FIT/JSON 文件下载 URL 的构造方式 |
| `WorkoutRestApi` | Retrofit REST API 接口定义 |

**反编译工具：** [jadx](https://github.com/skylot/jadx)（Dalvik bytecode 转 Java 源码）

**APK 包名：** `com.stt.android.suunto.china`

**数据库位置：** `/data/data/com.stt.android.suunto.china/databases/amer_app.db`

## 全天候健康数据 API (Asko Timeline)

Suunto 中国版 APP 采用代号为 **Asko Timeline** 的专用云端服务同步日常健康数据。

| 项目 | 值 |
|------|-----|
| 中国版 Base URL | `https://247.suunto-operations.cn` |
| 国际版 Base URL | `https://247.sports-tracker.com` |
| 认证方式 | HTTP 自定义头 `STTAuthorization: <sessionKey>`（与运动 API 一致） |
| 数据传输格式 | `application/x-ndjson`（换行符分隔的 JSON，流式传输） |

### 流式导出端点 (Streaming Export)

所有端点均支持查询参数 `?since={timestamp_ms}`。当 `since=0` 或省略时，服务端将从第一条记录开始下发全量历史数据。

#### 1. 日常活动与心率 (Activity)

```
GET /v1/activity/export?since={timestamp}
```

- **采样周期**：每 10 分钟一条记录。
- **单条格式**：
  ```json
  {"timestamp":"2024-09-13T19:40:00.010+08:00","entryData":{"hr":1.1833333,"stepCount":0,"energyConsumption":0.0}}
  ```
- **字段定义**：
  - `hr`：心率，**单位为 Hz**（赫兹）。转换为标准心率（bpm）公式：`bpm = round(hr * 60, 1)`（例如 `1.1833333` ≈ 71 bpm）。
  - `stepCount`：该 10 分钟区间内的累计步数。
  - `energyConsumption`：活动能量消耗，单位为**焦耳（J）**。换算千卡公式：`kcal = round(energyConsumption / 4184.0, 2)`。

#### 2. 身体资源与压力 (Recovery / Balance)

```
GET /v1/recovery/export?since={timestamp}
```

- **单条格式**：
  ```json
  {"timestamp":"2024-09-13T19:30:00.000+08:00","entryData":{"balance":0.69,"stressState":2}}
  ```
- **字段定义**：
  - `balance`：身体电量 / 资源（0.0 ~ 1.0 浮点数，`0.69` 表示 69%）。
  - `stressState`：压力状态枚举（1=恢复中, 2=低压力, 3=高压力等）。

#### 3. 每日睡眠概览 (Sleep)

```
GET /v1/sleep/export?since={timestamp}
```

- **单条格式**：
  ```json
  {"timestamp":"2024-09-13T22:49:10.210+08:00","entryData":{"deepSleepDuration":4091.0,"duration":26649.0,"hrAvg":0.8,"hrMin":0.73333335,"quality":0.96,"avgHrv":51.0,"avgHrvSampleCount":84}}
  ```
- **字段定义**：
  - `duration`：睡眠总时长（秒）。
  - `deepSleepDuration`：深睡时长（秒）。
  - `quality`：睡眠质量得分（0.0 ~ 1.0）。
  - `hrAvg` / `hrMin`：睡眠平均与最低心率（Hz，乘以 60 即为 bpm）。
  - `avgHrv`：整夜平均 HRV（毫秒）。
  - `avgHrvSampleCount`：HRV 采样样本数。

#### 4. 睡眠分期明细 (Sleep Stages)

```
GET /v1/sleepstages/export?since={timestamp}
```

- **单条格式**：
  ```json
  {"timestamp":"2025-10-01T16:48:00.000+00:00","entryData":{"stage":"LIGHT","duration":1440.0}}
  ```
- **字段定义**：
  - `stage`：分期类型（`LIGHT` 浅睡、`DEEP` 深睡、`REM` 快速眼动、`AWAKE` 清醒）。
  - `duration`：本分期持续时长（秒）。

#### 5. 睡眠夜间高频 HRV (Sleep HRV Samples)

```
GET /v1/sleephrvsamples/export?since={timestamp}
```

- 提供整夜毫秒级连续 HRV 采样序列。

---

## 本地 SQLite 数据库结构 (amer_app.db)

位于 `/data/data/com.stt.android.suunto.china/databases/amer_app.db`，由 Jetpack Room 维护：

| 表名 | 对应实体 | 说明 |
|------|---------|------|
| `sleepsegments` | `LocalSleepSegment` | 睡眠总览（含 25 项详细指标：spo2、avg_hrv、bedtime等） |
| `sleep_stage_intervals` | `LocalSleepStageInterval` | 睡眠分期时间片 |
| `sleep_hrv_samples` | `LocalSleepHrvSample` | 睡眠 HRV 采样 |
| `recoverydata` | `LocalRecoveryData` | 身体电量与压力状态 |
| `user` | `User` | 包含 `session` 字段（内含 `sessionKey`） |

## 逆向来源补充

| 类名 / 文件 | 功能 |
|------------|------|
| `AskoTimelineRestApi` | Retrofit 接口：定义了 `streamActivityData`、`streamRecoveryData`、`streamSleepData`、`streamSleepStagesData`、`streamSleepHrvSamplesData` |
| `AskoTimelineStreamsKt` | 流式 NDJSON 解析逻辑 |
| `BaseUrlConfiguration` | 环境配置表：包含 `PROD_CHINA` 下的 `https://247.suunto-operations.cn` 基址 |
| `SleepModule` | 注入 AskoTimelineRestApi 及 Room 数据访问对象 (DAO) |
