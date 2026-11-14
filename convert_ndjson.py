#!/usr/bin/env python3
"""
将 Suunto 健康数据 NDJSON 文件批量转为标准 CSV / JSON，便于在表格或分析软件中使用。
自动处理单位转换：
  - 心率：Hz -> bpm (乘以 60)
  - 能量：焦耳 (J) -> 千卡 (kcal, 除以 4184)
  - 时长：秒 (s) -> 分钟 / 小时
  - 身体资源：0.0~1.0 -> 0~100%
"""

import os
import sys
import glob
import json
import csv
import argparse

def convert_activity(files, out_csv):
    rows = []
    for f in sorted(files):
        with open(f, "r", encoding="utf-8") as fp:
            for line in fp:
                line = line.strip()
                if not line: continue
                try:
                    data = json.loads(line)
                    ts = data.get("timestamp")
                    entry = data.get("entryData", {})
                    hr_hz = entry.get("hr", 0)
                    hr_bpm = round(hr_hz * 60, 1) if hr_hz else None
                    steps = entry.get("stepCount", 0)
                    energy_j = entry.get("energyConsumption", 0.0)
                    energy_kcal = round(energy_j / 4184.0, 2)
                    rows.append({
                        "timestamp": ts,
                        "heart_rate_bpm": hr_bpm,
                        "steps": steps,
                        "energy_kcal": energy_kcal,
                        "energy_joules": energy_j
                    })
                except Exception:
                    continue
    if rows:
        with open(out_csv, "w", newline="", encoding="utf-8-sig") as fp:
            writer = csv.DictWriter(fp, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        print(f"[+] 转换完成: {out_csv} ({len(rows)} 行记录)")


def convert_recovery(files, out_csv):
    rows = []
    for f in sorted(files):
        with open(f, "r", encoding="utf-8") as fp:
            for line in fp:
                line = line.strip()
                if not line: continue
                try:
                    data = json.loads(line)
                    ts = data.get("timestamp")
                    entry = data.get("entryData", {})
                    balance = entry.get("balance", 0.0)
                    stress = entry.get("stressState")
                    rows.append({
                        "timestamp": ts,
                        "body_resources_pct": round(balance * 100, 1) if balance is not None else None,
                        "stress_state": stress
                    })
                except Exception:
                    continue
    if rows:
        with open(out_csv, "w", newline="", encoding="utf-8-sig") as fp:
            writer = csv.DictWriter(fp, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        print(f"[+] 转换完成: {out_csv} ({len(rows)} 行记录)")


def convert_sleep(files, out_csv):
    rows = []
    for f in sorted(files):
        with open(f, "r", encoding="utf-8") as fp:
            for line in fp:
                line = line.strip()
                if not line: continue
                try:
                    data = json.loads(line)
                    ts = data.get("timestamp")
                    entry = data.get("entryData", {})
                    dur_s = entry.get("duration", 0)
                    deep_s = entry.get("deepSleepDuration", 0)
                    hr_avg_hz = entry.get("hrAvg")
                    hr_min_hz = entry.get("hrMin")
                    rows.append({
                        "timestamp": ts,
                        "duration_hours": round(dur_s / 3600.0, 2) if dur_s else 0,
                        "deep_sleep_hours": round(deep_s / 3600.0, 2) if deep_s else 0,
                        "quality_score": round(entry.get("quality", 0) * 100, 1) if entry.get("quality") is not None else None,
                        "hr_avg_bpm": round(hr_avg_hz * 60, 1) if hr_avg_hz else None,
                        "hr_min_bpm": round(hr_min_hz * 60, 1) if hr_min_hz else None,
                        "avg_hrv_ms": entry.get("avgHrv"),
                        "hrv_sample_count": entry.get("avgHrvSampleCount")
                    })
                except Exception:
                    continue
    if rows:
        with open(out_csv, "w", newline="", encoding="utf-8-sig") as fp:
            writer = csv.DictWriter(fp, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        print(f"[+] 转换完成: {out_csv} ({len(rows)} 行记录)")


def main():
    parser = argparse.ArgumentParser(description="Suunto NDJSON 转 CSV 工具")
    parser.add_argument("--input", "-i", default="data/health", help="输入健康数据目录 (默认: data/health)")
    parser.add_argument("--output", "-o", default="data/health_csv", help="输出 CSV 目录 (默认: data/health_csv)")
    args = parser.parse_args()

    os.makedirs(args.output, exist_ok=True)
    
    # 转换各分类
    act_files = glob.glob(os.path.join(args.input, "activity", "*.ndjson"))
    if act_files:
        convert_activity(act_files, os.path.join(args.output, "daily_activity_heartrate_steps.csv"))

    rec_files = glob.glob(os.path.join(args.input, "recovery", "*.ndjson"))
    if rec_files:
        convert_recovery(rec_files, os.path.join(args.output, "body_resources_recovery.csv"))

    slp_files = glob.glob(os.path.join(args.input, "sleep", "*.ndjson"))
    if slp_files:
        convert_sleep(slp_files, os.path.join(args.output, "sleep_summary.csv"))

    print(f"\n[OK] 处理完成，CSV 已输出至: {os.path.abspath(args.output)}")


if __name__ == "__main__":
    main()
