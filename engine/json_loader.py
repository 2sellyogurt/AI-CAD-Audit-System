# -*- coding: utf-8 -*-
import os
import re
import json
import glob as glob_module
from typing import Any, Dict, List, Optional


_UUID_PATTERN = re.compile(
    r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}_'
)

_EMPTY_DATA: Dict[str, Any] = {
    "raw_texts": [],
    "elevations": [],
    "metadata": {
        "source_file": "",
        "discipline": "",
        "building": "",
        "text_count": 0,
        "elevation_count": 0,
    },
}

_loader_cache: Dict[str, "JsonLoader"] = {}
_dedup_cache: Dict[str, Any] = {}


def _detect_encoding(file_path: str) -> str:
    try:
        with open(file_path, 'rb') as f:
            raw = f.read(4096)
    except OSError:
        return 'utf-8'
    if raw[:3] == b'\xef\xbb\xbf':
        return 'utf-8-sig'
    if raw[:2] in (b'\xff\xfe', b'\xfe\xff'):
        return 'utf-16'
    try:
        raw.decode('utf-8')
        return 'utf-8'
    except UnicodeDecodeError:
        pass
    try:
        raw.decode('gbk')
        return 'gbk'
    except UnicodeDecodeError:
        pass
    try:
        raw.decode('gb18030')
        return 'gb18030'
    except UnicodeDecodeError:
        pass
    return 'utf-8'


def _repair_json_text(text: str) -> str:
    text = text.replace('\ufeff', '')
    text = re.sub(r'//.*?$', '', text, flags=re.MULTILINE)
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)
    text = re.sub(r',\s*([}\]])', r'\1', text)
    text = re.sub(r"'", '"', text)
    return text


def _load_json_file(file_path: str) -> Dict[str, Any]:
    encoding = _detect_encoding(file_path)
    try:
        with open(file_path, 'r', encoding=encoding, errors='replace') as f:
            content = f.read()
    except OSError:
        return dict(_EMPTY_DATA)
    content = _repair_json_text(content)
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return dict(_EMPTY_DATA)
    if not isinstance(data, dict):
        return dict(_EMPTY_DATA)
    if 'raw_texts' not in data:
        data['raw_texts'] = []
    if 'elevations' not in data:
        data['elevations'] = []
    if 'metadata' not in data:
        data['metadata'] = {
            'source_file': '',
            'discipline': '',
            'building': '',
            'text_count': len(data.get('raw_texts', [])),
            'elevation_count': len(data.get('elevations', [])),
        }
    return data


