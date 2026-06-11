# -*- coding: utf-8 -*-
import json
import os
import threading
from datetime import datetime
from collections import defaultdict


STATUS_NEW = "new"
STATUS_EXISTING = "existing"
STATUS_RESOLVED = "resolved"
STATUS_WAIVED = "waived"

VALID_STATUSES = frozenset([STATUS_NEW, STATUS_EXISTING, STATUS_RESOLVED, STATUS_WAIVED])


def make_key(c):
    t = c.get("type", "")
    f = c.get("floor", "")
    d = c.get("description", "")[:100]
    return f"{t}|{f}|{d}"


class ConflictStateManager:
    def __init__(self, cache_dir=None, project_name=None):
        if cache_dir is None:
            base = os.path.dirname(os.path.abspath(__file__))
            cache_dir = os.path.join(os.path.dirname(base), ".conflict_state_cache")
        if project_name is None:
            project_name = os.environ.get("PROJECT_NAME", "default")
        self._cache_dir = cache_dir
        self._project_name = project_name
        self._state_file = os.path.join(cache_dir, "conflict_states.json")
        self._lock = threading.Lock()
        self._states = {}
        self._loaded = False

    def _ensure_loaded(self):
        if self._loaded:
            return
        os.makedirs(self._cache_dir, exist_ok=True)
        if os.path.exists(self._state_file):
            try:
                with open(self._state_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._states = data.get("states", {})
            except (json.JSONDecodeError, IOError):
                self._states = {}
        self._loaded = True

    def _save(self):
        os.makedirs(self._cache_dir, exist_ok=True)
        data = {
            "version": "1.0",
            "project": self._project_name,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "states": self._states,
        }
        tmp_file = self._state_file + ".tmp"
        with self._lock:
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_file, self._state_file)  # 原子替换（M-64: 消除TOCTOU竞态）

    def get_status(self, conflict):
        self._ensure_loaded()
        key = make_key(conflict)
        entry = self._states.get(key)
        if entry:
            return entry.get("status", STATUS_NEW)
        return None

    def set_status(self, conflict, status, reviewer=None, note=None):
        if status not in VALID_STATUSES:
            raise ValueError(f"无效状态: {status}，有效值: {sorted(VALID_STATUSES)}")
        self._ensure_loaded()
        key = make_key(conflict)
        entry = self._states.get(key, {})
        entry["status"] = status
        entry["updated_at"] = datetime.now().isoformat(timespec="seconds")
        if reviewer is not None:
            entry["reviewer"] = reviewer
        if note is not None:
            entry["note"] = note
        self._states[key] = entry
        self._save()

    def set_waived(self, conflict, reviewer="human", note=None):
        self.set_status(conflict, STATUS_WAIVED, reviewer=reviewer, note=note)

    def set_resolved(self, conflict, reviewer="human", note=None):
        self.set_status(conflict, STATUS_RESOLVED, reviewer=reviewer, note=note)

    def set_new(self, conflict):
        self.set_status(conflict, STATUS_NEW)

    def set_existing(self, conflict):
        self.set_status(conflict, STATUS_EXISTING)

    def mark_waived_by_key(self, key, reviewer="human", note=None):
        self._ensure_loaded()
        entry = self._states.get(key, {})
        entry["status"] = STATUS_WAIVED
        entry["updated_at"] = datetime.now().isoformat(timespec="seconds")
        entry["reviewer"] = reviewer
        if note is not None:
            entry["note"] = note
        self._states[key] = entry
        self._save()

    def mark_resolved_by_key(self, key, reviewer="human", note=None):
        self._ensure_loaded()
        entry = self._states.get(key, {})
        entry["status"] = STATUS_RESOLVED
        entry["updated_at"] = datetime.now().isoformat(timespec="seconds")
        entry["reviewer"] = reviewer
        if note is not None:
            entry["note"] = note
        self._states[key] = entry
        self._save()

    def get_entry(self, conflict):
        self._ensure_loaded()
        key = make_key(conflict)
        return self._states.get(key)

    def get_entry_by_key(self, key):
        self._ensure_loaded()
        return self._states.get(key)

    def list_by_status(self, status):
        self._ensure_loaded()
        result = []
        for key, entry in self._states.items():
            if entry.get("status") == status:
                result.append((key, entry))
        return result

    def count_by_status(self):
        self._ensure_loaded()
        counts = defaultdict(int)
        for entry in self._states.values():
            counts[entry.get("status", STATUS_NEW)] += 1
        return dict(counts)

    def all_keys(self):
        self._ensure_loaded()
        return set(self._states.keys())

    def apply_states(self, conflicts):
        self._ensure_loaded()
        stats = {"new": 0, "existing": 0, "resolved": 0, "waived": 0, "unknown": 0}
        for c in conflicts:
            key = make_key(c)
            entry = self._states.get(key)
            if entry:
                status = entry.get("status", STATUS_NEW)
                c["status"] = status
                c["reviewer"] = entry.get("reviewer", "")
                c["review_note"] = entry.get("note", "")
                c["reviewed_at"] = entry.get("updated_at", "")
                if status in stats:
                    stats[status] += 1
            else:
                stats["unknown"] += 1
        return stats

    def sync_from_diff(self, current_conflicts, previous_keys):
        self._ensure_loaded()
        for c in current_conflicts:
            key = make_key(c)
            if key in self._states:
                existing_status = self._states[key].get("status")
                if existing_status in (STATUS_WAIVED, STATUS_RESOLVED):
                    continue
            if key not in previous_keys:
                self._states.setdefault(key, {})["status"] = STATUS_NEW
        cur_keys = {make_key(c) for c in current_conflicts}
        for key in previous_keys:
            if key not in cur_keys:
                if key in self._states:
                    entry_status = self._states[key].get("status")
                    if entry_status in (STATUS_RESOLVED, STATUS_WAIVED):
                        continue
                self._states[key] = {
                    "status": STATUS_RESOLVED,
                    "updated_at": datetime.now().isoformat(timespec="seconds"),
                    "reviewer": "auto",
                    "note": "冲突在新版本中消失，自动标记为resolved",
                }
        self._save()

    def summary(self):
        self._ensure_loaded()
        counts = self.count_by_status()
        return {
            "total": sum(counts.values()),
            "by_status": counts,
            "project": self._project_name,
            "cache_file": self._state_file,
        }
