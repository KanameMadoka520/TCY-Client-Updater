import os
import re
from urllib.parse import urlparse


_VERSION_TOKEN_RE = re.compile(r"\d+|[A-Za-z]+")


def version_sort_key(version_text):
    text = str(version_text or "").strip()
    if not text:
        return ((0, ""),)

    tokens = []
    for token in _VERSION_TOKEN_RE.findall(text):
        if token.isdigit():
            tokens.append((1, int(token)))
        else:
            tokens.append((0, token.lower()))

    if not tokens:
        tokens.append((0, text.lower()))
    return tuple(tokens)


def compare_versions(left, right):
    left_key = version_sort_key(left)
    right_key = version_sort_key(right)
    return (left_key > right_key) - (left_key < right_key)


def is_version_newer(candidate, current):
    return compare_versions(candidate, current) > 0


def sort_versioned_items(items, key="version", reverse=False):
    return sorted(
        items,
        key=lambda item: version_sort_key(item.get(key, "")) if isinstance(item, dict) else version_sort_key(""),
        reverse=reverse,
    )


def build_url_list(default_url, github_url, custom_url="", mirror_prefix=""):
    urls = []

    def add(url):
        value = str(url or "").strip()
        if value and value not in urls:
            urls.append(value)

    custom = str(custom_url or "").strip()
    default = str(default_url or "").strip()
    github = str(github_url or "").strip()
    mirror = str(mirror_prefix or "").strip()

    add(custom)
    add(default)
    add(github)

    if mirror and github and not github.startswith(mirror):
        add(mirror + github)

    return urls


def bounded_worker_count(total_count, max_workers, min_workers=1):
    total = int(total_count or 0)
    upper = max(int(max_workers or 1), 1)
    lower = max(int(min_workers or 1), 1)

    if total <= 0:
        return lower
    return min(max(total, lower), upper)


def summarize_url_fetch_results(url_list, results_by_url):
    success_urls = []
    failed_urls = []
    first_data = None

    for url in url_list or []:
        outcome = results_by_url.get(url) if isinstance(results_by_url, dict) else None
        if outcome and outcome.get("ok"):
            success_urls.append(url)
            if first_data is None:
                first_data = outcome.get("data")
        else:
            failed_urls.append(url)

    return first_data, success_urls, failed_urls


def summarize_elapsed_ms(values):
    samples = [int(value) for value in (values or []) if isinstance(value, (int, float))]
    if not samples:
        return {"count": 0, "min_ms": None, "avg_ms": None, "max_ms": None}

    return {
        "count": len(samples),
        "min_ms": min(samples),
        "avg_ms": round(sum(samples) / len(samples)),
        "max_ms": max(samples),
    }


def select_pending_updates(history, local_version, skipped_versions):
    skipped_set = {
        str(version).strip()
        for version in (skipped_versions or [])
        if str(version).strip()
    }
    candidates = []

    for item in history if isinstance(history, list) else []:
        if not isinstance(item, dict):
            continue

        version = str(item.get("version") or "").strip()
        if compare_versions(version, local_version) > 0:
            candidates.append(item)
        elif version in skipped_set:
            skipped_set.discard(version)

    return sort_versioned_items(candidates), sorted(skipped_set, key=version_sort_key)


def collect_https_hosts(urls, enabled=True):
    if not enabled:
        return set()
    hosts = set()
    for url in urls or []:
        host = urlparse(str(url or "").strip()).hostname
        if host:
            hosts.add(host.lower())
    return hosts


def ssl_mode_for_url(url, insecure_hosts=()):
    parsed = urlparse(str(url or "").strip())
    if parsed.scheme.lower() != "https":
        return "none"

    host = (parsed.hostname or "").lower()
    insecure = {str(item or "").strip().lower() for item in (insecure_hosts or []) if str(item or "").strip()}
    if host and host in insecure:
        return "compat"
    return "strict"


def classify_mirror_latency(latency_ms, ok):
    if not ok or latency_ms is None or latency_ms < 0:
        return "down"
    if latency_ms < 500:
        return "good"
    if latency_ms < 1000:
        return "warn"
    return "slow"


def build_self_update_batch_script(old_exe_path, temp_download_path, new_exe_path, current_pid, status_log_path):
    old_exe = str(old_exe_path).replace("/", "\\")
    temp_download = str(temp_download_path).replace("/", "\\")
    new_exe = str(new_exe_path).replace("/", "\\")
    status_log = str(status_log_path).replace("/", "\\")

    lines = [
        "@echo off",
        "chcp 65001 >nul 2>&1",
        f'set "OLD_EXE={old_exe}"',
        f'set "NEW_TMP={temp_download}"',
        f'set "NEW_EXE={new_exe}"',
        f'set "STATUS_LOG={status_log}"',
        'echo [%date% %time%] 自更新脚本启动 > "%STATUS_LOG%"',
        f"taskkill /F /PID {int(current_pid)} >nul 2>&1",
        "set RETRY=0",
        ":WAIT_LOOP",
        "timeout /t 1 /nobreak >nul",
        'del /F /Q "%OLD_EXE%" >nul 2>&1',
        'if exist "%OLD_EXE%" (',
        '  set /a RETRY+=1',
        '  if %RETRY% LSS 20 goto WAIT_LOOP',
        '  echo [%date% %time%] 无法删除旧版本文件：%OLD_EXE% >> "%STATUS_LOG%"',
        '  exit /b 1',
        ")",
        'if exist "%NEW_EXE%" del /F /Q "%NEW_EXE%" >nul 2>&1',
        'move /Y "%NEW_TMP%" "%NEW_EXE%" >nul',
        'if errorlevel 1 (',
        '  echo [%date% %time%] 无法将临时文件重命名为新版本：%NEW_TMP% -> %NEW_EXE% >> "%STATUS_LOG%"',
        '  exit /b 1',
        ")",
        'if not exist "%NEW_EXE%" (',
        '  echo [%date% %time%] 新版本文件不存在：%NEW_EXE% >> "%STATUS_LOG%"',
        '  exit /b 1',
        ")",
        'echo [%date% %time%] 自更新完成，准备启动：%NEW_EXE% >> "%STATUS_LOG%"',
        'start "" "%NEW_EXE%"',
        'del "%~f0"',
    ]
    return "\r\n".join(lines) + "\r\n"


def resolve_relative_path(base_dir, relative_path):
    if not isinstance(relative_path, str):
        raise ValueError("path must be a string")

    trimmed = relative_path.strip()
    if not trimmed:
        raise ValueError("path must not be empty")

    normalized = trimmed.replace("\\", os.sep).replace("/", os.sep)
    if os.path.isabs(normalized):
        raise ValueError("absolute paths are not allowed")

    base_real = os.path.realpath(base_dir)
    target_real = os.path.realpath(os.path.join(base_real, normalized))

    try:
        common = os.path.commonpath([base_real, target_real])
    except ValueError as exc:
        raise ValueError("path escapes base directory") from exc

    if common != base_real:
        raise ValueError("path escapes base directory")

    return target_real