class JsonLoader:

    def __init__(self, json_dir: str) -> None:
        self._json_dir: str = os.path.abspath(json_dir)
        self._files: List[str] = []
        self._data: Dict[str, Dict[str, Any]] = {}
        self._readable_names: Dict[str, str] = {}
        self._load_all()

    def _load_all(self) -> None:
        if not os.path.isdir(self._json_dir):
            return
        pattern = os.path.join(self._json_dir, '*_unified.json')
        found = glob_module.glob(pattern)
        self._files = sorted(
            [os.path.basename(f) for f in found],
            key=lambda x: x,
        )
        for fn in self._files:
            full_path = os.path.join(self._json_dir, fn)
            self._data[fn] = _load_json_file(full_path)
            self._readable_names[fn] = self._compute_readable_name(fn)

    def _compute_readable_name(self, filename: str) -> str:
        name = filename
        if name.endswith('_unified.json'):
            name = name[:-len('_unified.json')]
        m = _UUID_PATTERN.match(name)
        if m:
            name = name[m.end():]
        return name

    @property
    def files(self) -> List[str]:
        return list(self._files)

    def get_readable_name(self, fn: str) -> str:
        if fn in self._readable_names:
            return self._readable_names[fn]
        name = os.path.basename(fn)
        if name.endswith('_unified.json'):
            name = name[:-len('_unified.json')]
        m = _UUID_PATTERN.match(name)
        if m:
            name = name[m.end():]
        return name

    def get_text_lines_by_file(self, full_name: str) -> List[str]:
        fn = os.path.basename(full_name)
        data = self._data.get(fn)
        if data is None:
            return []
        raw_texts = data.get('raw_texts', [])
        if not isinstance(raw_texts, list):
            return []
        result: List[str] = []
        for item in raw_texts:
            if isinstance(item, str):
                result.append(item)
            elif isinstance(item, dict):
                text_val = item.get('text', item.get('content', ''))
                result.append(str(text_val) if text_val else '')
            else:
                result.append(str(item))
        return result

    def get_file_count(self) -> int:
        return len(self._files)

    def get_metadata_field(self, fn: str, field: str) -> str:
        data = self._data.get(os.path.basename(fn), {})
        if not isinstance(data, dict):
            return ""
        metadata = data.get("metadata", {})
        if not isinstance(metadata, dict):
            return ""
        return str(metadata.get(field, ""))

    def get_elevations_for_file(self, fn: str) -> List[Dict[str, Any]]:
        data = self._data.get(os.path.basename(fn), {})
        if not isinstance(data, dict):
            return []
        elevs = data.get("elevations", [])
        return elevs if isinstance(elevs, list) else []

    def get_axes_for_file(self, fn: str) -> List[str]:
        data = self._data.get(os.path.basename(fn), {})
        if not isinstance(data, dict):
            return []
        axes = data.get("axes", [])
        return axes if isinstance(axes, list) else []

    def get_professional_data(self, fn: str) -> Dict[str, Any]:
        data = self._data.get(fn, {})
        if not isinstance(data, dict):
            return {}
        return data.get("professional_data", {})

    def ensure_professional_data(self) -> None:
        for fn in self._files:
            data = self._data.get(fn, {})
            if not isinstance(data, dict):
                continue
            if "professional_data" not in data:
                data["professional_data"] = {}
            pd = data["professional_data"]
            if not isinstance(pd, dict):
                data["professional_data"] = {}
                pd = data["professional_data"]
            metadata = data.get("metadata", {})
            if isinstance(metadata, dict):
                if not pd.get("discipline"):
                    pd["discipline"] = metadata.get("discipline", "")
                if not pd.get("source_file"):
                    pd["source_file"] = metadata.get("source_file", fn)
                if not pd.get("building"):
                    pd["building"] = metadata.get("building", "")
            if not pd.get("source_file"):
                pd["source_file"] = fn
            if not pd.get("discipline"):
                pd["discipline"] = self._infer_discipline(fn)

    def _infer_discipline(self, fn: str) -> str:
        from .drawing_classifier import DrawingClassifier
        classifier = DrawingClassifier()
        return classifier.classify(fn)

    def get_metadata_by_file(self, full_name: str) -> Dict[str, Any]:
        fn = os.path.basename(full_name)
        data = self._data.get(fn, {})
        if not isinstance(data, dict):
            return {}
        return data.get("metadata", {})

    def get_full_text_by_file(self, full_name: str) -> str:
        lines = self.get_text_lines_by_file(full_name)
        return " ".join(lines)

    def get_dedup_engine(self) -> Any:
        from engine.dedup_engine import DedupEngine
        cache_key = self._json_dir
        if cache_key in _dedup_cache:
            return _dedup_cache[cache_key]

        engine = DedupEngine()
        for fn in self._files:
            data = self._data.get(fn, {})
            raw_texts = self.get_text_lines_by_file(fn)
            metadata = data.get("metadata", {})
            if not isinstance(metadata, dict):
                metadata = {}
            if "elevations" not in metadata and "elevations" in data:
                metadata["elevations"] = data["elevations"]
            if "axes" not in metadata and "axes" in data:
                metadata["axes"] = data["axes"]
            readable = self._readable_names.get(fn, fn)
            engine.register(fn, readable, raw_texts, metadata)

        _dedup_cache[cache_key] = engine
        return engine

    def get_dedup_summary(self) -> Dict[str, Any]:
        engine = self.get_dedup_engine()
        return engine.get_summary()

    def get_unique_file_keys(self) -> List[str]:
        engine = self.get_dedup_engine()
        dedup = engine.compute_dedup_report()
        return dedup.unique_files
