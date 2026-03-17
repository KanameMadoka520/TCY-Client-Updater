# -*- coding: utf-8 -*-
import ctypes
import os
import platform
import shutil
import time


def format_gb(value):
    if value is None:
        return None
    try:
        return round(float(value), 1)
    except Exception:
        return None


def get_windows_cpu_name():
    cpu_name = ""
    if os.name == 'nt':
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"HARDWARE\DESCRIPTION\System\CentralProcessor\0"
            ) as key:
                cpu_name = str(winreg.QueryValueEx(key, "ProcessorNameString")[0]).strip()
        except Exception:
            cpu_name = ""

    if not cpu_name:
        cpu_name = str(platform.processor() or "").strip()
    if not cpu_name:
        cpu_name = str(os.environ.get("PROCESSOR_IDENTIFIER") or "").strip()
    return cpu_name or "未知 CPU"


def get_available_memory_gb():
    try:
        if hasattr(ctypes, 'windll') and os.name == 'nt':
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ('dwLength', ctypes.c_ulong),
                    ('dwMemoryLoad', ctypes.c_ulong),
                    ('ullTotalPhys', ctypes.c_ulonglong),
                    ('ullAvailPhys', ctypes.c_ulonglong),
                    ('ullTotalPageFile', ctypes.c_ulonglong),
                    ('ullAvailPageFile', ctypes.c_ulonglong),
                    ('ullTotalVirtual', ctypes.c_ulonglong),
                    ('ullAvailVirtual', ctypes.c_ulonglong),
                    ('ullAvailExtendedVirtual', ctypes.c_ulonglong),
                ]

            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
            return format_gb(int(stat.ullAvailPhys) / (1024 ** 3))

        page_size = os.sysconf('SC_PAGE_SIZE')
        avail_pages = os.sysconf('SC_AVPHYS_PAGES')
        return format_gb(int(page_size * avail_pages) / (1024 ** 3))
    except Exception:
        return None


def get_disk_usage_for_path(path):
    try:
        target = path if path and os.path.exists(path) else os.getcwd()
        usage = shutil.disk_usage(target)
        return {
            "total_gb": format_gb(usage.total / (1024 ** 3)),
            "free_gb": format_gb(usage.free / (1024 ** 3)),
            "used_gb": format_gb(usage.used / (1024 ** 3)),
        }
    except Exception:
        return {"total_gb": None, "free_gb": None, "used_gb": None}


def summarize_java_versions(detected_versions, selected_java=None):
    versions = detected_versions if isinstance(detected_versions, list) else []
    result = {
        "java_count": len(versions),
        "current_java_label": "",
        "current_java_note": "",
    }

    if not versions:
        result["current_java_note"] = "当前未检测到系统里的可用 Java。"
        return result

    selected_path = ""
    if isinstance(selected_java, dict):
        selected_path = os.path.normcase(os.path.normpath(str(selected_java.get("java_path") or "").strip()))

    matched = None
    if selected_path:
        for item in versions:
            item_path = os.path.normcase(os.path.normpath(str(item.get("path") or "").strip()))
            if item_path == selected_path:
                matched = item
                break

    if matched:
        major = matched.get("major")
        version = str(matched.get("version") or "").strip()
        label = ""
        if major:
            label = f"Java {major}"
            if version and version != str(major):
                label = f"{label} ({version})"
        elif version:
            label = version
        if matched.get("is_graalvm") and "graalvm" not in label.lower():
            label = f"GraalVM {label}".strip()
        launcher = str(selected_java.get("launcher") or "启动器").strip()
        result["current_java_label"] = label
        result["current_java_note"] = f"依据 {launcher} 配置文件中的 Java 路径判断。"
        return result

    if selected_path:
        launcher = str((selected_java or {}).get("launcher") or "启动器").strip()
        result["current_java_note"] = f"已从 {launcher} 配置里读到 Java 路径，但当前没法稳定识别版本，所以这里不显示版本名。"
    else:
        result["current_java_note"] = "暂时无法从常见启动器配置里可靠读取当前实际使用的 Java 路径，所以这里不显示版本名。"
    return result


