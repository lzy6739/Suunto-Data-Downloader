#!/usr/bin/env python3
"""
从 Suunto APP 数据库 (amer_app.db) 中提取 session key

用法:
    python3 extract_token.py amer_app.db
    python3 extract_token.py /path/to/amer_app.db

前提:
    需要从 Android 手机的 Suunto 中国版 APP 数据目录提取 amer_app.db 文件。
    详细步骤详见 docs/TOKEN_ACQUISITION.md
"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path


def extract_session_key(db_path):
    """从 amer_app.db 中提取 session key"""
    path = Path(db_path)
    if not path.exists():
        print(f"[!] 数据库文件不存在: {path}")
        sys.exit(1)

    try:
        conn = sqlite3.connect(str(path))
        cursor = conn.execute("SELECT session FROM user LIMIT 1")
        row = cursor.fetchone()
        conn.close()
    except sqlite3.OperationalError as e:
        print(f"[!] 数据库读取失败: {e}")
        print("    确认文件是有效的 SQLite 数据库")
        sys.exit(1)

    if not row or not row[0]:
        print("[!] 数据库中未找到 session 数据")
        print("    请确认已在 Suunto APP 中登录并同步过运动数据")
        sys.exit(1)

    try:
        session_data = json.loads(row[0])
    except json.JSONDecodeError as e:
        print(f"[!] session 字段解析失败: {e}")
        print("    数据格式可能已变更，请检查 APP 版本")
        sys.exit(1)

    session_key = session_data.get("sessionKey")
    if not session_key:
        print("[!] session 中未找到 sessionKey 字段")
        print(f"    可用字段: {', '.join(session_data.keys())}")
        sys.exit(1)

    return session_key


def main():
    parser = argparse.ArgumentParser(
        description="从 Suunto APP 数据库提取 session key",
        epilog="详细步骤详见 docs/TOKEN_ACQUISITION.md"
    )
    parser.add_argument("db_path", help="amer_app.db 数据库文件路径")
    args = parser.parse_args()

    session_key = extract_session_key(args.db_path)

    print(f"Session Key: {session_key}")
    print(f"\n请将此值填入 config.json 的 session_key 字段")


if __name__ == "__main__":
    main()
