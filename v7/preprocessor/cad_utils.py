import os
from typing import Optional

_DEFAULT_AUTOCAD_PATHS = [
    r"E:\Program Files\CAD2024\AutoCAD 2024\acad.exe",
    r"C:\Program Files\Autodesk\AutoCAD 2024\acad.exe",
    r"C:\Program Files\Autodesk\AutoCAD 2023\acad.exe",
    r"C:\Program Files\Autodesk\AutoCAD 2022\acad.exe",
    r"C:\Program Files\Autodesk\AutoCAD 2021\acad.exe",
    r"C:\Program Files\ZWSOFT\ZWCAD 2023\Zwcad.exe",
    r"C:\Program Files\ZWSOFT\ZWCAD 2022\Zwcad.exe",
    r"C:\Program Files\AutoCAD\acad.exe",
]

_ODA_PATHS = [
    r"C:\Program Files\ODA\ODAFileConverter 24.11.0\ODAFileConverter.exe",
    r"C:\Program Files\ODA\ODAFileConverter 24.10.0\ODAFileConverter.exe",
    r"C:\Program Files\ODA\ODAFileConverter 23.10.0\ODAFileConverter.exe",
    r"C:\Program Files\ODA\ODAFileConverter\ODAFileConverter.exe",
]
_DWG_OUTPUT_VERSION = "ACAD2013"


def get_autocad_paths() -> list:
    env_path = os.environ.get("AUTOCAD_PATH", "")
    if env_path:
        return [env_path]
    return _DEFAULT_AUTOCAD_PATHS


def get_oda_paths() -> list:
    env_path = os.environ.get("ODA_CONVERTER_PATH", "")
    if env_path:
        return [env_path]
    return _ODA_PATHS


def get_dwg_output_version() -> str:
    return os.environ.get("DWG_OUTPUT_VERSION", _DWG_OUTPUT_VERSION)


def find_autocad() -> Optional[str]:
    for p in get_autocad_paths():
        if os.path.exists(p):
            return p
    return None


def find_oda_converter() -> Optional[str]:
    for p in get_oda_paths():
        if os.path.exists(p):
            return p
    try:
        import subprocess
        result = subprocess.run(
            ["where", "ODAFileConverter.exe"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip().split("\n")[0]
    except Exception:
        pass
    return None