def build_advice(system_info, client_info):
    items = []
    score = 0

    total_ram = float(system_info.get("ram_total_gb") or 0)
    avail_ram = float(system_info.get("ram_available_gb") or 0)
    disk_free = float(system_info.get("disk_free_gb") or 0)
    java_count = int(client_info.get("java_count") or 0)

    if java_count <= 0:
        score = max(score, 3)
        items.append({"severity": "error", "text": "未检测到可用 Java，客户端可能无法正常启动。"})

    if total_ram and total_ram < 6:
        score = max(score, 3)
        items.append({"severity": "error", "text": "总内存低于 6 GB，已经属于比较明确的基础硬件瓶颈。"})
    elif total_ram and total_ram < 8:
        score = max(score, 2)
        items.append({"severity": "warn", "text": "总内存低于 8 GB，基础运行条件会比较吃紧。"})

    if avail_ram and avail_ram < 3:
        score = max(score, 1)
        items.append({"severity": "warn", "text": "当前可用内存低于 3 GB。若这是因为你习惯保留很多后台程序，可按需忽略；如果实际游玩会卡，再优先清理后台。"})

    if disk_free and disk_free < 10:
        score = max(score, 3)
        items.append({"severity": "error", "text": "磁盘剩余空间低于 10 GB，更新、备份或生成缓存前建议先清理空间。"})
    elif disk_free and disk_free < 20:
        score = max(score, 1)
        items.append({"severity": "warn", "text": "磁盘剩余空间低于 20 GB，更新和备份前建议预留更多空间。"})

    if not items:
        items.append({"severity": "info", "text": "这里只看 Java、内存和磁盘这些基础条件的话，当前没有发现明显问题。"})

    level_map = {
        0: ("good", "基础运行条件看起来正常，没有明显短板。"),
        1: ("ok", "基础运行条件大体够用，但有一两项值得留意。"),
        2: ("tight", "当前存在比较明确的基础条件风险，开游戏前最好先处理一下。"),
        3: ("critical", "当前存在关键基础条件问题，先处理再继续会更稳妥。"),
    }
    level, summary = level_map.get(score, level_map[1])
    return {
        "level": level,
        "summary": summary,
        "items": items[:4],
    }


def build_system_overview(system_input, client_input):
    system_info = {
        "os_name": str(system_input.get("os_name") or "未知系统"),
        "os_version": str(system_input.get("os_version") or "未知版本"),
        "cpu_name": str(system_input.get("cpu_name") or "未知 CPU"),
        "cpu_threads": int(system_input.get("cpu_threads") or 0),
        "ram_total_gb": format_gb(system_input.get("ram_total_gb")),
        "ram_available_gb": format_gb(system_input.get("ram_available_gb")),
        "disk_total_gb": format_gb(system_input.get("disk_total_gb")),
        "disk_free_gb": format_gb(system_input.get("disk_free_gb")),
    }

    client_info = {
        "game_root": str(client_input.get("game_root") or ""),
        "local_version": str(client_input.get("local_version") or "未知"),
        "java_count": int(client_input.get("java_count") or 0),
        "current_java_label": str(client_input.get("current_java_label") or ""),
        "current_java_note": str(client_input.get("current_java_note") or ""),
        "mods_enabled": int(client_input.get("mods_enabled") or 0),
        "mods_disabled": int(client_input.get("mods_disabled") or 0),
        "save_count": int(client_input.get("save_count") or 0),
        "screenshot_count": int(client_input.get("screenshot_count") or 0),
    }

    advice = build_advice(system_info, client_info)
    return {
        "generated_at": time.strftime('%Y-%m-%d %H:%M:%S'),
        "system": system_info,
        "client": client_info,
        "advice": advice,
    }
