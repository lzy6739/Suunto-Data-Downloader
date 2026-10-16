# 获取 Session Token 指南

本工具使用 Suunto 云 API 下载运动数据，需要一个有效的 session key 进行认证。Session key 存储在手机端 Suunto APP 的本地 SQLite 数据库中。

## 前置条件

- **Android 手机**，已安装 Suunto 中国版 APP 并登录
- **USB 调试**已开启（设置 → 开发者选项 → USB 调试）
- **ADB 工具**已安装（`adb` 命令可用）
- **手机已 root**（需要 root 权限访问 APP 私有数据目录）

> Suunto 中国版 APP 包名：`com.stt.android.suunto.china`

## 方法一：ADB + Root 直接提取（推荐）

### 步骤 1：连接手机

用 USB 连接手机，确认 ADB 可以识别：

```bash
adb devices
# 应显示你的设备，如：
# ABCDEF123456    device
```

如果提示 "unauthorized"，请在手机上确认 USB 调试授权。

### 步骤 2：复制数据库文件

```bash
# 进入 ADB shell 并获取 root 权限
adb shell
su

# 复制数据库到可访问的位置
cp /data/data/com.stt.android.suunto.china/databases/amer_app.db /sdcard/amer_app.db

# 退出 su 和 adb shell
exit
exit

# 拉取到电脑
adb pull /sdcard/amer_app.db .

# 清理手机上的临时文件
adb shell rm /sdcard/amer_app.db
```

### 步骤 3：提取 Session Key

使用本项目提供的辅助脚本：

```bash
python3 scripts/extract_token.py amer_app.db
```

输出示例：

```
Session Key: abc123def456...
请将此值填入 config.json 的 session_key 字段
```

或者手动用 sqlite3 命令：

```bash
sqlite3 amer_app.db "SELECT session FROM user LIMIT 1;"
```

这会输出一段 JSON，其中的 `sessionKey` 字段就是你需要的值：

```json
{"sessionKey":"abc123def456...","watchKey":"...","facebookConnected":false}
```

## 方法二：通过 ADB 备份提取（无需 root）

> 此方法依赖于 Android 备份功能是否对目标 APP 生效，不保证成功。

```bash
# 创建包含 APP 数据的备份
adb backup -f suunto_backup.ab com.stt.android.suunto.china

# 在手机上确认备份操作（不要设置密码）

# 解包 .ab 文件（需要额外工具）
# Linux/macOS:
dd if=suunto_backup.ab bs=24 skip=1 | python3 -c "import zlib,sys; sys.stdout.buffer.write(zlib.decompress(sys.stdin.buffer.read()))" > suunto_backup.tar

# 从 tar 中提取数据库
tar xf suunto_backup.tar apps/com.stt.android.suunto.china/db/amer_app.db

# 提取 session key
python3 scripts/extract_token.py apps/com.stt.android.suunto.china/db/amer_app.db
```

## 方法三：使用第三方备份工具

如果上述方法不可用，可以使用 Android 备份工具（如 Helium、Titanium Backup 等）备份 APP 数据，然后从备份中提取 `amer_app.db`。

## 将 Token 填入配置

提取到 session key 后，编辑 `config.json`：

```json
{
  "session_key": "你提取到的session_key值",
  ...
}
```

然后测试连接：

```bash
python3 suunto_sync.py --list
```

如果成功列出运动列表，说明 token 有效。

## Token 有效期

- Session key 有效期较长，通常可使用数周至数月
- APP 重新登录后 token 会失效
- 服务端可能不定期使 token 失效

**过期症状：** 运行同步时出现 `认证失败 (HTTP 401/403)` 错误。

**解决：** 重新从手机提取 `amer_app.db`，获取新的 session key，更新 `config.json`。

## 安全提示

- `amer_app.db` 数据库包含你的账号信息（用户 ID、头像、session key 等），提取后请及时删除
- **不要** 将 `config.json`（含 session key）提交到 Git 仓库
- **不要** 将 `amer_app.db` 分享给他人
- Session key 等同于你的账号密码，持有者可以访问你的所有运动数据
- 本项目的 `.gitignore` 已配置排除 `config.json` 和 `*.db` 文件

## 常见问题

### 找不到 amer_app.db

确认 APP 包名是否正确：

```bash
adb shell pm list packages | grep suunto
# 中国版应显示：package:com.stt.android.suunto.china
```

如果包名不同，调整路径中的包名部分。

### session 字段为空或不存在

- 确认已在 APP 中成功登录
- 尝试在 APP 中手动同步一次运动数据
- 如果刚安装 APP，需要先登录并等待数据同步

### sqlite3 命令不可用

- Linux: `sudo apt install sqlite3` 或 `sudo pacman -S sqlite`
- macOS: `brew install sqlite`
- Windows: 使用 Python 脚本（`scripts/extract_token.py`）代替，无需额外安装

### 国际版 APP

如果你使用的是 Suunto 国际版（非中国版），数据库路径可能不同：

```bash
# 国际版包名可能是：
com.stt.android.suunto
# 或
com.suunto.suuntoapp
```

请根据实际情况调整路径。API 端点也可能不同，详见 [API_REFERENCE.md](API_REFERENCE.md)。
