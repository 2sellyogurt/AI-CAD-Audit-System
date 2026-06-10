# -*- coding: utf-8 -*-
import json
import sys
import os
from collections import defaultdict

_parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent not in sys.path:
    sys.path.insert(0, _parent)

from v7.conflict_state_manager import (
    ConflictStateManager, make_key,
    STATUS_NEW, STATUS_EXISTING, STATUS_RESOLVED, STATUS_WAIVED,
)


def diff(current_path, previous_path, output_path=None, state_manager=None):
    if state_manager is None:
        state_manager = ConflictStateManager()

    with open(current_path, "r", encoding="utf-8") as f:
        cur = json.load(f)

    if not os.path.exists(previous_path):
        for c in cur:
            key = make_key(c)
            persisted = state_manager.get_entry_by_key(key)
            if persisted and persisted.get("status") in (STATUS_RESOLVED, STATUS_WAIVED):
                c["status"] = persisted["status"]
                c["reviewer"] = persisted.get("reviewer", "")
                c["review_note"] = persisted.get("note", "")
                c["reviewed_at"] = persisted.get("updated_at", "")
            else:
                c["status"] = STATUS_NEW
        out = output_path or current_path.replace(".json", "_diff.json")
        with open(out, "w", encoding="utf-8") as f:
            json.dump(cur, f, ensure_ascii=False, indent=2)
        print(f"无历史基线，{len(cur)}个冲突均标记为new（持久化状态已保留waived/resolved）")
        return cur

    with open(previous_path, "r", encoding="utf-8") as f:
        prev = json.load(f)

    prev_keys = {make_key(c) for c in prev}
    cur_keys = {make_key(c) for c in cur}

    stats = {"new": 0, "existing": 0, "resolved": 0, "waived": 0}
    for c in cur:
        key = make_key(c)
        persisted = state_manager.get_entry_by_key(key)
        if persisted and persisted.get("status") in (STATUS_RESOLVED, STATUS_WAIVED):
            c["status"] = persisted["status"]
            c["reviewer"] = persisted.get("reviewer", "")
            c["review_note"] = persisted.get("note", "")
            c["reviewed_at"] = persisted.get("updated_at", "")
            stats[persisted["status"]] += 1
        elif key not in prev_keys:
            c["status"] = STATUS_NEW
            stats["new"] += 1
        else:
            c["status"] = STATUS_EXISTING
            stats["existing"] += 1

    resolved_keys = prev_keys - cur_keys
    for key in resolved_keys:
        persisted = state_manager.get_entry_by_key(key)
        if persisted and persisted.get("status") == STATUS_WAIVED:
            stats["waived"] = stats.get("waived", 0) + 1
        else:
            stats["resolved"] += 1

    state_manager.sync_from_diff(cur, prev_keys)

    print(f"当前版本: {len(cur)}个冲突")
    print(f"历史基线: {len(prev)}个冲突")
    print(f"  新增: {stats['new']}")
    print(f"  持续: {stats['existing']}")
    print(f"  已解决: {stats['resolved']}")
    print(f"  已豁免(waived): {stats.get('waived', 0)}")

    out = output_path or current_path.replace(".json", "_diff.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(cur, f, ensure_ascii=False, indent=2)
    print(f"输出: {out}")
    return cur


def mark_waived(current_path, key_fragment, note=None):
    state_manager = ConflictStateManager()
    with open(current_path, "r", encoding="utf-8") as f:
        cur = json.load(f)
    matched = None
    for c in cur:
        k = make_key(c)
        if key_fragment in k:
            matched = (k, c)
            break
    if matched is None:
        print(f"未找到匹配 '{key_fragment}' 的冲突")
        return None
    key, conflict = matched
    state_manager.mark_waived_by_key(key, reviewer="human", note=note)
    print(f"已豁免: {key[:120]}")
    state_summary = state_manager.summary()
    print(f"状态库统计: {state_summary['by_status']}")
    return key


def mark_resolved(current_path, key_fragment, note=None):
    state_manager = ConflictStateManager()
    with open(current_path, "r", encoding="utf-8") as f:
        cur = json.load(f)
    matched = None
    for c in cur:
        k = make_key(c)
        if key_fragment in k:
            matched = (k, c)
            break
    if matched is None:
        print(f"未找到匹配 '{key_fragment}' 的冲突")
        return None
    key, conflict = matched
    state_manager.mark_resolved_by_key(key, reviewer="human", note=note)
    print(f"已标记为已解决: {key[:120]}")
    state_summary = state_manager.summary()
    print(f"状态库统计: {state_summary['by_status']}")
    return key


def show_status(current_path=None):
    state_manager = ConflictStateManager()
    summary = state_manager.summary()
    print(f"项目: {summary['project']}")
    print(f"缓存文件: {summary['cache_file']}")
    print(f"总记录: {summary['total']}")
    print(f"状态分布: {summary['by_status']}")

    if current_path and os.path.exists(current_path):
        with open(current_path, "r", encoding="utf-8") as f:
            cur = json.load(f)
        cur_keys = {make_key(c) for c in cur}
        waived = state_manager.list_by_status(STATUS_WAIVED)
        resolved = state_manager.list_by_status(STATUS_RESOLVED)

        if waived:
            print(f"\n已豁免({len(waived)})条:")
            for key, entry in waived:
                active = "✓" if key in cur_keys else "✗(已消失)"
                print(f"  {active} {key[:100]}")
                if entry.get("note"):
                    print(f"    原因: {entry['note']}")
        if resolved:
            print(f"\n已解决({len(resolved)})条:")
            for key, entry in resolved:
                active = "✓" if key in cur_keys else "✗(已消失)"
                print(f"  {active} {key[:100]}")
                if entry.get("note"):
                    print(f"    备注: {entry['note']}")
    return summary


def list_waived():
    state_manager = ConflictStateManager()
    waived = state_manager.list_by_status(STATUS_WAIVED)
    if not waived:
        print("无豁免记录")
        return
    print(f"豁免记录 ({len(waived)}条):")
    for key, entry in waived:
        print(f"  {key[:120]}")
        if entry.get("note"):
            print(f"    原因: {entry['note']}")
        print(f"    时间: {entry.get('updated_at', '')}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="冲突版本比对 + 持续状态管理")
    parser.add_argument("current", nargs="?", default="spatial_conflicts_v5.json",
                        help="当前版本冲突JSON")
    parser.add_argument("previous", nargs="?", default="spatial_conflicts_v4.json",
                        help="历史基线冲突JSON")
    parser.add_argument("output", nargs="?", default=None, help="输出JSON路径")
    parser.add_argument("--mark-waived", metavar="KEY_FRAGMENT",
                        help="将匹配的冲突标记为豁免(waived)")
    parser.add_argument("--mark-resolved", metavar="KEY_FRAGMENT",
                        help="将匹配的冲突标记为已解决(resolved)")
    parser.add_argument("--note", metavar="TEXT", help="标记时的备注说明")
    parser.add_argument("--status", action="store_true", help="显示状态库概况")
    parser.add_argument("--list-waived", action="store_true", help="列出所有豁免记录")
    args = parser.parse_args()

    if args.mark_waived:
        mark_waived(args.current, args.mark_waived, note=args.note)
    elif args.mark_resolved:
        mark_resolved(args.current, args.mark_resolved, note=args.note)
    elif args.status:
        show_status(args.current if args.current != "spatial_conflicts_v5.json" or os.path.exists(args.current) else None)
    elif args.list_waived:
        list_waived()
    else:
        diff(args.current, args.previous, args.output)
