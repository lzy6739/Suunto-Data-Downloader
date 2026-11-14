#!/usr/bin/env python3
"""
Suunto 大陆区全天候健康数据流式导出工具 (Asko Timeline API)
支持导出：
  1. activity       - 日常心率 (Hz -> bpm)、步数、活动能量消耗 (10分钟采样)
  2. recovery       - 身体电量 (Resources balance 0~100%)、压力状态 (Stress state)
  3. sleep          - 每日睡眠汇总 (时长、深睡、平均/最低心率、HRV均值、睡眠质量)
  4. sleepstages    - 睡眠分期时间轴 (LIGHT, DEEP, REM, AWAKE 及持续时长)
  5. sleephrvsamples- 睡眠期间夜间高频 HRV 采样点 (毫秒级)

认证方式：
  HTTP Header: STTAuthorization: <sessionKey>
  与运动数据同步项目 (Suunto Data Downloader) 共享相同的 sessionKey。
"""

import os
import sys
import json
import time
import argparse
import urllib.request
import urllib.error
from datetime import datetime

# 接口基址与端点定义
BASE_URL_CHINA = "https://247.suunto-operations.cn"
BASE_URL_GLOBAL = "https://247.sports-tracker.com"

ENDPOINTS = {
    "activity": "v1/activity/export",
    "recovery": "v1/recovery/export",
    "sleep": "v1/sleep/export",
    "sleepstages": "v1/sleepstages/export",
    "sleephrvsamples": "v1/sleephrvsamples/export"
}

STATE_FILE = "health_sync_state.json"


def load_config(config_path="config.json"):
    """读取配置文件或返回空配置"""
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[!] 读取配置文件 {config_path} 失败: {e}", file=sys.stderr)
    return {}


