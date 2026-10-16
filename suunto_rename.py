#!/usr/bin/env python3
"""
将同步目录中的 workoutKey 命名文件重命名为 {Sport}_{DateTime} 格式
匹配 Suunto APP 的命名习惯：
  FIT:  {Sport}_{YYYY-MM-DD}T{HH_mm_ss}.fit
  JSON: {Sport}_{YYYY-MM-DD}T{HH_mm_ss}.json → 按年份归入子目录

ActivityType → 默认运动名（覆盖 99.87% 的情况）
对于歧义 ActivityType (4/12/96)，用 API 列表的 activityId 消歧

用法:
    python3 suunto_rename.py                  # 执行重命名
    python3 suunto_rename.py --dry-run        # 预览重命名结果，不执行
    python3 suunto_rename.py --config my.json # 指定配置文件
"""

import argparse
import json
import os
import sys
import urllib.request
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# 脚本所在目录
SCRIPT_DIR = Path(__file__).parent.resolve()
DEFAULT_CONFIG_PATH = SCRIPT_DIR / "config.json"

# ActivityType → 默认运动名
ACTIVITY_TYPE_DEFAULT = {
    2: "Multisport", 3: "Running", 4: "Cycling", 5: "MountainBiking",
    6: "Swimming", 12: "Walking", 17: "IndoorCycling", 18: "CircuitTraining",
    23: "Gym", 25: "Soccer", 27: "Volleyball", 35: "TableTennis",
    43: "TrackRunning", 75: "Orienteering", 82: "TrailRunning",
    93: "Treadmill", 96: "Hiking", 100: "Chores", 105: "E-Biking",
}

# 歧义消解：(ActivityType, activityId) → 运动名
DISAMBIGUATION = {
    # ActivityType=4: 默认 Cycling，但 activityId=0 时为 Walking
    (4, 0): "Walking",
    # ActivityType=12: 默认 Walking，但 activityId=1 时为 Running，11 时为 Hiking
    (12, 1): "Running",
    (12, 11): "Hiking",
    # ActivityType=96: 默认 Hiking，但 activityId=0 时为 Walking
    (96, 0): "Walking",
}

# 需要消歧的 ActivityType
AMBIGUOUS_TYPES = {4, 12, 96}


