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