def load_sync_state(data_dir):
    """读取上一次各数据类型的同步时间戳（毫秒）"""
    state_path = os.path.join(data_dir, STATE_FILE)
    if os.path.exists(state_path):
        try:
            with open(state_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_sync_state(data_dir, state):
    """持久化保存最新同步状态"""
    os.makedirs(data_dir, exist_ok=True)
    state_path = os.path.join(data_dir, STATE_FILE)
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def fetch_stream(base_url, endpoint, session_key, since=0, timeout=120):
    """
    发起流式导出请求，返回生成器按行读取并解析 NDJSON
    """
    url = f"{base_url.rstrip('/')}/{endpoint.lstrip('/')}"
    if since and since > 0:
        url += f"?since={int(since)}"

    headers = {
        "STTAuthorization": session_key,
        "User-Agent": "Suunto/6.15.5 (Android; zh-CN)",
        "Accept": "application/x-ndjson, text/plain, */*"
    }

    req = urllib.request.Request(url, headers=headers, method="GET")
    
    try:
        response = urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        if e.code == 401 or e.code == 403:
            raise RuntimeError(f"认证失败 (HTTP {e.code})：请检查 sessionKey 是否已过期或填写错误")
        raise RuntimeError(f"HTTP 请求异常: {e.code} - {e.reason}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"网络连接失败: {e.reason}")

    # 流式迭代行
    for line in response:
        line_str = line.decode("utf-8", errors="ignore").strip()
        if not line_str:
            continue
        try:
            item = json.loads(line_str)
            yield item
        except json.JSONDecodeError:
            continue


def parse_timestamp_ms(ts_str):
    """
    尝试将 ISO-8601 字符串解析为毫秒时间戳
    例: '2024-09-13T19:40:00.010+08:00'
    """
    if not ts_str:
        return 0
    try:
        # Python 3.11+ 支持 fromisoformat 直接处理 +08:00
        dt = datetime.fromisoformat(ts_str)
        return int(dt.timestamp() * 1000)
    except Exception:
        return 0


def sync_category(category, base_url, session_key, output_dir, state, full_sync=False):
    """
    同步单个数据大类并按月落盘为 NDJSON
    """
    endpoint = ENDPOINTS[category]
    since = 0 if full_sync else state.get(category, 0)
    
    print(f"\n[*] 正在同步 [{category}] (起点: since={since})...")
    
    cat_dir = os.path.join(output_dir, category)
    os.makedirs(cat_dir, exist_ok=True)
    
    # 缓存已打开的文件句柄，按月保存 (YYYY-MM.ndjson)
    file_handles = {}
    record_count = 0
    max_ts = since

    try:
        for item in fetch_stream(base_url, endpoint, session_key, since=since):
            ts_str = item.get("timestamp")
            if not ts_str:
                continue

            ts_ms = parse_timestamp_ms(ts_str)
            if ts_ms > max_ts:
                max_ts = ts_ms

            # 提取年月分组
            month_key = ts_str[:7] if len(ts_str) >= 7 else "unknown"
            filename = f"{month_key}.ndjson"
            
            if filename not in file_handles:
                filepath = os.path.join(cat_dir, filename)
                file_handles[filename] = open(filepath, "a", encoding="utf-8")
            
            file_handles[filename].write(json.dumps(item, ensure_ascii=False) + "\n")
            record_count += 1
            
            if record_count % 500 == 0:
                print(f"    已流式接收 {record_count} 条记录...", end="\r", flush=True)

    finally:
        for fh in file_handles.values():
            fh.close()

    print(f"    [+] 同步完成：本次接收 {record_count} 条记录，最新时间戳: {max_ts}")
    if max_ts > since:
        state[category] = max_ts


def main():
    parser = argparse.ArgumentParser(description="Suunto 大陆区全天候健康数据导出工具")
    parser.add_argument("--config", "-c", default="config.json", help="配置文件路径 (默认: config.json)")
    parser.add_argument("--token", "-t", default="", help="直接指定 sessionKey (覆盖配置文件)")
    parser.add_argument("--output", "-o", default="data/health", help="输出目录 (默认: data/health)")
    parser.add_argument("--category", choices=list(ENDPOINTS.keys()) + ["all"], default="all", help="导出指定分类 (默认: all)")
    parser.add_argument("--full", action="store_true", help="强制从头全量同步 (忽略上次保存的 since 状态)")
    parser.add_argument("--global-server", action="store_true", help="切换为国际区服务器 (默认使用大陆区 247.suunto-operations.cn)")
    args = parser.parse_args()

    cfg = load_config(args.config)
    session_key = args.token or cfg.get("session_key") or cfg.get("sessionKey") or cfg.get("token")

    if not session_key:
        print("[!] 错误: 未提供有效的 sessionKey！", file=sys.stderr)
        print("    请在 config.json 中配置 {\"session_key\": \"...\"} 或通过 --token 参数传入。", file=sys.stderr)
        print("    (sessionKey 可从手机 /data/data/com.stt.android.suunto.china/databases/amer_app.db 的 user 表中读取)", file=sys.stderr)
        sys.exit(1)

    cfg_base_url = cfg.get("health_base_url") or BASE_URL_CHINA
    base_url = BASE_URL_GLOBAL if args.global_server else cfg_base_url
    
    default_out = cfg.get("output", {}).get("health_dir", "data/health") if isinstance(cfg.get("output"), dict) else "data/health"
    out_dir = out_dir if out_dir != "data/health" else default_out
    print("=" * 60)
    print(f"Suunto Health Data Downloader (Asko Timeline API)")
    print(f"服务器: {base_url}")
    print(f"输出目录: {os.path.abspath(out_dir)}")
    print(f"同步模式: {'全量 (since=0)' if args.full else '增量同步'}")
    print("=" * 60)

    state = load_sync_state(out_dir)
    categories = list(ENDPOINTS.keys()) if args.category == "all" else [args.category]

    for cat in categories:
        try:
            sync_category(cat, base_url, session_key, out_dir, state, full_sync=args.full)
        except Exception as e:
            print(f"[x] 分类 [{cat}] 同步失败: {e}", file=sys.stderr)

    save_sync_state(out_dir, state)
    print("\n[OK] 全部同步事务处理结束。")


if __name__ == "__main__":
    main()