def load_config(config_path):
    """从 JSON 配置文件加载设置"""
    path = Path(config_path)
    if not path.exists():
        print(f"[!] 配置文件不存在: {path}")
        print(f"    请执行以下命令创建配置文件:")
        print(f"    cp config.example.json config.json")
        print(f"    然后编辑 config.json，填入你的 session_key")
        sys.exit(1)

    try:
        with open(path, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        print(f"[!] 配置文件格式错误: {e}")
        sys.exit(1)

    session_key = config.get("session_key", "")
    if not session_key:
        print("[!] 配置文件中的 session_key 为空")
        print("    请编辑 config.json，填入你的 session_key")
        sys.exit(1)

    return config


def resolve_path(path_str, base_dir):
    """解析路径：相对路径以 base_dir 为基准"""
    p = Path(path_str)
    if p.is_absolute():
        return p
    return base_dir / p


def fetch_workout_activity_ids(base_url, session_key):
    """从 API 获取所有 workout 的 activityId（用于消歧）"""
    workouts = []
    offset = 0
    page_size = 200
    while True:
        url = f"{base_url}/workouts/?limit={page_size}&offset={offset}"
        req = urllib.request.Request(url, headers={"STTAuthorization": session_key})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                print("  [!] 认证失败，session_key 可能已过期")
                print("      详见: docs/TOKEN_ACQUISITION.md")
                sys.exit(1)
            raise
        batch = data["payload"]
        workouts.extend(batch)
        if len(batch) < page_size:
            break
        offset += len(batch)
    return {w["key"]: w["activityId"] for w in workouts}


def get_sport_name(activity_type, activity_id):
    """根据 ActivityType + activityId 确定运动名称"""
    if activity_type in AMBIGUOUS_TYPES:
        key = (activity_type, activity_id)
        if key in DISAMBIGUATION:
            return DISAMBIGUATION[key]
    return ACTIVITY_TYPE_DEFAULT.get(activity_type, f"Unknown{activity_type}")


def datetime_to_filename_parts(dt_str):
    """将 ISO DateTime 转为 (year, filename_body)

    输入: 2026-10-15T20:02:00.510+08:00
    输出: ("2026", "2026-10-15T20_02_00")
    """
    dt = datetime.fromisoformat(dt_str)
    year = str(dt.year)
    body = dt.strftime("%Y-%m-%dT%H_%M_%S")
    return year, body


def main():
    parser = argparse.ArgumentParser(description="Suunto 运动数据批量重命名")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH),
                        help="配置文件路径（默认: config.json）")
    parser.add_argument("--dry-run", action="store_true",
                        help="预览重命名结果，不实际执行")
    args = parser.parse_args()

    # 加载配置
    config = load_config(args.config)
    session_key = config["session_key"]
    base_url = config.get("api_base_url", "https://cloud-api.suunto.cn/apiserver/v1").rstrip("/")

    # 解析输出路径
    output_config = config.get("output", {})
    fit_dir = resolve_path(output_config.get("fit_dir", "./data/fit"), SCRIPT_DIR)
    json_dir = resolve_path(output_config.get("json_dir", "./data/json"), SCRIPT_DIR)
    # 重命名后的根目录（JSON 按年份归入子目录，FIT 留在原目录）
    data_dir = fit_dir.parent

    print("[1/3] 获取 API activityId（用于消歧）...")
    activity_ids = fetch_workout_activity_ids(base_url, session_key)
    print(f"  获取到 {len(activity_ids)} 条运动的 activityId")

    print("[2/3] 扫描 JSON 文件，构建重命名映射...")
    rename_plan = []  # (workoutKey, sport, year, new_name, json_src, fit_src)
    used_names = defaultdict(int)  # 检测重名
    errors = []

    json_src = str(json_dir)
    fit_src = str(fit_dir)

    if not os.path.isdir(json_src):
        print(f"[!] JSON 目录不存在: {json_src}")
        print("    请先运行 suunto_sync.py 同步数据")
        sys.exit(1)

    for f in sorted(os.listdir(json_src)):
        if not f.endswith(".json"):
            continue
        workout_key = os.path.splitext(f)[0]
        # 跳过已重命名的文件（含下划线或不在 workoutKey 格式中）
        if not (workout_key.isalnum() and workout_key.isascii()):
            continue
        json_path = os.path.join(json_src, f)
        fit_path = os.path.join(fit_src, f"{workout_key}.fit")

        try:
            with open(json_path) as fh:
                data = json.load(fh)
            header = data["DeviceLog"]["Header"]
            dt_str = header["DateTime"]
            activity_type = header.get("ActivityType", 0)

            activity_id = activity_ids.get(workout_key, -1)
            sport = get_sport_name(activity_type, activity_id)
            year, body = datetime_to_filename_parts(dt_str)

            new_name = f"{sport}_{body}"
            # 检查重名（同秒内多条运动）
            name_key = (sport, body)
            used_names[name_key] += 1
            if used_names[name_key] > 1:
                new_name = f"{sport}_{body}_{used_names[name_key]}"

            rename_plan.append((workout_key, sport, year, new_name, json_path, fit_path))
        except Exception as e:
            errors.append((workout_key, str(e)))

    print(f"  构建重命名计划: {len(rename_plan)} 条")
    if errors:
        print(f"  解析失败: {len(errors)} 条")
        for wk, err in errors[:5]:
            print(f"    {wk}: {err}")

    if not rename_plan:
        print("\n  没有需要重命名的文件。")
        return

    # 统计运动类型分布
    sport_counts = defaultdict(int)
    for _, sport, _, _, _, _ in rename_plan:
        sport_counts[sport] += 1
    print(f"\n  运动类型分布:")
    for sport, count in sorted(sport_counts.items(), key=lambda x: -x[1]):
        print(f"    {sport}: {count}")

    if args.dry_run:
        print(f"\n--dry-run 模式，不执行重命名--")
        print(f"\n  预览（前 20 个）:")
        for workout_key, sport, year, new_name, json_path, fit_path in rename_plan[:20]:
            print(f"    {workout_key} → {year}/{new_name}.json")
        if len(rename_plan) > 20:
            print(f"    ... 还有 {len(rename_plan) - 20} 个")
        return

    print(f"\n[3/3] 执行重命名...")

    # 创建年份目录
    years_needed = set(rp[2] for rp in rename_plan)
    for year in years_needed:
        os.makedirs(os.path.join(json_src, year), exist_ok=True)

    renamed_json = 0
    renamed_fit = 0

    for workout_key, sport, year, new_name, json_path, fit_path in rename_plan:
        # JSON: 移到年份子目录
        json_dest = os.path.join(json_src, year, f"{new_name}.json")
        if os.path.exists(json_path):
            os.rename(json_path, json_dest)
            renamed_json += 1

        # FIT: 留在 fit/ 目录，只改名
        fit_dest = os.path.join(fit_src, f"{new_name}.fit")
        if os.path.exists(fit_path):
            os.rename(fit_path, fit_dest)
            renamed_fit += 1

    print(f"\n===== 重命名完成 =====")
    print(f"  JSON: {renamed_json} 个（已按年份归入子目录）")
    print(f"  FIT:  {renamed_fit} 个")

    # 输出 workoutKey → 新文件名 映射
    mapping_path = os.path.join(str(data_dir), "key_to_name.json")
    mapping = {}
    for wk, sport, year, new_name, _, _ in rename_plan:
        mapping[wk] = {"sport": sport, "year": year, "name": new_name}
    with open(mapping_path, "w") as f:
        json.dump(mapping, f, indent=2, ensure_ascii=False)
    print(f"  映射表已保存: {mapping_path}")


if __name__ == "__main__":
    main()
