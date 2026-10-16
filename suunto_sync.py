#!/usr/bin/env python3
"""
Suunto 运动数据增量同步脚本
从 Suunto 云服务器直接下载 FIT 和 JSON 文件到本地

用法:
    python3 suunto_sync.py                  # 增量同步（FIT + JSON）
    python3 suunto_sync.py --dry-run        # 仅查看缺失，不下载
    python3 suunto_sync.py --json-only      # 只同步 JSON
    python3 suunto_sync.py --fit-only       # 只同步 FIT
    python3 suunto_sync.py --list           # 列出所有运动（不下载）
    python3 suunto_sync.py --config my.json # 指定配置文件

认证:
    STTAuthorization header（sessionKey 从 APP 数据库提取）
    过期后需重新从手机提取，详见 docs/TOKEN_ACQUISITION.md
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# 尝试导入 fitdecode（用于 FIT 文件验证）
try:
    import fitdecode
    FITDECODE_AVAILABLE = True
except ImportError:
    FITDECODE_AVAILABLE = False

# 脚本所在目录（用于解析相对路径）
SCRIPT_DIR = Path(__file__).parent.resolve()
DEFAULT_CONFIG_PATH = SCRIPT_DIR / "config.json"


def load_config(config_path):
    """从 JSON 配置文件加载设置"""
    path = Path(config_path)
    if not path.exists():
        print(f"[!] 配置文件不存在: {path}")
        print(f"    请执行以下命令创建配置文件:")
        print(f"    cp config.example.json config.json")
        print(f"    然后编辑 config.json，填入你的 session_key")
        print(f"    Token 获取方法详见: docs/TOKEN_ACQUISITION.md")
        sys.exit(1)

    try:
        with open(path, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        print(f"[!] 配置文件格式错误: {e}")
        sys.exit(1)

    # 验证必填字段
    session_key = config.get("session_key", "")
    if not session_key or session_key in ("YOUR_SESSION_KEY_HERE", ""):
        print("[!] 配置文件中的 session_key 为空")
        print("    请编辑 config.json，填入你的 session_key")
        print("    Token 获取方法详见: docs/TOKEN_ACQUISITION.md")
        sys.exit(1)

    return config


def resolve_path(path_str, base_dir):
    """解析路径：相对路径以 base_dir 为基准"""
    p = Path(path_str)
    if p.is_absolute():
        return p
    return base_dir / p


def api_request(url, session_key):
    """发送 API 请求"""
    req = urllib.request.Request(url, headers={"STTAuthorization": session_key})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            print("  [!] 认证失败 (HTTP {})，session_key 可能已过期".format(e.code))
            print("      请重新从手机提取 session key，详见: docs/TOKEN_ACQUISITION.md")
            sys.exit(1)
        raise


def fetch_all_workouts(base_url, session_key, page_size):
    """获取所有运动列表（分页）"""
    workouts = []
    offset = 0
    while True:
        url = f"{base_url}/workouts/?limit={page_size}&offset={offset}"
        data = api_request(url, session_key)
        batch = data["payload"]
        workouts.extend(batch)
        print(f"  获取运动列表: {len(workouts)}", end="\r")
        if len(batch) < page_size:
            break
        offset += len(batch)
    print(f"  获取运动列表: {len(workouts)} 条                    ")
    return workouts


def scan_downloaded(fit_dir, json_dir):
    """扫描已下载的 workoutKey 命名文件（纯字母数字文件名）"""
    fit_keys = set()
    json_keys = set()

    if os.path.isdir(fit_dir):
        for f in os.listdir(fit_dir):
            if f.lower().endswith(".fit"):
                name = os.path.splitext(f)[0]
                if name.isalnum() and name.isascii():
                    fit_keys.add(name)

    if os.path.isdir(json_dir):
        for f in os.listdir(json_dir):
            if f.endswith(".json"):
                name = os.path.splitext(f)[0]
                if name.isalnum() and name.isascii():
                    json_keys.add(name)

    return fit_keys, json_keys


def download_file(url, dest_path, session_key):
    """下载文件到指定路径"""
    req = urllib.request.Request(url, headers={"STTAuthorization": session_key})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = resp.read()
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        with open(dest_path, "wb") as f:
            f.write(data)
        return len(data)
    except Exception as e:
        print(f"\n  [!] 下载失败: {e}")
        if os.path.exists(dest_path):
            os.remove(dest_path)
        return None


def validate_fit_file(fit_path):
    """
    验证 FIT 文件的数据完整性
    返回: (warnings, errors) 列表
    """
    if not FITDECODE_AVAILABLE:
        return [], []

    warnings = []
    errors = []

    try:
        with fitdecode.FitReader(fit_path) as fit:
            for frame in fit:
                if isinstance(frame, fitdecode.FitDataMessage) and frame.name == 'session':
                    field_names = [f.name for f in frame.fields]

                    # 1. 检查 peak_epoc（应该是整数，不应该是浮点数）
                    if 'peak_epoc' in field_names:
                        peak_epoc = frame.get_value('peak_epoc')
                        if peak_epoc is not None and isinstance(peak_epoc, float):
                            warnings.append(f"peak_epoc 为浮点数 ({peak_epoc})，应为整数")

                    # 2. 检查 estimated_vo2_max（应该是整数，不应该是浮点数）
                    if 'estimated_vo2_max' in field_names:
                        vo2 = frame.get_value('estimated_vo2_max')
                        if vo2 is not None and isinstance(vo2, float):
                            warnings.append(f"estimated_vo2_max 为浮点数 ({vo2})，应为整数")

                    # 3. 检查 max_speed 是否缺失
                    if 'max_speed' not in field_names:
                        warnings.append("max_speed 字段缺失")

                    # 4. 检查结束时间合理性
                    start_time = frame.get_value('start_time')
                    timestamp = frame.get_value('timestamp')
                    total_timer_time = frame.get_value('total_timer_time')

                    if start_time and timestamp and total_timer_time:
                        import datetime as dt_mod
                        try:
                            start_dt = datetime.fromisoformat(str(start_time))
                            end_dt = datetime.fromisoformat(str(timestamp))
                            duration_sec = float(total_timer_time)

                            expected_end = start_dt + dt_mod.timedelta(seconds=duration_sec)
                            actual_diff = abs((end_dt - expected_end).total_seconds())

                            if actual_diff > 60:
                                warnings.append(
                                    f"结束时间异常：预期 {expected_end}, "
                                    f"实际 {end_dt}, 差异 {actual_diff:.1f}秒"
                                )
                        except Exception:
                            pass

                    break  # 只检查 session 消息
    except Exception as e:
        errors.append(f"FIT 文件解析失败: {e}")

    return warnings, errors


def list_workouts(workouts, fit_keys, json_keys):
    """列出所有运动及其下载状态"""
    print(f"\n{'序号':>4}  {'日期时间':<20} {'workoutKey':<24} {'距离':>8} {'FIT':>4} {'JSON':>5}")
    print("-" * 80)
    for i, w in enumerate(workouts):
        dt = datetime.fromtimestamp(w["startTime"] / 1000, tz=timezone.utc).astimezone()
        dist = (w.get("totalDistance") or 0) / 1000
        has_fit = "+" if w["key"] in fit_keys else "-"
        has_json = "+" if w["key"] in json_keys else "-"
        print(f"{i+1:>4}  {dt.strftime('%Y-%m-%d %H:%M'):<20} {w['key']:<24} {dist:>6.1f}km  {has_fit:>3}  {has_json:>4}")
    print(f"\n共 {len(workouts)} 条")


def main():
    parser = argparse.ArgumentParser(description="Suunto 运动数据增量同步")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH),
                        help="配置文件路径（默认: config.json）")
    parser.add_argument("--dry-run", action="store_true", help="仅显示缺失，不下载")
    parser.add_argument("--json-only", action="store_true", help="只同步 JSON")
    parser.add_argument("--fit-only", action="store_true", help="只同步 FIT")
    parser.add_argument("--list", action="store_true", help="列出所有运动")
    args = parser.parse_args()

    # 加载配置
    config = load_config(args.config)
    session_key = config["session_key"]
    base_url = config.get("api_base_url", "https://cloud-api.suunto.cn/apiserver/v1").rstrip("/")
    sync_config = config.get("sync", {})
    page_size = sync_config.get("page_size", 200)
    download_delay = sync_config.get("download_delay", 0.3)
    validate_fit = sync_config.get("validate_fit", True)

    # 解析输出路径
    output_config = config.get("output", {})
    fit_dir = resolve_path(output_config.get("fit_dir", "./data/fit"), SCRIPT_DIR)
    json_dir = resolve_path(output_config.get("json_dir", "./data/json"), SCRIPT_DIR)

    sync_fit = not args.json_only
    sync_json = not args.fit_only

    # Step 1: 获取运动列表
    print("[1/3] 获取运动列表...")
    workouts = fetch_all_workouts(base_url, session_key, page_size)

    # Step 2: 扫描已下载文件
    print("[2/3] 扫描已下载文件...")
    fit_keys, json_keys = scan_downloaded(str(fit_dir), str(json_dir))

    total = len(workouts)
    need_fit = [w for w in workouts if sync_fit and w["key"] not in fit_keys]
    need_json = [w for w in workouts if sync_json and w["key"] not in json_keys]

    print(f"\n  服务器总计: {total} 条")
    if sync_fit:
        print(f"  FIT  已有: {len(fit_keys)}, 缺失: {len(need_fit)}")
    if sync_json:
        print(f"  JSON 已有: {len(json_keys)}, 缺失: {len(need_json)}")

    if args.list:
        list_workouts(workouts, fit_keys, json_keys)
        return

    if not need_fit and not need_json:
        print("\n  所有文件已同步，无需下载。")
        return

    if args.dry_run:
        print("\n--dry-run 模式，不执行下载--")
        if need_fit:
            print(f"\n  缺失 FIT（前 10 个）:")
            for w in need_fit[:10]:
                dt = datetime.fromtimestamp(w["startTime"] / 1000, tz=timezone.utc).astimezone()
                print(f"    {w['key']}  {dt.strftime('%Y-%m-%d %H:%M')}")
            if len(need_fit) > 10:
                print(f"    ... 还有 {len(need_fit) - 10} 个")
        if need_json:
            print(f"\n  缺失 JSON（前 10 个）:")
            for w in need_json[:10]:
                dt = datetime.fromtimestamp(w["startTime"] / 1000, tz=timezone.utc).astimezone()
                print(f"    {w['key']}  {dt.strftime('%Y-%m-%d %H:%M')}")
            if len(need_json) > 10:
                print(f"    ... 还有 {len(need_json) - 10} 个")
        return

    # Step 3: 下载
    print(f"\n[3/3] 开始下载...")
    need_fit_set = {w["key"] for w in need_fit}
    need_json_set = {w["key"] for w in need_json}

    downloaded_fit = 0
    downloaded_json = 0
    failed_keys = []

    for i, w in enumerate(workouts):
        wkey = w["key"]
        need_this_fit = sync_fit and wkey in need_fit_set
        need_this_json = sync_json and wkey in need_json_set

        if not need_this_fit and not need_this_json:
            continue

        dt = datetime.fromtimestamp(w["startTime"] / 1000, tz=timezone.utc).astimezone()
        dt_str = dt.strftime("%Y-%m-%d %H:%M")
        progress = f"[{i+1}/{total}]"
        fit_ok = not need_this_fit
        json_ok = not need_this_json

        if need_this_fit:
            fit_path = os.path.join(str(fit_dir), f"{wkey}.fit")
            url = (
                f"{base_url}/workout/exportFit/{wkey}"
                f"?autogeneraterecords=true&generatefillerlaps=true"
                f"&removesinglelocation=true&removerecordsduringpauses=true"
                f"&reducepoolswimminglaptypes=true"
            )
            size = download_file(url, fit_path, session_key)
            if size is not None:
                downloaded_fit += 1
                fit_ok = True
                print(f"  {progress} FIT  {dt_str} {wkey} ({size//1024}KB)")

                # 验证 FIT 文件
                if validate_fit:
                    warnings, errors = validate_fit_file(fit_path)
                    if warnings:
                        print(f"       ⚠️  警告: {'; '.join(warnings)}")
                    if errors:
                        print(f"       ❌ 错误: {'; '.join(errors)}")
            else:
                fit_ok = False
            time.sleep(download_delay)

        if need_this_json:
            json_path = os.path.join(str(json_dir), f"{wkey}.json")
            url = f"{base_url}/workouts/{wkey}/ultimatemanager"
            size = download_file(url, json_path, session_key)
            if size is not None:
                downloaded_json += 1
                json_ok = True
                if not need_this_fit:
                    print(f"  {progress} JSON {dt_str} {wkey} ({size//1024}KB)")
            else:
                json_ok = False
            time.sleep(download_delay)

        if not fit_ok or not json_ok:
            if wkey not in failed_keys:
                failed_keys.append(wkey)

    print(f"\n===== 同步完成 =====")
    if sync_fit:
        print(f"  FIT  下载: {downloaded_fit} 个")
    if sync_json:
        print(f"  JSON 下载: {downloaded_json} 个")
    if failed_keys:
        print(f"  失败: {len(failed_keys)} 个（可能是手动导入的运动，服务器无法生成导出文件）")
        for k in failed_keys[:5]:
            print(f"    {k}")
        if len(failed_keys) > 5:
            print(f"    ... 还有 {len(failed_keys) - 5} 个")


if __name__ == "__main__":
    main()
