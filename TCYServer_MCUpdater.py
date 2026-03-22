# -*- coding: utf-8 -*-
"""
PROJECT: TCY Client Updater
AUTHOR: KanameMadoka520
LICENSE: CC BY-NC-SA 4.0 (Creative Commons Attribution-NonCommercial-ShareAlike 4.0)

此项目遵循 CC BY-NC-SA 4.0 协议。
1. 允许非商业用途的复制、修改和分发。
2. 禁止任何形式的商业盈利行为（包括但不限于付费整合包、付费服专用客户端）。
3. 修改后的版本必须以相同协议（开源）发布，并保留原作者署名。

详情请参阅: https://creativecommons.org/licenses/by-nc-sa/4.0/
"""

import sys
import os
import logging
from logging.handlers import RotatingFileHandler
import traceback
import json
import re
import zipfile
import shutil
import glob
import threading
import base64
import time
import hashlib
import uuid
import gzip
import io
import subprocess
import platform
from pathlib import Path
from datetime import datetime
import webbrowser
from multiprocessing import freeze_support
from TCYNBTeditor import NbtIO, open_nbt_editor, open_nbt_editor_empty
from jvm_advisor import build_jvm_recommendation, normalize_jvm_advisor_settings, JAVA_VERSION_NOTES
from mirror_catalog import DEFAULT_MIRROR_PREFIX, MIRROR_CATALOG, get_mirror_urls
from system_overview import build_system_overview, get_available_memory_gb, get_disk_usage_for_path, get_windows_cpu_name, summarize_java_versions
from updater_utils import bounded_worker_count, build_self_update_batch_script, build_url_list, classify_mirror_latency, collect_https_hosts, is_version_newer, resolve_relative_path, select_pending_updates, sort_versioned_items, ssl_mode_for_url, summarize_elapsed_ms, summarize_url_fetch_results, version_sort_key
from concurrent.futures import ThreadPoolExecutor, as_completed

# === 网络请求相关库 ===
import urllib.request
import urllib.error
from urllib.parse import urlparse
import ssl
import socket

import ctypes
from ctypes import windll, c_long, c_int, byref
try:
    import winreg
except Exception:
    winreg = None

# 窗口样式常量
GWL_STYLE = -16
WS_THICKFRAME = 0x00040000  # 关键：这是允许窗口调整大小的样式位
WS_CAPTION = 0x00C00000     # 标题栏样式（我们需要移除它，防止出现系统标题栏）

# 系统命令常量
WM_SYSCOMMAND = 0x0112
SC_SIZE = 0xF000

# === 开启 GPU 加速 (注释掉禁用代码) ===
# os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = "--disable-gpu --disable-d3d11 --disable-accelerated-video-decode"

if getattr(sys, 'frozen', False):
    current_dir = os.path.dirname(sys.executable)
    sys.stdout = open(os.devnull, 'w')
    sys.stderr = open(os.devnull, 'w')
else:
    current_dir = os.path.dirname(os.path.abspath(__file__))

log_file_path = os.path.join(current_dir, "launcher_debug.log")
logger = logging.getLogger("TCYUpdater")
logger.setLevel(logging.DEBUG)
_rfh = RotatingFileHandler(log_file_path, maxBytes=5*1024*1024, backupCount=3, encoding='utf-8')
_rfh.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
logger.addHandler(_rfh)

def log_info(msg): logger.info(msg)
def log_error(msg): logger.error(msg)
def log_warning(msg): logger.warning(msg)

def flush_log_handlers():
    for handler in logger.handlers:
        try:
            handler.flush()
        except Exception:
            pass

try:
    import webview
except Exception as e:
    with open(os.path.join(current_dir, "CRASH_IMPORT.txt"), "w") as f: f.write(traceback.format_exc())
    sys.exit(1)

# Pillow 已从默认打包依赖中移除：
# - 默认使用 WebView2 前端生成缩略图/预览并回传缓存到磁盘（避免打包 PIL 导致体积膨胀）
# - 开发环境如需 Pillow 作为兜底，可动态 import（冻结包内通常不会包含 Pillow）

def _try_import_pillow_image():
    try:
        import importlib
        return importlib.import_module('PIL.Image')
    except Exception:
        return None

TARGET_VERSION_NAME = "异界战斗幻想"
CONFIG_FILE = "launcher_settings.json"

# ===整合包初始版本 (客户端内容版本) ===
INITIAL_VERSION = "26.02.06.15.24"
# ===更新器自身版本 (传统版本号) ===
LAUNCHER_INTERNAL_VERSION = "1.0.7"

# === 默认版本检查 JSON 地址 ===
DEFAULT_LATEST_JSON_URL = "https://tcymc.space/update/latest.json"
DEFAULT_UPDATER_JSON_URL = "https://tcymc.space/update/Updater-latest.json"

# === GitHub 备用地址 ===
GITHUB_LATEST_JSON_URL = "https://github.com/KanameMadoka520/TCY-Client-Updater/releases/download/versions/latest.json"
GITHUB_UPDATER_JSON_URL = "https://github.com/KanameMadoka520/TCY-Client-Updater/releases/download/versions/Updater-latest.json"

MIRROR_LIST = get_mirror_urls()

JSON_FETCH_MAX_WORKERS = 4
MIRROR_SPEED_MAX_WORKERS = 6

global_window = None

try:
    from tcy_assets import BACKGROUND_IMAGE_B64 as DEFAULT_BG_B64
except ImportError:
    DEFAULT_BG_B64 = ""

def get_resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'): base_path = sys._MEIPASS
    else: base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

class ConfigManager:
    def __init__(self):
        self.default_config = {
            "bg_type": "default", "custom_bg_data": "", "visual_effect": "glass",
            "mask_opacity": 40, "blur_radius": 0, "text_color": "#333333",
            "accent_color": "#f59e0b", "bg_mode": "cover",
            "font_family": "'Segoe UI', system-ui, sans-serif",
            "current_version": INITIAL_VERSION,
            # ===自定义镜像前缀 ===
            "mirror_prefix": DEFAULT_MIRROR_PREFIX,
            # === 默认窗口大小 (宽x高) ===
            "window_size": "950x700",
            # ===跳过的可选版本记录 ===
            "skipped_versions": [],
            # === 自定义版本检查 JSON 地址 (为空则使用默认地址) ===
            "custom_latest_url": "",
            "custom_updater_url": "",
            # === 缓存的更新历史记录 (从 latest.json 拉取后写入本地) ===
            "cached_history": [],
            "max_backups": 1,
            "parallel_downloads": 3,
            "mod_presets": [],
            "mod_dep_ignores": {},
            "auto_select_mirror": True,
            "allow_insecure_mirror_ssl": True,
            "mirror_speed_cache": {},
            "activity_log": [],
            "ai_api_url": "",
            "ai_api_key": "",
            "ai_model": "gpt-3.5-turbo",
            "jvm_profile": "medium",
            "jvm_subpage": "overview",
            "jvm_template": "custom",
            "mc_version": "1.20.1",
            "loader": "forge",
            "modpack_scale": "medium",
            "cpu_tier": "mainstream",
            "is_x3d": False,
            "preferred_java_version": "auto",

            # === 截图收藏夹（仅保存引用，不复制文件） ===
            "favorite_folders": [
                {"id": "default", "name": "默认收藏", "created": time.strftime('%Y-%m-%d %H:%M:%S'), "items": []}
            ],
            "favorite_last_folder_id": "default",
        }
        self.config = self.load_config()
    def load_config(self):
        config_path = os.path.join(current_dir, CONFIG_FILE)
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    saved_config = json.load(f)
                    config = self.default_config.copy()
                    config.update(saved_config)
                    return config
            except Exception: pass
        return self.default_config.copy()
    def save_config(self, new_config):
        self.config.update(new_config)
        save_data = self.config.copy()
        if save_data['bg_type'] != 'custom': save_data['custom_bg_data'] = "" 
        try:
            with open(os.path.join(current_dir, CONFIG_FILE), 'w', encoding='utf-8') as f: json.dump(save_data, f, indent=4)
        except Exception: pass

class Api:

    # Track in-progress backup operations by world folder name (race condition guard)
    _active_backups = set()
    _screenshot_cache_lock = threading.Lock()
    _screenshot_cache_inflight = set()
    _screenshot_prewarm_started = False

    def __init__(self):
        self.game_root = self.find_game_root()
        self.cfg_mgr = ConfigManager()
        self.cancel_event = threading.Event()
        self.update_stage = 0  # 0: idle, 1: downloading, 2: applying
        self._pending_update_preview = None
        self._preview_ttl_seconds = 600
        self.log(f"核心初始化完成，根目录定位: {self.game_root}")

    def cancel_current_update(self):
        if self.update_stage == 1:
            self.cancel_event.set()
            self.log("用户请求取消当前下载...")
            return True
        return False

    def _safe_js_alert(self, message):
        if not global_window:
            return
        safe = str(message).replace('\\', '\\\\').replace("'", "\\'").replace("\n", " ")
        try:
            global_window.evaluate_js(f"alert('{safe}')")
        except Exception:
            pass

    def _is_network_timeout_error(self, err):
        s = str(err).lower()
        timeout_keywords = ['timed out', 'timeout', 'time out', 'stall timeout']
        if any(k in s for k in timeout_keywords):
            return True
        if isinstance(err, (socket.timeout, TimeoutError)):
            return True
        reason = getattr(err, 'reason', None)
        if isinstance(reason, (socket.timeout, TimeoutError)):
            return True
        return False

    def _build_download_candidates(self, original_url, source_type):
        candidates = []

        def add_candidate(u):
            if isinstance(u, str) and u and u not in candidates:
                candidates.append(u)

        if source_type == 'cn' and isinstance(original_url, str) and 'github.com' in original_url:
            prefix = self.cfg_mgr.config.get("mirror_prefix", DEFAULT_MIRROR_PREFIX)
            mirrored = original_url
            if prefix and not original_url.startswith(prefix):
                mirrored = prefix + original_url
            add_candidate(mirrored)
            add_candidate(original_url)
        else:
            add_candidate(original_url)

        return candidates

    def _get_insecure_ssl_hosts(self):
        configured_mirror = self.cfg_mgr.config.get("mirror_prefix", DEFAULT_MIRROR_PREFIX).strip()
        allow_insecure = bool(self.cfg_mgr.config.get("allow_insecure_mirror_ssl", True))
        return collect_https_hosts(list(MIRROR_LIST) + [configured_mirror], enabled=allow_insecure)

    def _get_ssl_context_for_url(self, url):
        mode = ssl_mode_for_url(url, insecure_hosts=self._get_insecure_ssl_hosts())
        if mode == "none":
            return None, mode
        if mode == "compat":
            return ssl._create_unverified_context(), mode
        return ssl.create_default_context(), mode

    def _urlopen_with_policy(self, req, timeout, url=None):
        target_url = url or getattr(req, "full_url", None) or getattr(req, "get_full_url", lambda: "")()
        context, mode = self._get_ssl_context_for_url(target_url)
        if mode == "strict":
            log_info(f"SSL策略[strict]: {target_url}")
        if mode == "compat":
            log_warning(f"SSL策略[compat]: {target_url}")
        if context is None:
            return urllib.request.urlopen(req, timeout=timeout)
        return urllib.request.urlopen(req, timeout=timeout, context=context)

    def _download_url_to_path(self, url, dest_path, progress_cb=None, connect_timeout=8, stall_timeout=15, allow_cancel=False):
        req = urllib.request.Request(url, headers={'User-Agent': 'TCYClientUpdater/1.0'})
        dest_dir = os.path.dirname(dest_path)
        if dest_dir:
            os.makedirs(dest_dir, exist_ok=True)

        with self._urlopen_with_policy(req, timeout=connect_timeout, url=url) as resp:
            total_size = resp.headers.get('Content-Length')
            try:
                total_size = int(total_size) if total_size else -1
            except Exception:
                total_size = -1

            downloaded = 0
            block_num = 0
            block_size = 64 * 1024
            last_data_ts = time.time()

            with open(dest_path, 'wb') as f:
                while True:
                    if allow_cancel and self.cancel_event.is_set():
                        raise Exception("Update cancelled by user")

                    try:
                        chunk = resp.read(block_size)
                    except socket.timeout:
                        raise Exception("Download stall timeout")

                    now = time.time()
                    if not chunk:
                        if now - last_data_ts > stall_timeout:
                            raise Exception("Download stall timeout")
                        break

                    f.write(chunk)
                    downloaded += len(chunk)
                    block_num += 1
                    last_data_ts = now

                    if progress_cb:
                        progress_cb(block_num, block_size, total_size if total_size > 0 else downloaded)

    def _download_with_cancel(self, url, dest_path, progress_cb=None, connect_timeout=8, stall_timeout=15):
        self._download_url_to_path(
            url,
            dest_path,
            progress_cb=progress_cb,
            connect_timeout=connect_timeout,
            stall_timeout=stall_timeout,
            allow_cancel=True,
        )

    def _probe_resume_feasibility(self, url, connect_timeout=8):
        result = {
            "ok": False,
            "range_supported": False,
            "remote_size": None,
            "etag": None,
            "last_modified": None,
            "content_encoding": None,
            "via": "none",
            "status": None,
            "reasons": []
        }

        def add_reason(code, msg):
            result["reasons"].append({"code": code, "msg": msg})

        # 1) HEAD probe
        try:
            req = urllib.request.Request(url, method='HEAD', headers={'User-Agent': 'TCYClientUpdater/1.0'})
            with self._urlopen_with_policy(req, timeout=connect_timeout, url=url) as resp:
                headers = resp.headers
                result["status"] = getattr(resp, 'status', None)
                result["via"] = "HEAD"

                content_len = headers.get('Content-Length')
                if content_len and str(content_len).isdigit():
                    result["remote_size"] = int(content_len)
                else:
                    add_reason("NO_CONTENT_LENGTH", "HEAD 未返回有效 Content-Length")

                accept_ranges = (headers.get('Accept-Ranges') or '').lower()
                if 'bytes' in accept_ranges:
                    result["range_supported"] = True
                else:
                    add_reason("NO_ACCEPT_RANGES", "HEAD 未声明 Accept-Ranges: bytes")

                result["etag"] = headers.get('ETag')
                result["last_modified"] = headers.get('Last-Modified')
                result["content_encoding"] = headers.get('Content-Encoding')
        except Exception as e:
            add_reason("HEAD_FAILED", f"HEAD 探测失败: {e}")

        # 2) Range GET probe if needed
        if not result["range_supported"]:
            try:
                req = urllib.request.Request(
                    url,
                    headers={
                        'User-Agent': 'TCYClientUpdater/1.0',
                        'Range': 'bytes=0-0'
                    }
                )
                with self._urlopen_with_policy(req, timeout=connect_timeout, url=url) as resp:
                    result["status"] = getattr(resp, 'status', None)
                    result["via"] = "RANGE_GET"
                    content_range = resp.headers.get('Content-Range', '')
                    if result["status"] == 206 and content_range.startswith('bytes 0-0/'):
                        result["range_supported"] = True
                        try:
                            total = int(content_range.split('/')[-1])
                            result["remote_size"] = total
                        except Exception:
                            add_reason("BAD_CONTENT_RANGE", f"Content-Range 无法解析: {content_range}")
                    else:
                        add_reason("RANGE_NOT_SUPPORTED", f"Range 探测未返回 206，状态={result['status']}")

                    if not result["etag"]:
                        result["etag"] = resp.headers.get('ETag')
                    if not result["last_modified"]:
                        result["last_modified"] = resp.headers.get('Last-Modified')
                    if not result["content_encoding"]:
                        result["content_encoding"] = resp.headers.get('Content-Encoding')
            except Exception as e:
                add_reason("RANGE_PROBE_FAILED", f"Range 探测失败: {e}")

        result["ok"] = bool(result["range_supported"] and isinstance(result["remote_size"], int) and result["remote_size"] > 0)
        return result

    def _evaluate_resume_for_path(self, url, dest_path):
        local_size = os.path.getsize(dest_path) if os.path.exists(dest_path) else 0
        probe = self._probe_resume_feasibility(url)

        decision = {
            "resume_enabled": False,
            "local_size": local_size,
            "remote_size": probe.get("remote_size"),
            "etag": probe.get("etag"),
            "last_modified": probe.get("last_modified"),
            "reasons": list(probe.get("reasons", [])),
            "probe": probe
        }

        if local_size <= 0:
            decision["reasons"].append({"code": "NO_LOCAL_PARTIAL", "msg": "本地无可续传分片"})
            return decision

        if not probe.get("ok"):
            decision["reasons"].append({"code": "PROBE_NOT_OK", "msg": "远端续传探测不满足"})
            return decision

        remote_size = probe.get("remote_size")
        if not isinstance(remote_size, int) or remote_size <= 0:
            decision["reasons"].append({"code": "BAD_REMOTE_SIZE", "msg": "远端大小无效"})
            return decision

        if local_size >= remote_size:
            decision["reasons"].append({"code": "LOCAL_TOO_LARGE", "msg": "本地文件不小于远端，禁用续传"})
            return decision

        if not (probe.get("etag") or probe.get("last_modified")):
            decision["reasons"].append({"code": "NO_REMOTE_VALIDATOR", "msg": "远端缺少 ETag/Last-Modified"})
            return decision

        content_encoding = (probe.get("content_encoding") or '').lower()
        if content_encoding and content_encoding not in ('identity',):
            decision["reasons"].append({"code": "UNSAFE_ENCODING", "msg": f"不安全 Content-Encoding: {content_encoding}"})
            return decision

        decision["resume_enabled"] = True
        return decision

    def _run_command_capture(self, command, shell=False):
        try:
            kwargs = {
                "capture_output": True,
                "text": True,
                "encoding": 'utf-8',
                "errors": 'ignore',
                "shell": shell,
                "timeout": 5,
            }
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                kwargs["startupinfo"] = startupinfo
                kwargs["creationflags"] = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
            result = subprocess.run(
                command,
                **kwargs
            )
            return {
                "ok": True,
                "returncode": result.returncode,
                "stdout": (result.stdout or '').strip(),
                "stderr": (result.stderr or '').strip(),
            }
        except Exception as e:
            return {"ok": False, "error": str(e), "stdout": "", "stderr": ""}

    def _parse_java_version_number(self, text):
        if not text:
            return None
        m = re.search(r'version\s+"([^"]+)"', text)
        version = m.group(1) if m else None
        if not version:
            m = re.search(r'\b((?:1\.)?\d+(?:\.\d+){0,3})\b', text)
            version = m.group(1) if m else None
        if not version:
            return None
        if version.startswith('1.'):
            parts = version.split('.')
            if len(parts) >= 2 and parts[1].isdigit():
                return int(parts[1])
            return None
        major = version.split('.')[0]
        return int(major) if major.isdigit() else None

    def _extract_java_version_label(self, text):
        if not text:
            return "未知"
        m = re.search(r'version\s+"([^"]+)"', text)
        if m:
            return m.group(1)
        m = re.search(r'\b((?:1\.)?\d+(?:\.\d+){0,3})\b', text)
        return m.group(1) if m else "未知"

    def _detect_java_candidates(self):
        candidates = []
        seen = set()

        def add_candidate(path, source):
            if not path:
                return
            norm = os.path.normpath(path)
            key = norm.lower()
            if key in seen:
                return
            seen.add(key)
            candidates.append({"path": norm, "source": source})

        if os.name == 'nt' and winreg:
            reg_roots = [
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\JavaSoft"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\JavaSoft"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Eclipse Adoptium"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\JDK"),
            ]
            for hive, base_key in reg_roots:
                try:
                    with winreg.OpenKey(hive, base_key) as root:
                        sub_count = winreg.QueryInfoKey(root)[0]
                        for i in range(sub_count):
                            try:
                                sub_name = winreg.EnumKey(root, i)
                                with winreg.OpenKey(root, sub_name) as sub_key:
                                    try:
                                        java_home = winreg.QueryValueEx(sub_key, 'JavaHome')[0]
                                    except Exception:
                                        java_home = ''
                                    if java_home:
                                        java_bin = os.path.join(java_home, 'bin', 'java.exe')
                                        if os.path.exists(java_bin):
                                            add_candidate(java_bin, f'registry:{base_key}\\{sub_name}')
                            except Exception:
                                pass
                except Exception:
                    pass

        cmd_name = 'where' if os.name == 'nt' else 'which'
        cmd_res = self._run_command_capture([cmd_name, 'java'])
        if cmd_res.get("ok"):
            combined = '\n'.join([cmd_res.get('stdout', ''), cmd_res.get('stderr', '')])
            for line in combined.splitlines():
                line = line.strip()
                if line and os.path.exists(line):
                    add_candidate(line, f'{cmd_name} java')

        env_java_home = os.environ.get('JAVA_HOME', '').strip()
        if env_java_home:
            java_bin = os.path.join(env_java_home, 'bin', 'java.exe' if os.name == 'nt' else 'java')
            if os.path.exists(java_bin):
                add_candidate(java_bin, 'JAVA_HOME')

        common_dirs = []
        if os.name == 'nt':
            common_dirs.extend([
                r'C:\Program Files\Java',
                r'C:\Program Files\Eclipse Adoptium',
                r'C:\Program Files\Microsoft',
                r'C:\Program Files\GraalVM',
                r'C:\Program Files\BellSoft',
                r'C:\Program Files (x86)\Java',
            ])
        else:
            common_dirs.extend(['/usr/bin', '/usr/local/bin', '/usr/lib/jvm', '/opt', '/Library/Java/JavaVirtualMachines'])

        for base in common_dirs:
            if not os.path.exists(base):
                continue
            if os.path.isfile(base):
                if os.path.basename(base).startswith('java'):
                    add_candidate(base, 'common_path')
                continue
            try:
                for name in os.listdir(base):
                    full = os.path.join(base, name)
                    if os.path.isdir(full):
                        bin_java = os.path.join(full, 'bin', 'java.exe' if os.name == 'nt' else 'java')
                        if os.path.exists(bin_java):
                            add_candidate(bin_java, 'common_path')
                    elif name.lower().startswith('java'):
                        add_candidate(full, 'common_path')
            except Exception:
                pass

        return candidates

    def detect_java_versions(self):
        try:
            versions = []
            for item in self._detect_java_candidates():
                probe = self._run_command_capture([item['path'], '-version'])
                raw = '\n'.join([probe.get('stderr', ''), probe.get('stdout', '')]).strip()
                version_label = self._extract_java_version_label(raw)
                major = self._parse_java_version_number(raw)
                path_lower = item['path'].lower()
                is_graal = 'graal' in raw.lower() or 'graal' in path_lower
                arch = '64-bit' if any(k in raw.lower() for k in ['64-bit', 'x86_64', 'amd64']) else '未知'
                versions.append({
                    "path": item['path'],
                    "source": item['source'],
                    "version": version_label,
                    "major": major,
                    "arch": arch,
                    "is_graalvm": is_graal,
                    "runtime": raw.splitlines()[0] if raw else '未知'
                })

            versions.sort(key=lambda x: ((x.get('major') or 0), x.get('is_graalvm', False)), reverse=True)
            return {"success": True, "data": versions}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_system_memory_info(self):
        try:
            total_bytes = 0
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
                total_bytes = int(stat.ullTotalPhys)
            else:
                page_size = os.sysconf('SC_PAGE_SIZE')
                phys_pages = os.sysconf('SC_PHYS_PAGES')
                total_bytes = int(page_size * phys_pages)
            total_gb = round(total_bytes / (1024 ** 3), 1)
            return {"success": True, "data": {"total_bytes": total_bytes, "total_gb": total_gb}}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _extract_jvm_args_from_text(self, text):
        if not text:
            return ''
        patterns = [
            r'(-Xms\S+.*?-Xmx\S+[^\n\r]*)',
            r'((?:-Xms\S+| -Xms\S+|^)(?:.*?)(?:-XX:[^\n\r]+))',
            r'(java(?:w)?\.exe?\s+[^\n\r]*?(?:-Xmx\S+| -Xmx\S+)[^\n\r]*)',
        ]
        for pattern in patterns:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                return ' '.join(m.group(1).split())
        return ''

    def _get_launcher_config_paths(self):
        user_home = os.path.expanduser('~')
        paths = [
            os.path.join(user_home, '.hmcl', 'hmcl.json'),
            os.path.join(user_home, '.hmcl', 'hmcl.json5'),
            os.path.join(user_home, '.minecraft', 'PCL', 'Setup.ini'),
            os.path.join(user_home, '.minecraft', 'PCL', 'PCL.ini'),
            os.path.join(current_dir, 'hmcl.json'),
            os.path.join(current_dir, 'PCL', 'Setup.ini'),
        ]
        appdata = os.environ.get('APPDATA', '')
        if appdata:
            paths.extend([
                os.path.join(appdata, '.minecraft', 'PCL', 'Setup.ini'),
                os.path.join(appdata, '.minecraft', 'PCL', 'PCL.ini'),
                os.path.join(appdata, 'HMCL', 'hmcl.json'),
            ])

        result = []
        seen = set()
        for path in paths:
            norm = os.path.normpath(path)
            if norm.lower() in seen or not os.path.exists(norm):
                continue
            seen.add(norm.lower())
            result.append(norm)
        return result

    def _normalize_java_binary_path(self, path):
        raw = str(path or '').strip().strip('"').strip("'")
        if not raw:
            return ''
        norm = os.path.normpath(raw.replace('\\\\', '\\'))
        lower = norm.lower()
        if lower.endswith('javaw.exe'):
            alt = norm[:-len('javaw.exe')] + 'java.exe'
            if os.path.exists(alt):
                return os.path.normpath(alt)
        return norm

    def _extract_java_binary_from_text(self, text):
        if not text:
            return ''
        patterns = [
            r'([A-Za-z]:\\\\[^"\r\n]+?javaw?\.exe)',
            r'([A-Za-z]:\\[^"\r\n]+?javaw?\.exe)',
            r'((?:/[^\s"\']+)+/java)',
        ]
        for pattern in patterns:
            m = re.search(pattern, text, re.IGNORECASE)
            if not m:
                continue
            candidate = self._normalize_java_binary_path(m.group(1))
            if candidate and os.path.exists(candidate):
                return candidate
        return ''

    def _detect_launcher_java_selection(self):
        for norm in self._get_launcher_config_paths():
            try:
                with open(norm, 'r', encoding='utf-8', errors='ignore') as f:
                    text = f.read()
                java_path = self._extract_java_binary_from_text(text)
                if java_path:
                    launcher = 'HMCL' if 'hmcl' in norm.lower() else 'PCL' if 'pcl' in norm.lower() else '未知启动器'
                    return {
                        'launcher': launcher,
                        'config_path': norm,
                        'java_path': java_path,
                    }
            except Exception:
                pass
        return None

    def _detect_launcher_jvm_configs(self):
        candidates = []
        for norm in self._get_launcher_config_paths():
            try:
                with open(norm, 'r', encoding='utf-8', errors='ignore') as f:
                    text = f.read()
                args = self._extract_jvm_args_from_text(text)
                if args:
                    launcher = 'HMCL' if 'hmcl' in norm.lower() else 'PCL' if 'pcl' in norm.lower() else '未知启动器'
                    candidates.append({
                        'launcher': launcher,
                        'path': norm,
                        'args': args,
                    })
            except Exception:
                pass
        return candidates

    def get_launcher_jvm_profiles(self):
        try:
            return {"success": True, "data": self._detect_launcher_jvm_configs()}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_jvm_recommendations(self, profile="medium"):
        try:
            raw_settings = profile
            if isinstance(profile, str):
                text = profile.strip()
                if text.startswith('{'):
                    try:
                        raw_settings = json.loads(text)
                    except Exception:
                        raw_settings = {"profile": profile}
                else:
                    raw_settings = {"profile": profile}
            elif not isinstance(profile, dict):
                raw_settings = {"profile": "medium"}

            settings = normalize_jvm_advisor_settings(raw_settings)
            mem_info = self.get_system_memory_info()
            total_gb = 0
            if mem_info.get('success'):
                total_gb = mem_info['data'].get('total_gb', 0)

            detected_java = self.detect_java_versions()
            detected_versions = detected_java.get('data', []) if detected_java.get('success') else []
            data = build_jvm_recommendation(settings, total_gb, detected_versions)
            data["java_versions"] = JAVA_VERSION_NOTES
            return {"success": True, "data": data}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_system_overview(self):
        try:
            os_name = str(platform.system() or "Windows")
            os_version = str(platform.release() or platform.version() or "未知版本")

            memory_info = self.get_system_memory_info()
            total_gb = None
            if isinstance(memory_info, dict) and memory_info.get('success'):
                total_gb = memory_info.get('data', {}).get('total_gb')

            available_gb = get_available_memory_gb()
            disk_info = get_disk_usage_for_path(self.game_root)
            cpu_name = get_windows_cpu_name()
            cpu_threads = os.cpu_count() or 0

            java_versions = []
            try:
                java_res = self.detect_java_versions()
                if isinstance(java_res, dict) and java_res.get('success'):
                    java_versions = java_res.get('data', []) or []
            except Exception:
                java_versions = []
            selected_java = self._detect_launcher_java_selection()
            java_summary = summarize_java_versions(java_versions, selected_java)

            mods_enabled = 0
            mods_disabled = 0
            try:
                mods = self.get_mods_metadata()
                if isinstance(mods, list):
                    mods_enabled = sum(1 for item in mods if item.get('enabled'))
                    mods_disabled = sum(1 for item in mods if not item.get('enabled'))
            except Exception:
                pass

            save_count = 0
            try:
                saves_dir = self._get_saves_dir()
                if os.path.exists(saves_dir):
                    for entry in os.listdir(saves_dir):
                        world_path = os.path.join(saves_dir, entry)
                        if os.path.isdir(world_path) and os.path.exists(os.path.join(world_path, "level.dat")):
                            save_count += 1
            except Exception:
                pass

            screenshot_count = 0
            try:
                screenshot_dir = self._get_screenshots_dir()
                if os.path.exists(screenshot_dir):
                    valid_ext = {'.png', '.jpg', '.jpeg', '.bmp', '.webp'}
                    for filename in os.listdir(screenshot_dir):
                        full_path = os.path.join(screenshot_dir, filename)
                        if os.path.isfile(full_path) and os.path.splitext(filename)[1].lower() in valid_ext:
                            screenshot_count += 1
            except Exception:
                pass

            payload = build_system_overview(
                {
                    "os_name": os_name,
                    "os_version": os_version,
                    "cpu_name": cpu_name,
                    "cpu_threads": cpu_threads,
                    "ram_total_gb": total_gb,
                    "ram_available_gb": available_gb,
                    "disk_total_gb": disk_info.get("total_gb"),
                    "disk_free_gb": disk_info.get("free_gb"),
                },
                {
                    "game_root": self.game_root,
                    "local_version": self.get_local_version(),
                    "java_count": java_summary.get("java_count"),
                    "current_java_label": java_summary.get("current_java_label"),
                    "current_java_note": java_summary.get("current_java_note"),
                    "mods_enabled": mods_enabled,
                    "mods_disabled": mods_disabled,
                    "save_count": save_count,
                    "screenshot_count": screenshot_count,
                }
            )
            return {"success": True, "data": payload}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _download_with_resume(self, url, dest_path, local_size, remote_size, progress_cb=None, connect_timeout=8, stall_timeout=15):
        req = urllib.request.Request(
            url,
            headers={
                'User-Agent': 'TCYClientUpdater/1.0',
                'Range': f'bytes={local_size}-'
            }
        )

        with self._urlopen_with_policy(req, timeout=connect_timeout, url=url) as resp:
            status = getattr(resp, 'status', None)
            content_range = resp.headers.get('Content-Range', '')
            if status != 206 or f'bytes {local_size}-' not in content_range:
                raise Exception(f"Resume rejected by server: status={status}, content-range={content_range}")

            block_num = max(1, local_size // (64 * 1024))
            block_size = 64 * 1024
            downloaded = local_size
            last_data_ts = time.time()

            with open(dest_path, 'ab') as f:
                while True:
                    if self.cancel_event.is_set():
                        raise Exception("Update cancelled by user")
                    try:
                        chunk = resp.read(block_size)
                    except socket.timeout:
                        raise Exception("Resume stall timeout")

                    now = time.time()
                    if not chunk:
                        if now - last_data_ts > stall_timeout:
                            raise Exception("Resume stall timeout")
                        break

                    f.write(chunk)
                    downloaded += len(chunk)
                    block_num += 1
                    last_data_ts = now

                    if progress_cb:
                        progress_cb(block_num, block_size, remote_size)

    def _download_with_candidates_resumable(self, candidates, dest_path, progress_cb=None, connect_timeout=8, stall_timeout=15, log_context=None):
        last_error = None
        context_name = log_context or os.path.basename(dest_path)

        for idx, c_url in enumerate(candidates, start=1):
            if self.cancel_event.is_set():
                raise Exception("Update cancelled by user")

            try:
                self.log(f"[{context_name}] 评估续传能力 {idx}/{len(candidates)}: {c_url}")
                self.log(f"[{context_name}] 当前下载地址: {c_url}")
                decision = self._evaluate_resume_for_path(c_url, dest_path)

                try:
                    self._add_activity_log("resume_probe_result", {
                        "context": context_name,
                        "url": c_url,
                        "resume_enabled": decision.get("resume_enabled"),
                        "local_size": decision.get("local_size"),
                        "remote_size": decision.get("remote_size"),
                        "reasons": decision.get("reasons", [])
                    })
                except Exception:
                    pass

                if decision.get("resume_enabled"):
                    self.log(f"[{context_name}] 续传已启用: local={decision['local_size']} remote={decision['remote_size']}")
                    self._download_with_resume(
                        c_url,
                        dest_path,
                        decision['local_size'],
                        decision['remote_size'],
                        progress_cb=progress_cb,
                        connect_timeout=connect_timeout,
                        stall_timeout=stall_timeout
                    )
                    return c_url

                reason_items = decision.get('reasons', [])
                reasons = '; '.join([f"{r.get('code', 'UNKNOWN')}({r.get('msg', '')})" for r in reason_items]) or 'UNKNOWN'
                self.log(f"[{context_name}] 续传不可用，回退全量下载: {reasons}")
                self._download_with_cancel(
                    c_url,
                    dest_path,
                    progress_cb=progress_cb,
                    connect_timeout=connect_timeout,
                    stall_timeout=stall_timeout
                )
                return c_url

            except Exception as e:
                if self.cancel_event.is_set() or "cancelled" in str(e).lower():
                    raise
                last_error = e
                self.log(f"[{context_name}] 下载失败: {c_url} -> {e}")
                try:
                    self._add_activity_log("resume_fallback_full_download", {
                        "context": context_name,
                        "url": c_url,
                        "error": str(e)
                    })
                except Exception:
                    pass
                if os.path.exists(dest_path):
                    try:
                        os.remove(dest_path)
                    except Exception:
                        pass
                continue

        if last_error:
            raise last_error
        raise Exception("没有可用的下载源")

    def min_window(self):
        if global_window: global_window.minimize()
    def max_window(self):
        if global_window: global_window.toggle_fullscreen()
    def enter_fullscreen(self):
        """进入系统级全屏"""
        if global_window: global_window.toggle_fullscreen()
    def exit_fullscreen(self):
        """退出系统级全屏"""
        if global_window: global_window.toggle_fullscreen()
    def close_window(self):
        if global_window: global_window.destroy()

    def mark_ready(self):
        threading.Thread(target=self.init_app).start()

    # === ✅【新增】安全获取窗口句柄的辅助函数 ===
    def _get_hwnd(self):
        if not global_window: return 0
        try:
            h = global_window.native.Handle
            # 关键修复：检查是否为 C# 的 IntPtr 对象
            if hasattr(h, 'ToInt32'):
                return h.ToInt32()
            return int(h)
        except Exception:
            return 0

    # === 获取屏幕缩放比例 (增强版) ===
    def _get_dpi_scale(self):
        try:
            hwnd = self._get_hwnd() # ✅ 使用修复后的方法获取句柄
            if hwnd == 0: return 1.0
            
            # 尝试获取精准的窗口 DPI
            try:
                # Windows 10 1607+
                dpi = windll.user32.GetDpiForWindow(hwnd)
                return dpi / 96.0
            except AttributeError:
                # Windows 7/8 或旧版 Win10
                hdc = windll.user32.GetDC(hwnd)
                dpi = windll.gdi32.GetDeviceCaps(hdc, 88) # 88 = LOGPIXELSX
                windll.user32.ReleaseDC(hwnd, hdc)
                return dpi / 96.0
        except Exception as e:
            print(f"DPI detect error: {e}")
            return 1.0 # 默认不缩放

    # === ✅【终极修正】调整窗口大小接口 ===
    def set_window_size(self, width, height):
        if not global_window: return
        try:
            # 1. 解析目标逻辑大小
            target_w_logical = int(width)
            target_h_logical = int(height)
            
            # 2. 获取当前 DPI 缩放
            scale = self._get_dpi_scale()
            
            # 3. 计算物理像素 (Physical Pixels)
            # 这是传给 Windows API 的真实值
            final_w_physical = int(target_w_logical * scale)
            final_h_physical = int(target_h_logical * scale)
            
            # 4. 直接调用 Windows API 设置大小
            hwnd = self._get_hwnd() # ✅ 使用修复后的方法获取句柄
            
            if hwnd > 0:
                # SetWindowPos(hwnd, hWndInsertAfter, x, y, cx, cy, uFlags)
                # SWP_NOMOVE (0x0002) | SWP_NOZORDER (0x0004) | SWP_NOACTIVATE (0x0010)
                windll.user32.SetWindowPos(
                    hwnd, 0, 
                    0, 0,  # 忽略 x, y
                    final_w_physical, final_h_physical, 
                    0x0002 | 0x0004 | 0x0010
                )
            
            # 5. 保存配置 (保存逻辑值！)
            self.cfg_mgr.config['window_size'] = f"{target_w_logical}x{target_h_logical}"
            self.cfg_mgr.save_config(self.cfg_mgr.config)
            
            self.log(f"窗口大小已调整: {target_w_logical}x{target_h_logical} (缩放: {scale})")

        except Exception as e:
            self.log(f"调整窗口大小失败: {e}")
            traceback.print_exc() # 打印详细报错到控制台以便排查
    
    def init_app(self):
        try:
            cfg = self.cfg_mgr.config
            current_bg = DEFAULT_BG_B64 if cfg['bg_type'] == 'default' else cfg['custom_bg_data']
            # 这里虽然是探测 .minecraft/versions，但 UI 显示的路径会基于 find_game_root 的结果
            target_path = os.path.join(self.game_root, ".minecraft", "versions", TARGET_VERSION_NAME)
            if not os.path.exists(target_path):
                 target_path = os.path.join(self.game_root, "versions", TARGET_VERSION_NAME)

            init_data = {
                "versionName": TARGET_VERSION_NAME, "bgImage": current_bg,
                "settings": cfg, "detectedPath": target_path if os.path.exists(target_path) else "",
                "localVersion": self.get_local_version(),
                "launcherVersion": LAUNCHER_INTERNAL_VERSION,
                "mirrorCatalog": MIRROR_CATALOG,
                "defaultMirrorPrefix": DEFAULT_MIRROR_PREFIX,
            }
            if global_window: global_window.evaluate_js(f"initApp({json.dumps(init_data)})")

            # ===启动时自动触发检查更新（静默模式，使用顶部悬浮提示）===
            self.check_online_update(startup_mode=True)
            
        except Exception: pass

    def find_game_root(self):
        # 强制返回当前运行目录，不做任何智能探测，防止误判为 .minecraft 内部
        return os.path.abspath(current_dir)
    
     # ===启动时的目录严格校验 ===
    def check_game_directory_exists(self):
        """
        启动时目录校验（与 check_path 保持一致）：
        兼容 Launcher/.minecraft/versions 或 Launcher/versions 两种结构
        """
        p1 = os.path.join(self.game_root, ".minecraft", "versions", TARGET_VERSION_NAME)
        p2 = os.path.join(self.game_root, "versions", TARGET_VERSION_NAME)

        print(f"[Init Check] 正在校验目录结构: {os.path.abspath(p1)}")
        print(f"[Init Check] 备用目录校验: {os.path.abspath(p2)}")

        ok = os.path.exists(p1) or os.path.exists(p2)
        if ok:
            print("[Init Check] 目录校验通过！成功找到异界战斗幻想版本文件夹。")
        else:
            print("[Init Check] 目录校验失败！未找到异界战斗幻想文件夹。请检查更新器是否放对位置?找糖醋鱼反馈!")
        return ok

    def check_path(self):
        # 兼容两种结构： Launcher/.minecraft/versions 或 Launcher/versions
        p1 = os.path.join(self.game_root, ".minecraft", "versions", TARGET_VERSION_NAME)
        p2 = os.path.join(self.game_root, "versions", TARGET_VERSION_NAME)
        return os.path.exists(p1) or os.path.exists(p2)

    def log(self, msg):
        log_info(f"[GUI Log] {msg}")
        if global_window:
            safe_msg = msg.replace("'", '"').replace("\n", " ")
            try: global_window.evaluate_js(f"addLog('{safe_msg}')")
            except: pass

    def _add_activity_log(self, event_type, details):
        """添加一条操作日志记录（持久化到配置文件）"""
        entry = {
            "timestamp": time.strftime('%Y-%m-%d %H:%M:%S'),
            "type": event_type,
            "details": details
        }
        try:
            cfg = self.cfg_mgr.load_config()
            log_list = cfg.get("activity_log", [])
            log_list.append(entry)
            # 保留最近 200 条记录，防止 JSON 膨胀
            if len(log_list) > 200:
                log_list = log_list[-200:]
            self.cfg_mgr.save_config({"activity_log": log_list})
        except Exception:
            pass

    def _get_game_version_dir(self):
        """获取游戏版本目录的绝对路径"""
        p1 = os.path.join(self.game_root, ".minecraft", "versions", TARGET_VERSION_NAME)
        if os.path.exists(p1): return p1
        p2 = os.path.join(self.game_root, "versions", TARGET_VERSION_NAME)
        if os.path.exists(p2): return p2
        return p1

    def _resolve_game_relative_path(self, sub_path, relative_path):
        return resolve_relative_path(self._get_game_subdir(sub_path), relative_path)

    def _get_screenshots_dir(self):
        """获取截图目录的绝对路径"""
        version_dir = self._get_game_version_dir()
        return os.path.join(version_dir, "screenshots")

    def _get_thumbnail_cache_dir(self):
        """获取截图缩略图缓存目录（位于更新器同级）"""
        cache_dir = os.path.join(self.game_root, "thumbnail_cache", "screenshots", "thumbs")
        os.makedirs(cache_dir, exist_ok=True)
        return cache_dir

    def _build_image_cache_key(self, source_path, stat_obj, variant):
        raw = f"{variant}|{os.path.abspath(source_path)}|{getattr(stat_obj, 'st_size', 0)}|{getattr(stat_obj, 'st_mtime_ns', 0)}"
        return hashlib.sha1(raw.encode('utf-8', errors='ignore')).hexdigest()

    def _build_thumbnail_cache_key(self, source_path, stat_obj):
        return self._build_image_cache_key(source_path, stat_obj, 'thumb')

    def _get_image_cache_path(self, source_path, stat_obj, variant):
        cache_key = self._build_image_cache_key(source_path, stat_obj, variant)
        cache_dir = self._get_thumbnail_cache_dir()
        return os.path.join(cache_dir, f"{cache_key}.jpg"), cache_key

    def _get_thumbnail_cache_path(self, source_path, stat_obj):
        cache_key = self._build_thumbnail_cache_key(source_path, stat_obj)
        return os.path.join(self._get_thumbnail_cache_dir(), f"{cache_key}.jpg"), cache_key

    def _path_to_file_url(self, path, version_token=None):
        file_url = Path(path).resolve().as_uri()
        if version_token is not None:
            file_url += f"?v={version_token}"
        return file_url

    def _get_screenshot_valid_cache_names(self):
        screenshots_dir = self._get_screenshots_dir()
        valid_names = {"thumb": set()}
        if os.path.exists(screenshots_dir):
            allowed_exts = {'.png', '.jpg', '.jpeg', '.webp'}
            for filename in os.listdir(screenshots_dir):
                full_path = os.path.join(screenshots_dir, filename)
                if not os.path.isfile(full_path):
                    continue
                if os.path.splitext(filename)[1].lower() not in allowed_exts:
                    continue
                try:
                    stat_obj = os.stat(full_path)
                    _, cache_key = self._get_image_cache_path(full_path, stat_obj, 'thumb')
                    valid_names['thumb'].add(f"{cache_key}.jpg")
                except Exception:
                    continue
        return valid_names

    def get_screenshot_cache_stats(self, include_details=False):
        try:
            valid_names = self._get_screenshot_valid_cache_names()

            def stat_dir(cache_dir, variant):
                total_bytes = 0
                file_count = 0
                orphan_bytes = 0
                orphan_count = 0
                oldest = None
                newest = None
                details = []
                try:
                    for fn in os.listdir(cache_dir):
                        if not fn.lower().endswith('.jpg'):
                            continue
                        p = os.path.join(cache_dir, fn)
                        try:
                            st = os.stat(p)
                        except Exception:
                            continue
                        file_count += 1
                        total_bytes += st.st_size
                        mtime = st.st_mtime
                        oldest = mtime if oldest is None else min(oldest, mtime)
                        newest = mtime if newest is None else max(newest, mtime)
                        is_orphan = fn not in valid_names.get(variant, set())
                        if is_orphan:
                            orphan_count += 1
                            orphan_bytes += st.st_size
                        if include_details:
                            details.append({"name": fn, "bytes": st.st_size, "mtime": mtime, "orphan": is_orphan})
                except Exception:
                    pass
                if include_details:
                    details.sort(key=lambda x: x.get('bytes', 0), reverse=True)
                    details = details[:50]
                return {
                    "dir": cache_dir,
                    "file_count": file_count,
                    "total_bytes": total_bytes,
                    "orphan_count": orphan_count,
                    "orphan_bytes": orphan_bytes,
                    "oldest_mtime": oldest,
                    "newest_mtime": newest,
                    "details": details if include_details else None,
                }

            thumb_dir = self._get_thumbnail_cache_dir()

            # hit/miss based on current screenshots
            screenshots_dir = self._get_screenshots_dir()
            allowed_exts = {'.png', '.jpg', '.jpeg', '.webp'}
            hit_thumb = miss_thumb = 0
            try:
                for filename in os.listdir(screenshots_dir):
                    full_path = os.path.join(screenshots_dir, filename)
                    if not os.path.isfile(full_path):
                        continue
                    if os.path.splitext(filename)[1].lower() not in allowed_exts:
                        continue
                    try:
                        st = os.stat(full_path)
                        thumb_path, _ = self._get_image_cache_path(full_path, st, 'thumb')
                        hit_thumb += 1 if os.path.exists(thumb_path) else 0
                        miss_thumb += 0 if os.path.exists(thumb_path) else 1
                    except Exception:
                        continue
            except Exception:
                pass

            thumb_stats = stat_dir(thumb_dir, 'thumb')
            thumb_stats.update({"hit_count": hit_thumb, "miss_count": miss_thumb})

            return json.dumps({
                "success": True,
                "thumb": thumb_stats,
            }, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    def clear_screenshot_cache(self, variant="all", orphan_only=False):
        try:
            variant = str(variant or 'all').lower()
            orphan_only = bool(orphan_only)
            if variant not in ('all', 'thumb'):
                raise ValueError('variant 不合法')

            valid_names = self._get_screenshot_valid_cache_names() if orphan_only else {"thumb": set()}

            deleted_files = 0
            deleted_bytes = 0

            def clear_dir(cache_dir, v):
                nonlocal deleted_files, deleted_bytes
                try:
                    for fn in os.listdir(cache_dir):
                        if not fn.lower().endswith('.jpg'):
                            continue
                        if orphan_only and fn in valid_names.get(v, set()):
                            continue
                        p = os.path.join(cache_dir, fn)
                        meta_path = os.path.splitext(p)[0] + '.json'
                        try:
                            st = os.stat(p)
                        except Exception:
                            st = None
                        try:
                            os.remove(p)
                            if os.path.exists(meta_path):
                                try:
                                    os.remove(meta_path)
                                except Exception:
                                    pass
                            deleted_files += 1
                            if st:
                                deleted_bytes += st.st_size
                        except Exception:
                            pass
                except Exception:
                    pass

            with Api._screenshot_cache_lock:
                if variant in ('all', 'thumb'):
                    clear_dir(self._get_thumbnail_cache_dir(), 'thumb')
                    # Also clear legacy preview cache directory from older versions
                    legacy_preview_dir = os.path.join(self.game_root, "thumbnail_cache", "screenshots", "previews")
                    if os.path.isdir(legacy_preview_dir):
                        clear_dir(legacy_preview_dir, 'preview')
                # best-effort: clear inflight markers
                Api._screenshot_cache_inflight.clear()

            return json.dumps({
                "success": True,
                "deleted_files": deleted_files,
                "deleted_bytes": deleted_bytes,
            }, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    def get_screenshot_source_url(self, rel_path):
        try:
            abs_path = self._resolve_screenshot_path(rel_path)
            st = os.stat(abs_path)
            return json.dumps({
                "success": True,
                "source_url": self._path_to_file_url(abs_path, getattr(st, 'st_mtime_ns', 0)),
            }, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    def open_screenshot_with_default_app(self, rel_path):
        try:
            abs_path = self._resolve_screenshot_path(rel_path)
            if os.name == 'nt':
                os.startfile(abs_path)
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', abs_path])
            else:
                subprocess.Popen(['xdg-open', abs_path])
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def reveal_screenshot_in_folder(self, rel_path):
        try:
            abs_path = self._resolve_screenshot_path(rel_path)
            parent_dir = os.path.dirname(abs_path)
            if os.name == 'nt':
                os.startfile(parent_dir)
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', parent_dir])
            else:
                subprocess.Popen(['xdg-open', parent_dir])
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def store_screenshot_cache(self, rel_path, variant, data_url, width=None, height=None):
        try:
            variant = str(variant or '').lower()
            if variant not in ('thumb',):
                raise ValueError('variant 不合法')
            abs_path = self._resolve_screenshot_path(rel_path)
            st = os.stat(abs_path)
            cache_path, cache_key = self._get_image_cache_path(abs_path, st, variant)

            data_url = str(data_url or '')
            prefix = 'data:image/jpeg;base64,'
            if not data_url.startswith(prefix):
                raise ValueError('仅支持 JPEG data_url')
            b64 = data_url[len(prefix):]
            if not b64:
                raise ValueError('data_url 为空')
            # basic size guard (base64 is ~4/3)
            if len(b64) > (40 * 1024 * 1024):
                raise ValueError('data_url 过大')
            img_bytes = base64.b64decode(b64)
            if len(img_bytes) > (30 * 1024 * 1024):
                raise ValueError('图片字节过大')

            with Api._screenshot_cache_lock:
                os.makedirs(os.path.dirname(cache_path), exist_ok=True)
                tmp_path = cache_path + '.tmp'
                with open(tmp_path, 'wb') as f:
                    f.write(img_bytes)
                os.replace(tmp_path, cache_path)
                # Sidecar metadata: preserve original source dimensions so gallery can show true resolution
                try:
                    meta_path = os.path.splitext(cache_path)[0] + '.json'
                    meta = {
                        "variant": variant,
                        "source_width": int(width) if str(width).isdigit() or isinstance(width, int) else None,
                        "source_height": int(height) if str(height).isdigit() or isinstance(height, int) else None,
                        "saved_at": int(time.time())
                    }
                    with open(meta_path + '.tmp', 'w', encoding='utf-8') as mf:
                        json.dump(meta, mf, ensure_ascii=False)
                    os.replace(meta_path + '.tmp', meta_path)
                except Exception:
                    pass

            return json.dumps({
                "success": True,
                "variant": variant,
                "rel_path": rel_path,
                "cache_key": cache_key,
                "cache_path": cache_path,
                "cache_url": self._path_to_file_url(cache_path, getattr(st, 'st_mtime_ns', 0)),
                "width": width,
                "height": height,
            }, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    def _ensure_image_cached(self, abs_path, variant='thumb'):
        raise RuntimeError("当前构建不在后端生成截图缓存，请使用前端生成并调用 store_screenshot_cache")

    def _ensure_thumbnail_cached(self, abs_path, max_edge=320):
        raise RuntimeError("当前构建不在后端生成缩略图，请使用前端生成并调用 store_screenshot_cache")

    def _prewarm_screenshot_cache(self, rel_paths, variant='thumb', max_workers=3):
        # 缓存生成已迁移到前端（WebView2 原生解码 + Canvas 缩放），后端不再预热
        return

    def _schedule_initial_thumbnail_prewarm(self, items):
        # 后端不再预热；前端会按需批量请求并生成
        return

    def _resolve_screenshot_path(self, rel_path):
        rel_path = str(rel_path or "").replace("\\", "/").strip("/")
        if not rel_path or ".." in rel_path or os.path.isabs(rel_path):
            raise ValueError("非法截图路径")
        base_dir = os.path.abspath(self._get_screenshots_dir())
        abs_path = os.path.abspath(os.path.join(base_dir, rel_path))
        if not abs_path.startswith(base_dir + os.sep) and abs_path != base_dir:
            raise ValueError("截图路径越界")
        if not os.path.isfile(abs_path):
            raise FileNotFoundError("截图文件不存在")
        return abs_path

    def _format_size_label(self, size_bytes):
        size = float(size_bytes or 0)
        units = ["B", "KB", "MB", "GB"]
        idx = 0
        while size >= 1024 and idx < len(units) - 1:
            size /= 1024.0
            idx += 1
        if idx == 0:
            return f"{int(size)} {units[idx]}"
        return f"{size:.1f} {units[idx]}"

    def _jpeg_get_size_fast(self, path):
        try:
            with open(path, 'rb') as f:
                data = f.read(4096)
            if len(data) < 10 or data[0:2] != b'\xff\xd8':
                return None, None
            i = 2
            while i + 9 < len(data):
                if data[i] != 0xFF:
                    i += 1
                    continue
                marker = data[i + 1]
                # SOI/EOI have no length
                if marker in (0xD8, 0xD9):
                    i += 2
                    continue
                if i + 3 >= len(data):
                    break
                seg_len = (data[i + 2] << 8) + data[i + 3]
                if seg_len <= 0:
                    break
                if marker in (0xC0, 0xC2) and i + 8 < len(data):
                    h = (data[i + 5] << 8) + data[i + 6]
                    w = (data[i + 7] << 8) + data[i + 8]
                    return w, h
                i += 2 + seg_len
        except Exception:
            pass
        return None, None

    def _build_screenshot_item_from_path(self, base_dir, rel_path, full_path):
        stat = os.stat(full_path)
        width = height = None
        try:
            # 优先从 thumb sidecar 读取原图尺寸
            meta_path = os.path.splitext(self._get_image_cache_path(full_path, stat, 'thumb')[0])[0] + '.json'
            if os.path.exists(meta_path):
                try:
                    with open(meta_path, 'r', encoding='utf-8') as f:
                        meta = json.load(f)
                    mw = meta.get('source_width')
                    mh = meta.get('source_height')
                    if isinstance(mw, int) and isinstance(mh, int) and mw > 0 and mh > 0:
                        width, height = mw, mh
                except Exception:
                    width = height = None

            # 如果 sidecar 不存在或无效，直接从原图读取真实尺寸（前端/浏览器生成 thumb 之前也能拿到真值）
            if not width or not height:
                ext = os.path.splitext(full_path)[1].lower()
                if ext == '.png':
                    with open(full_path, 'rb') as f:
                        header = f.read(24)
                    if len(header) >= 24 and header[:8] == b'\x89PNG\r\n\x1a\n':
                        width = int.from_bytes(header[16:20], 'big')
                        height = int.from_bytes(header[20:24], 'big')
                elif ext in ('.jpg', '.jpeg'):
                    width, height = self._jpeg_get_size_fast(full_path)
                else:
                    # webp/其他格式：保持未知，等待前端首次生成 thumb 后回填真实尺寸 sidecar
                    width = height = None
        except Exception:
            width = height = None

        name = os.path.basename(rel_path)
        rel_norm = str(rel_path).replace('\\', '/').lstrip('/')
        return {
            "name": name,
            "rel_path": rel_norm,
            "size_bytes": stat.st_size,
            "size_label": self._format_size_label(stat.st_size),
            "mtime": stat.st_mtime,
            "mtime_ns": getattr(stat, 'st_mtime_ns', int(stat.st_mtime * 1_000_000_000)),
            "mtime_label": datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
            "width": width,
            "height": height,
            "resolution": f"{width}×{height}" if width and height else "未知",
            "ext": os.path.splitext(name)[1].lower(),
        }

    def _build_screenshot_item(self, base_dir, filename):
        full_path = os.path.join(base_dir, filename)
        return self._build_screenshot_item_from_path(base_dir, filename, full_path)

    def list_screenshots(self):
        try:
            base_dir = self._get_screenshots_dir()
            os.makedirs(base_dir, exist_ok=True)
            # 先清理无效缓存（孤儿文件）
            try:
                self.clear_screenshot_cache('all', orphan_only=True)
            except Exception:
                pass

            allowed_exts = {'.png', '.jpg', '.jpeg', '.webp'}
            items = []
            scanned_files = 0
            skipped_ext = 0
            failed_meta = 0
            failed_samples = []
            max_items = 10000

            for root, dirs, files in os.walk(base_dir):
                rel_root = os.path.relpath(root, base_dir)
                rel_root = '' if rel_root == '.' else rel_root
                for fn in files:
                    scanned_files += 1
                    if len(items) >= max_items:
                        break
                    ext = os.path.splitext(fn)[1].lower()
                    if ext not in allowed_exts:
                        skipped_ext += 1
                        continue
                    full_path = os.path.join(root, fn)
                    rel_path = os.path.join(rel_root, fn) if rel_root else fn
                    try:
                        items.append(self._build_screenshot_item_from_path(base_dir, rel_path, full_path))
                    except Exception as item_err:
                        failed_meta += 1
                        if len(failed_samples) < 8:
                            failed_samples.append({"rel_path": rel_path, "error": str(item_err)})
                        log_warning(f"截图元数据读取失败 {rel_path}: {item_err}")
                if len(items) >= max_items:
                    break

            items.sort(key=lambda x: x.get("mtime", 0), reverse=True)
            self._schedule_initial_thumbnail_prewarm(items)
            return json.dumps({
                "success": True,
                "thumbnail_engine": "webview2",
                "directory": base_dir,
                "cache_directory": self._get_thumbnail_cache_dir(),
                "scan": {
                    "scanned_files": scanned_files,
                    "skipped_ext": skipped_ext,
                    "failed_meta": failed_meta,
                    "failed_samples": failed_samples,
                    "items": len(items)
                },
                "items": items
            }, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    def get_screenshot_thumbnails(self, rel_paths_json):
        try:
            rel_paths = json.loads(rel_paths_json) if isinstance(rel_paths_json, str) else rel_paths_json
            if not isinstance(rel_paths, list):
                raise ValueError("缩略图请求参数格式错误")
            rel_batch = [rel for rel in rel_paths[:24] if rel]
            items = []
            for rel_path in rel_batch:
                try:
                    abs_path = self._resolve_screenshot_path(rel_path)
                    st = os.stat(abs_path)
                    cache_path, _ = self._get_image_cache_path(abs_path, st, 'thumb')
                    if os.path.exists(cache_path):
                        items.append({
                            "rel_path": rel_path,
                            "thumbnail_path": cache_path,
                            "thumbnail_url": self._path_to_file_url(cache_path, getattr(st, 'st_mtime_ns', 0)),
                            "cached": True,
                        })
                    else:
                        items.append({
                            "rel_path": rel_path,
                            "cached": False,
                        })
                except Exception as item_err:
                    items.append({"rel_path": rel_path, "error": str(item_err)})
            return json.dumps({"success": True, "items": items, "engine": "webview2"}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)



    def export_screenshots(self, rel_paths_json):
        try:
            rel_paths = json.loads(rel_paths_json) if isinstance(rel_paths_json, str) else rel_paths_json
            if not isinstance(rel_paths, list) or not rel_paths:
                return json.dumps({"success": False, "error": "未选择任何截图"}, ensure_ascii=False)
            if not global_window:
                return json.dumps({"success": False, "error": "窗口未就绪"}, ensure_ascii=False)
            target = global_window.create_file_dialog(webview.FOLDER_DIALOG)
            if not target:
                return json.dumps({"success": False, "error": "已取消导出"}, ensure_ascii=False)
            export_dir = target[0] if isinstance(target, (list, tuple)) else target
            os.makedirs(export_dir, exist_ok=True)
            exported = 0
            errors = []
            for rel_path in rel_paths:
                try:
                    abs_path = self._resolve_screenshot_path(rel_path)
                    rel_norm = str(rel_path or '').replace('\\', '/').strip('/')
                    rel_parts = [part for part in rel_norm.split('/') if part]
                    dest_path = os.path.join(export_dir, *rel_parts) if rel_parts else os.path.join(export_dir, os.path.basename(abs_path))
                    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                    if os.path.abspath(dest_path) == os.path.abspath(abs_path):
                        exported += 1
                        continue
                    shutil.copy2(abs_path, dest_path)
                    exported += 1
                except Exception as item_err:
                    errors.append({"rel_path": rel_path, "error": str(item_err)})
            return json.dumps({
                "success": exported > 0 and not errors,
                "partial": exported > 0 and bool(errors),
                "exported": exported,
                "failed": len(errors),
                "destination": export_dir,
                "errors": errors,
            }, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    def get_favorite_folders(self):
        try:
            cfg = self.cfg_mgr.load_config()
            folders = cfg.get('favorite_folders', [])
            last_id = cfg.get('favorite_last_folder_id', 'default')
            return json.dumps({"success": True, "folders": folders, "last_folder_id": last_id}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    def create_favorite_folder(self, name):
        try:
            name = str(name or '').strip()
            if not name:
                return json.dumps({"success": False, "error": "收藏夹名称不能为空"}, ensure_ascii=False)
            cfg = self.cfg_mgr.load_config()
            folders = cfg.get('favorite_folders', [])
            # prevent duplicate names
            if any(str(f.get('name','')) == name for f in folders):
                return json.dumps({"success": False, "error": "收藏夹名称已存在"}, ensure_ascii=False)
            folder_id = uuid.uuid4().hex[:10]
            folder = {"id": folder_id, "name": name, "created": time.strftime('%Y-%m-%d %H:%M:%S'), "items": []}
            folders.append(folder)
            self.cfg_mgr.save_config({"favorite_folders": folders, "favorite_last_folder_id": folder_id})
            self._add_activity_log("favorites_folder_create", {"id": folder_id, "name": name})
            return json.dumps({"success": True, "folder": folder}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    def rename_favorite_folder(self, folder_id, name):
        try:
            folder_id = str(folder_id or '').strip()
            name = str(name or '').strip()
            if not folder_id:
                return json.dumps({"success": False, "error": "folder_id 不能为空"}, ensure_ascii=False)
            if not name:
                return json.dumps({"success": False, "error": "收藏夹名称不能为空"}, ensure_ascii=False)
            cfg = self.cfg_mgr.load_config()
            folders = cfg.get('favorite_folders', [])
            if any(str(f.get('name','')) == name and str(f.get('id')) != folder_id for f in folders):
                return json.dumps({"success": False, "error": "收藏夹名称已存在"}, ensure_ascii=False)
            found = False
            for f in folders:
                if str(f.get('id')) == folder_id:
                    f['name'] = name
                    found = True
                    break
            if not found:
                return json.dumps({"success": False, "error": "收藏夹不存在"}, ensure_ascii=False)
            self.cfg_mgr.save_config({"favorite_folders": folders})
            self._add_activity_log("favorites_folder_rename", {"id": folder_id, "name": name})
            return json.dumps({"success": True}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    def delete_favorite_folder(self, folder_id):
        try:
            folder_id = str(folder_id or '').strip()
            if not folder_id:
                return json.dumps({"success": False, "error": "folder_id 不能为空"}, ensure_ascii=False)
            cfg = self.cfg_mgr.load_config()
            folders = cfg.get('favorite_folders', [])
            if folder_id == 'default':
                return json.dumps({"success": False, "error": "默认收藏夹不可删除"}, ensure_ascii=False)
            before = len(folders)
            folders = [f for f in folders if str(f.get('id')) != folder_id]
            if len(folders) == before:
                return json.dumps({"success": False, "error": "收藏夹不存在"}, ensure_ascii=False)
            last_id = cfg.get('favorite_last_folder_id', 'default')
            if last_id == folder_id:
                last_id = 'default'
            self.cfg_mgr.save_config({"favorite_folders": folders, "favorite_last_folder_id": last_id})
            self._add_activity_log("favorites_folder_delete", {"id": folder_id})
            return json.dumps({"success": True, "last_folder_id": last_id}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    def add_items_to_favorite_folder(self, folder_id, rel_paths_json):
        try:
            folder_id = str(folder_id or '').strip()
            rel_paths = json.loads(rel_paths_json) if isinstance(rel_paths_json, str) else rel_paths_json
            if not folder_id:
                return json.dumps({"success": False, "error": "folder_id 不能为空"}, ensure_ascii=False)
            if not isinstance(rel_paths, list) or not rel_paths:
                return json.dumps({"success": False, "error": "未选择任何图片"}, ensure_ascii=False)
            # validate all paths
            safe_paths = []
            for p in rel_paths:
                try:
                    p = str(p or '')
                    self._resolve_screenshot_path(p)
                    safe_paths.append(p)
                except Exception:
                    continue
            if not safe_paths:
                return json.dumps({"success": False, "error": "没有可加入的有效图片"}, ensure_ascii=False)

            cfg = self.cfg_mgr.load_config()
            folders = cfg.get('favorite_folders', [])
            target = None
            for f in folders:
                if str(f.get('id')) == folder_id:
                    target = f
                    break
            if not target:
                return json.dumps({"success": False, "error": "收藏夹不存在"}, ensure_ascii=False)
            items = target.get('items', [])
            if not isinstance(items, list):
                items = []
            before = len(items)
            for p in safe_paths:
                if p not in items:
                    items.append(p)
            target['items'] = items
            self.cfg_mgr.save_config({"favorite_folders": folders, "favorite_last_folder_id": folder_id})
            added = len(items) - before
            self._add_activity_log("favorites_add", {"folder_id": folder_id, "added": added})
            return json.dumps({"success": True, "added": added}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    def remove_items_from_favorite_folder(self, folder_id, rel_paths_json):
        try:
            folder_id = str(folder_id or '').strip()
            rel_paths = json.loads(rel_paths_json) if isinstance(rel_paths_json, str) else rel_paths_json
            if not folder_id:
                return json.dumps({"success": False, "error": "folder_id 不能为空"}, ensure_ascii=False)
            if not isinstance(rel_paths, list) or not rel_paths:
                return json.dumps({"success": False, "error": "未选择任何图片"}, ensure_ascii=False)
            rel_set = set(str(p or '') for p in rel_paths)

            cfg = self.cfg_mgr.load_config()
            folders = cfg.get('favorite_folders', [])
            target = None
            for f in folders:
                if str(f.get('id')) == folder_id:
                    target = f
                    break
            if not target:
                return json.dumps({"success": False, "error": "收藏夹不存在"}, ensure_ascii=False)
            items = target.get('items', [])
            if not isinstance(items, list):
                items = []
            before = len(items)
            items = [p for p in items if p not in rel_set]
            target['items'] = items
            self.cfg_mgr.save_config({"favorite_folders": folders})
            removed = before - len(items)
            self._add_activity_log("favorites_remove", {"folder_id": folder_id, "removed": removed})
            return json.dumps({"success": True, "removed": removed}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    def move_items_between_favorite_folders(self, source_folder_id, target_folder_id, rel_paths_json):
        try:
            source_folder_id = str(source_folder_id or '').strip()
            target_folder_id = str(target_folder_id or '').strip()
            rel_paths = json.loads(rel_paths_json) if isinstance(rel_paths_json, str) else rel_paths_json
            if not source_folder_id or not target_folder_id:
                return json.dumps({"success": False, "error": "收藏夹参数不合法"}, ensure_ascii=False)
            if source_folder_id == target_folder_id:
                return json.dumps({"success": False, "error": "源收藏夹和目标收藏夹不能相同"}, ensure_ascii=False)
            if not isinstance(rel_paths, list) or not rel_paths:
                return json.dumps({"success": False, "error": "未选择任何图片"}, ensure_ascii=False)

            rel_set = set(str(p or '') for p in rel_paths)
            cfg = self.cfg_mgr.load_config()
            folders = cfg.get('favorite_folders', [])
            src = next((f for f in folders if str(f.get('id')) == source_folder_id), None)
            dst = next((f for f in folders if str(f.get('id')) == target_folder_id), None)
            if not src or not dst:
                return json.dumps({"success": False, "error": "收藏夹不存在"}, ensure_ascii=False)

            src_items = src.get('items', []) if isinstance(src.get('items', []), list) else []
            dst_items = dst.get('items', []) if isinstance(dst.get('items', []), list) else []
            moving = [p for p in src_items if p in rel_set]
            if not moving:
                return json.dumps({"success": False, "error": "没有可移动的图片"}, ensure_ascii=False)

            src['items'] = [p for p in src_items if p not in rel_set]
            for p in moving:
                if p not in dst_items:
                    dst_items.append(p)
            dst['items'] = dst_items

            self.cfg_mgr.save_config({"favorite_folders": folders, "favorite_last_folder_id": target_folder_id})
            self._add_activity_log("favorites_move", {"source": source_folder_id, "target": target_folder_id, "count": len(moving)})
            return json.dumps({"success": True, "moved": len(moving)}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    def export_favorite_items(self, rel_paths_json):
        # reuse export_screenshots behavior
        return self.export_screenshots(rel_paths_json)


    def _verify_sha256(self, file_path, expected_hash):
        """校验文件 SHA256，返回 (是否匹配, 实际hash)"""
        sha256 = hashlib.sha256()
        try:
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(8192), b''):
                    sha256.update(chunk)
            actual = sha256.hexdigest()
            return actual == expected_hash.lower(), actual
        except Exception:
            return False, ""

    def _get_backup_root(self):
        """获取备份根目录"""
        return os.path.join(self._get_game_version_dir(), ".update_backups")

    def _create_backup(self, version, affected_paths):
        """备份受影响的文件。返回 backup_dir 路径，失败返回 None"""
        backup_root = self._get_backup_root()
        backup_dir = os.path.join(backup_root, f"backup_{version}_{int(time.time())}")
        os.makedirs(backup_dir, exist_ok=True)
        game_dir = self._get_game_version_dir()
        backed_up = []
        for abs_path in affected_paths:
            if os.path.exists(abs_path):
                try:
                    rel = os.path.relpath(abs_path, game_dir)
                except ValueError:
                    rel = os.path.basename(abs_path)
                dest = os.path.join(backup_dir, rel)
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                try:
                    shutil.copy2(abs_path, dest)
                    backed_up.append(rel)
                except Exception as e:
                    log_warning(f"备份文件失败 {rel}: {e}")
        manifest = {"version": version, "timestamp": time.time(), "files": backed_up}
        with open(os.path.join(backup_dir, "_backup_manifest.json"), 'w', encoding='utf-8') as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)
        self.log(f"已备份 {len(backed_up)} 个文件到 {os.path.basename(backup_dir)}")
        log_info(f"备份创建完成: {backup_dir}, 文件数: {len(backed_up)}")
        self._cleanup_old_backups()
        return backup_dir

    def _restore_backup(self, backup_dir):
        """从备份恢复文件"""
        game_dir = self._get_game_version_dir()
        backup_root = os.path.realpath(self._get_backup_root())
        backup_dir = os.path.realpath(backup_dir)
        try:
            if os.path.commonpath([backup_root, backup_dir]) != backup_root:
                self.log("备份目录非法，无法回滚")
                return False
        except ValueError:
            self.log("备份目录非法，无法回滚")
            return False

        manifest_path = os.path.join(backup_dir, "_backup_manifest.json")
        if not os.path.exists(manifest_path):
            self.log("备份清单不存在，无法回滚")
            return False
        with open(manifest_path, 'r', encoding='utf-8') as f:
            manifest = json.load(f)
        restored = 0
        for rel_path in manifest.get("files", []):
            try:
                src = resolve_relative_path(backup_dir, rel_path)
                dest = resolve_relative_path(game_dir, rel_path)
            except ValueError as e:
                log_error(f"跳过非法回滚路径 {rel_path}: {e}")
                continue
            if os.path.exists(src):
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                try:
                    shutil.copy2(src, dest)
                    restored += 1
                except Exception as e:
                    log_error(f"回滚文件失败 {rel_path}: {e}")
        self.log(f"已从备份恢复 {restored} 个文件")
        log_info(f"回滚完成: {backup_dir}, 恢复文件数: {restored}")
        return True

    def _cleanup_old_backups(self):
        """清理超出数量限制的旧备份"""
        max_backups = self.cfg_mgr.config.get("max_backups", 1)
        backup_root = self._get_backup_root()
        if not os.path.exists(backup_root): return
        backups = sorted([
            d for d in os.listdir(backup_root)
            if os.path.isdir(os.path.join(backup_root, d)) and d.startswith("backup_")
        ])
        while len(backups) > max_backups:
            oldest = backups.pop(0)
            try:
                shutil.rmtree(os.path.join(backup_root, oldest))
                log_info(f"已清理旧备份: {oldest}")
            except Exception as e:
                log_error(f"清理旧备份失败: {e}")

    def list_backups(self):
        """列出可用的备份（供前端调用）"""
        backup_root = self._get_backup_root()
        if not os.path.exists(backup_root): return json.dumps([])
        result = []
        for d in sorted(os.listdir(backup_root), reverse=True):
            manifest_path = os.path.join(backup_root, d, "_backup_manifest.json")
            if os.path.exists(manifest_path):
                try:
                    with open(manifest_path, 'r', encoding='utf-8') as f:
                        m = json.load(f)
                    result.append({
                        "dir_name": d,
                        "version": m.get("version", "?"),
                        "timestamp": m.get("timestamp", 0),
                        "file_count": len(m.get("files", []))
                    })
                except: pass
        return json.dumps(result)

    def perform_rollback(self, dir_name):
        """执行手动回滚（供前端调用）"""
        try:
            backup_dir = resolve_relative_path(self._get_backup_root(), dir_name)
        except ValueError:
            return False
        if not os.path.exists(backup_dir): return False
        success = self._restore_backup(backup_dir)
        if success:
            self.log(f"回滚完成，已恢复到更新前的状态")
        return success

    def test_mirror_speeds(self):
        """测试所有镜像延迟，后台线程执行"""
        threading.Thread(target=self._test_mirrors_thread).start()

    def _probe_single_mirror_speed(self, mirror, test_url_path, label_by_url, insecure_hosts):
        test_url = mirror + test_url_path
        ssl_mode = ssl_mode_for_url(test_url, insecure_hosts=insecure_hosts)
        try:
            start = time.time()
            req = urllib.request.Request(
                test_url,
                method='HEAD',
                headers={'User-Agent': 'TCYClientUpdater/1.0'}
            )
            with self._urlopen_with_policy(req, timeout=5, url=test_url) as resp:
                latency = int((time.time() - start) * 1000)
                result = {
                    "mirror": mirror,
                    "label": label_by_url.get(mirror, mirror),
                    "tested_url": test_url,
                    "method": "HEAD",
                    "latency": latency,
                    "ok": True,
                    "ssl_mode": ssl_mode,
                    "status_class": classify_mirror_latency(latency, True),
                }
                self.log(f"[测速] {mirror} -> {latency}ms")
                return result
        except Exception as e:
            self.log(f"[测速] {mirror} -> 超时/失败")
            return {
                "mirror": mirror,
                "label": label_by_url.get(mirror, mirror),
                "tested_url": test_url,
                "method": "HEAD",
                "latency": -1,
                "ok": False,
                "ssl_mode": ssl_mode,
                "status_class": classify_mirror_latency(-1, False),
                "error": str(e),
            }

    def _test_mirrors_thread(self):
        try:
            self.log("正在测试镜像速度...")
            test_url_path = "https://github.com/KanameMadoka520/TCY-Client-Updater/releases/download/versions/latest.json"
            results = []
            label_by_url = {item["url"]: item["label"] for item in MIRROR_CATALOG}
            insecure_hosts = self._get_insecure_ssl_hosts()
            max_workers = bounded_worker_count(len(MIRROR_LIST), MIRROR_SPEED_MAX_WORKERS)
            self.log(f"镜像测速并发数: {max_workers}")
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {
                    executor.submit(
                        self._probe_single_mirror_speed,
                        mirror,
                        test_url_path,
                        label_by_url,
                        insecure_hosts,
                    ): mirror
                    for mirror in MIRROR_LIST
                }
                for future in as_completed(futures):
                    results.append(future.result())
            results.sort(key=lambda r: r['latency'] if r['ok'] else 99999)
            cache = {r['mirror']: r['latency'] for r in results}
            self.cfg_mgr.save_config({"mirror_speed_cache": cache})
            if self.cfg_mgr.config.get("auto_select_mirror", True):
                best = next((r for r in results if r['ok']), None)
                if best:
                    self.cfg_mgr.save_config({"mirror_prefix": best['mirror']})
                    self.log(f"自动选择最快镜像: {best['mirror']} ({best['latency']}ms)")
                    if global_window:
                        global_window.evaluate_js(f"applyMirrorPrefixFromBackend({json.dumps(best['mirror'])})")
            selected_mirror = self.cfg_mgr.config.get("mirror_prefix", DEFAULT_MIRROR_PREFIX)
            for item in results:
                item["selected"] = item.get("mirror") == selected_mirror
            if global_window:
                global_window.evaluate_js(f"showMirrorSpeedResults({json.dumps(results, ensure_ascii=False)})")
            self.log(f"镜像测速完成: {len([r for r in results if r['ok']])} 个可用")
        except Exception as e:
            log_error(f"镜像测速异常: {traceback.format_exc()}")
            self.log(f"镜像测速异常: {e}")
            if global_window:
                global_window.evaluate_js(f"setMirrorSpeedTestState('failed', {json.dumps('测速线程异常')})")

    def select_update_zip(self):
        """打开文件选择对话框选择 zip 更新包"""
        try:
            if global_window:
                result = global_window.create_file_dialog(
                    webview.OPEN_DIALOG,
                    allow_multiple=False,
                    file_types=('ZIP files (*.zip)', 'All files (*.*)')
                )
                if result and len(result) > 0:
                    return result[0]
        except Exception as e:
            self.log(f"选择文件失败: {e}")
        return None

    def preview_zip(self, zip_path):
        """预览 zip 内的 manifest.json 内容"""
        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                if 'manifest.json' in zf.namelist():
                    with zf.open('manifest.json') as f:
                        data = json.load(f)
                    actions_count = len(data.get('actions', []))
                    files_count = len(data.get('external_files', []))
                    desc_parts = []
                    for a in data.get('actions', [])[:5]:
                        if a.get('type') == 'delete_keyword':
                            desc_parts.append(f"删除含 [{a.get('keyword','')}] 的文件")
                        elif a.get('type') == 'delete':
                            desc_parts.append(f"删除 {a.get('path','')}")
                        elif a.get('type') == 'copy_folder':
                            desc_parts.append(f"覆盖 {a.get('dest','')}")
                    return json.dumps({
                        "valid": True,
                        "actions_count": actions_count,
                        "files_count": files_count,
                        "actions_preview": desc_parts
                    })
            return json.dumps({"valid": False, "error": "zip 中未找到 manifest.json"})
        except Exception as e:
            return json.dumps({"valid": False, "error": str(e)})

    def install_from_zip(self, zip_path, source_type='global'):
        """从本地 zip 安装更新（后台线程）"""
        def _run():
            try:
                # 将 zip 复制到游戏根目录
                dest = os.path.join(self.game_root, os.path.basename(zip_path))
                if os.path.abspath(zip_path) != os.path.abspath(dest):
                    shutil.copy2(zip_path, dest)

                # 直接执行本地 zip 的更新逻辑
                self._perform_local_zip_update(dest, source_type)

                self.log("本地更新包安装完成！")
                if global_window:
                    global_window.evaluate_js("alert('更新安装完成！请重启游戏客户端。')")
            except Exception as e:
                self.log(f"本地安装失败: {e}")
                log_error(f"本地zip安装异常: {traceback.format_exc()}")
                if global_window:
                    global_window.evaluate_js(f"alert('安装失败: {str(e)}')")
        threading.Thread(target=_run).start()

    def _perform_local_zip_update(self, zip_path, source_type):
        """从本地 zip 执行更新（原子性，含备份回滚）"""
        staging_dir = os.path.join(self.game_root, "temp_staging")
        temp_dir = os.path.join(self.game_root, "temp_update_tcy")
        backup_dir = None

        try:
            for d in [staging_dir, temp_dir]:
                if os.path.exists(d):
                    shutil.rmtree(d)
            os.makedirs(staging_dir, exist_ok=True)

            # 解压
            with zipfile.ZipFile(zip_path, 'r') as zf:
                for file in zf.namelist():
                    zf.extract(file, temp_dir)

            manifest_path = os.path.join(temp_dir, "manifest.json")
            data = {}
            if os.path.exists(manifest_path):
                with open(manifest_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

            actions = data.get('actions', [])
            external_files = data.get('external_files', [])
            total_ops = len(actions) + len(external_files)
            current_op = [0]

            def report_step(name):
                current_op[0] += 1
                p = int((current_op[0] / total_ops) * 100) if total_ops > 0 else 100
                if global_window:
                    safe_msg = name.replace("'", "\\'")
                    global_window.evaluate_js(f"updateProgressDetails({p}, '--', '({current_op[0]}/{total_ops}): {safe_msg}')")

            # 下载 external_files 到暂存区
            mirror_prefix = self.cfg_mgr.config.get("mirror_prefix", DEFAULT_MIRROR_PREFIX)
            files_to_download = []

            for item in external_files:
                target_path = os.path.join(self.game_root, item['path'])
                expected_sha = item.get('sha256', '')
                if os.path.exists(target_path):
                    if expected_sha:
                        match, _ = self._verify_sha256(target_path, expected_sha)
                        if match:
                            report_step(f"跳过(hash匹配): {item['name']}")
                            continue
                    elif abs(os.path.getsize(target_path) - item.get('size', 0)) < 1024:
                        report_step(f"跳过已存在: {item['name']}")
                        continue
                files_to_download.append(item)

            # 下载需要的 external_files
            if files_to_download:
                max_workers = self.cfg_mgr.config.get("parallel_downloads", 3)
                from concurrent.futures import ThreadPoolExecutor, as_completed

                self.log(f"下载 {len(files_to_download)} 个外部文件...")
                dl_errors = []

                def dl_single(item):
                    if self.cancel_event.is_set():
                        return False
                    d_url = item['url']
                    if source_type == 'cn' and "github.com" in d_url:
                        if mirror_prefix and not d_url.startswith(mirror_prefix):
                            d_url = mirror_prefix + d_url
                    staging_path = os.path.join(staging_dir, item['path'])
                    os.makedirs(os.path.dirname(staging_path), exist_ok=True)
                    self._download_url_to_path(d_url, staging_path, connect_timeout=15, stall_timeout=20)
                    expected_sha = item.get('sha256', '')
                    if expected_sha:
                        match, actual = self._verify_sha256(staging_path, expected_sha)
                        if not match:
                            raise Exception(f"SHA256校验失败: {item['name']}")
                    self.log(f"已下载: {item['name']}")
                    report_step(f"下载完成: {item['name']}")
                    return True

                self.update_stage = 1
                self.cancel_event.clear()

                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    futures = {executor.submit(dl_single, item): item for item in files_to_download}
                    for future in as_completed(futures):
                        if self.cancel_event.is_set():
                            break
                        try:
                            future.result()
                        except Exception as e:
                            dl_errors.append(str(e))

                if self.cancel_event.is_set():
                    self.log("本地更新下载阶段被取消。")
                    if global_window:
                        global_window.evaluate_js("onUpdateCancelled()")
                    return

                if dl_errors:
                    raise Exception("下载失败:\n" + "\n".join(dl_errors))

            self.update_stage = 2
            if global_window:
                global_window.evaluate_js("disableCancelButton()")

            # 收集受影响的文件并备份
            affected_paths = []
            for action in actions:
                if action.get('type') == 'delete_keyword':
                    t_folder = os.path.join(self.game_root, action.get('folder', ''))
                    keyword = action.get('keyword', '')
                    if os.path.exists(t_folder) and keyword:
                        for f in os.listdir(t_folder):
                            if keyword.lower() in f.lower():
                                affected_paths.append(os.path.join(t_folder, f))
                elif action.get('type') == 'delete':
                    affected_paths.append(os.path.join(self.game_root, action.get('path', '')))
                elif action.get('type') == 'copy_folder':
                    dest = os.path.join(self.game_root, action.get('dest', ''))
                    if os.path.exists(dest):
                        for root, dirs, files in os.walk(dest):
                            for f in files:
                                affected_paths.append(os.path.join(root, f))

            for item in files_to_download:
                tp = os.path.join(self.game_root, item['path'])
                if os.path.exists(tp):
                    affected_paths.append(tp)

            version_str = data.get('version', time.strftime('%y.%m.%d.%H.%M'))
            if affected_paths:
                backup_dir = self._create_backup(version_str, affected_paths)

            try:
                # 执行 actions
                for action in actions:
                    if action.get('type') == 'delete_keyword':
                        t_folder = os.path.join(self.game_root, action.get('folder', ''))
                        keyword = action.get('keyword', '')
                        if os.path.exists(t_folder) and keyword:
                            for f in os.listdir(t_folder):
                                if keyword.lower() in f.lower():
                                    try:
                                        os.remove(os.path.join(t_folder, f))
                                        self.log(f"删: {f}")
                                    except: pass
                    elif action.get('type') == 'delete':
                        try: os.remove(os.path.join(self.game_root, action.get('path')))
                        except: pass
                    elif action.get('type') == 'copy_folder':
                        src = os.path.join(temp_dir, action.get('src'))
                        dest = os.path.join(self.game_root, action.get('dest'))
                        if os.path.exists(src):
                            shutil.copytree(src, dest, dirs_exist_ok=True)
                            self.log(f"合并配置: {action.get('src')}")

                # 移动暂存文件
                for item in files_to_download:
                    sp = os.path.join(staging_dir, item['path'])
                    tp = os.path.join(self.game_root, item['path'])
                    if os.path.exists(sp):
                        os.makedirs(os.path.dirname(tp), exist_ok=True)
                        shutil.move(sp, tp)
                        self.log(f"已安装: {item['name']}")

                self.log("本地更新包应用完成")
            except Exception as e:
                self.log(f"应用失败，正在回滚: {e}")
                if backup_dir:
                    self._restore_backup(backup_dir)
                raise

        finally:
            for d in [temp_dir, staging_dir]:
                if os.path.exists(d):
                    try: shutil.rmtree(d)
                    except: pass
            if os.path.exists(zip_path):
                try: os.remove(zip_path)
                except: pass

    def save_settings(self, settings_json):
        try:
            data = json.loads(settings_json)
            self.cfg_mgr.save_config(data)
            return True
        except: return False

    def get_launcher_settings(self):
        """返回启动器当前设置，供前端读取预设等配置"""
        try:
            return self.cfg_mgr.load_config()
        except Exception:
            return {}
    def select_custom_image(self):
        try:
            file_types = ('Image Files (*.png;*.jpg;*.jpeg;*.webp)', 'All files (*.*)')
            if global_window:
                result = global_window.create_file_dialog(webview.OPEN_DIALOG, allow_multiple=False, file_types=file_types)
                if result and len(result) > 0:
                    with open(result[0], "rb") as f:
                        b64 = base64.b64encode(f.read()).decode('utf-8')
                        return f"data:image/png;base64,{b64}"
        except: pass
        return None
    def get_default_bg(self): return DEFAULT_BG_B64
    def open_folder_path(self, folder_path):
        try:
            folder_path = str(folder_path or '')
            if not folder_path:
                return {"success": False, "error": "路径为空"}
            abs_path = os.path.abspath(folder_path)
            # Restrict to game_root subtree for safety
            root = os.path.abspath(self.game_root)
            if not (abs_path == root or abs_path.startswith(root + os.sep)):
                return {"success": False, "error": "不允许打开此路径"}
            if os.path.isfile(abs_path):
                abs_path = os.path.dirname(abs_path)
            os.makedirs(abs_path, exist_ok=True)
            if os.name == 'nt':
                os.startfile(abs_path)
            else:
                subprocess.Popen(['xdg-open', abs_path])
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def copy_to_clipboard(self, text):
        try:
            text = '' if text is None else str(text)
            if os.name == 'nt':
                proc = subprocess.run(
                    ['clip'],
                    input=text,
                    text=True,
                    encoding='utf-8',
                    errors='ignore',
                    capture_output=True,
                    timeout=5,
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
                )
                if proc.returncode == 0:
                    return {"success": True}
                return {"success": False, "error": (proc.stderr or proc.stdout or 'clip 执行失败').strip()}
            proc = subprocess.run(
                ['sh', '-lc', 'command -v xclip >/dev/null 2>&1 && xclip -selection clipboard || command -v xsel >/dev/null 2>&1 && xsel --clipboard --input'],
                input=text,
                text=True,
                encoding='utf-8',
                errors='ignore',
                capture_output=True,
                timeout=5
            )
            if proc.returncode == 0:
                return {"success": True}
            return {"success": False, "error": '系统剪贴板工具不可用（需要 xclip 或 xsel）'}
        except Exception as e:
            return {"success": False, "error": str(e)}

    _status_proxy_port = None
    _status_proxy_server = None
    _status_proxy_target = "https://server.tcymc.space"  # 当前反代目标，可动态切换

    def get_server_status_url(self):
        """启动本地反向代理服务（仅首次），返回 localhost URL 供 iframe 加载。
        原理：在本地启动一个 HTTP 反向代理，将所有请求转发到目标网站，
        并剥掉 Content-Security-Policy / X-Frame-Options 等限制性响应头，
        使 iframe 可以正常加载原本禁止嵌入的页面。
        使用 ThreadingHTTPServer 支持并发请求，避免浏览器并行加载资源时串行阻塞。
        代理线程为 daemon 线程，主程序退出时自动终止（含异常退出/崩溃），不会残留。"""
        if Api._status_proxy_port and Api._status_proxy_server:
            return {"success": True, "url": f"http://127.0.0.1:{Api._status_proxy_port}/",
                    "port": Api._status_proxy_port, "target": Api._status_proxy_target}
        try:
            from http.server import BaseHTTPRequestHandler
            from socketserver import ThreadingTCPServer

            blocked_headers = {'content-security-policy', 'x-frame-options',
                               'content-security-policy-report-only'}

            # 注入到 HTML 页面的脚本：拦截外部链接点击 → postMessage 给父窗口
            _NAV_SCRIPT = (b'<script>(function(){'
                b'document.addEventListener("click",function(e){'
                b'var a=e.target.closest("a");if(!a||!a.href)return;'
                b'try{var u=new URL(a.href,location.href);'
                b'if(u.origin!==location.origin){'
                b'e.preventDefault();e.stopPropagation();'
                b'window.parent.postMessage({type:"proxy-navigate",url:u.href},"*");'
                b'}}catch(ex){}},true);'
                b'})();</script>')

            class _ProxyHandler(BaseHTTPRequestHandler):
                def do_GET(self):
                    proxy_url = Api._status_proxy_target + self.path
                    try:
                        # 判断是否是 HTML 请求（浏览器导航/页面请求的 Accept 包含 text/html）
                        accept_hdr = self.headers.get('Accept', '')
                        is_html_req = 'text/html' in accept_hdr

                        fwd_headers = {
                            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                                          'AppleWebKit/537.36 (KHTML, like Gecko) '
                                          'Chrome/131.0.0.0 Safari/537.36',
                            'Accept': accept_hdr or '*/*',
                            'Accept-Language': self.headers.get('Accept-Language', 'zh-CN,zh;q=0.9'),
                        }
                        # HTML 请求不发 Accept-Encoding，让服务器返回未压缩 HTML（方便注入脚本）
                        # 非 HTML 资源 (CSS/JS/图片) 透传 Accept-Encoding 保持 gzip 加速
                        if not is_html_req:
                            ae = self.headers.get('Accept-Encoding')
                            if ae:
                                fwd_headers['Accept-Encoding'] = ae

                        req = urllib.request.Request(proxy_url, headers=fwd_headers)
                        with urllib.request.urlopen(req, timeout=15) as resp:
                            body = resp.read()
                            ct = resp.headers.get('Content-Type', '')
                            is_html = 'text/html' in ct

                            # 对 HTML 响应注入链接拦截脚本
                            if is_html:
                                # 通常服务器会返回未压缩 HTML（因为我们没发 Accept-Encoding）
                                # 但某些服务器无视 Accept-Encoding 仍返回压缩数据，保险起见处理
                                ce = resp.headers.get('Content-Encoding', '')
                                if 'gzip' in ce:
                                    import gzip as _gzip
                                    body = _gzip.decompress(body)
                                elif ce and ce != 'identity':
                                    # 未知编码（如 br），无法解压则跳过注入，原样透传
                                    is_html = False

                                if is_html:
                                    if b'</head>' in body:
                                        body = body.replace(b'</head>', _NAV_SCRIPT + b'</head>', 1)
                                    elif b'</body>' in body:
                                        body = body.replace(b'</body>', _NAV_SCRIPT + b'</body>', 1)
                                    else:
                                        body += _NAV_SCRIPT

                            self.send_response(resp.status)
                            for key, val in resp.headers.items():
                                k = key.lower()
                                if k in blocked_headers:
                                    continue
                                # 注入后的 HTML 已解压，跳过原始编码和长度头
                                if is_html and k in ('content-encoding', 'content-length',
                                                      'transfer-encoding'):
                                    continue
                                self.send_header(key, val)
                            if is_html:
                                self.send_header('Content-Length', str(len(body)))
                            self.end_headers()
                            self.wfile.write(body)
                    except Exception as e:
                        self.send_response(502)
                        self.send_header('Content-Type', 'text/plain; charset=utf-8')
                        self.end_headers()
                        self.wfile.write(f"反向代理错误: {e}".encode('utf-8'))

                def log_message(self, format, *args):
                    pass  # 静默，不污染控制台

            # ThreadingTCPServer 支持并发请求（浏览器同时请求 CSS/JS/图片不会串行阻塞）
            class _ThreadingHTTPServer(ThreadingTCPServer):
                allow_reuse_address = True
                def finish_request(self, request, client_address):
                    _ProxyHandler(request, client_address, self)

            server = _ThreadingHTTPServer(('127.0.0.1', 0), _ProxyHandler)
            Api._status_proxy_port = server.server_address[1]
            Api._status_proxy_server = server
            t = threading.Thread(target=server.serve_forever, daemon=True)
            t.start()
            log_info(f"Server status reverse proxy started on port {Api._status_proxy_port}")
            return {"success": True, "url": f"http://127.0.0.1:{Api._status_proxy_port}/",
                    "port": Api._status_proxy_port, "target": Api._status_proxy_target}
        except Exception as e:
            log_error(f"get_server_status_url failed: {e}")
            return {"success": False, "error": str(e)}

    def set_proxy_target(self, url):
        """动态切换反向代理的目标网址。下次请求将转发到新的目标。"""
        if not url or not url.strip():
            return {"success": False, "error": "网址不能为空"}
        url = url.strip().rstrip('/')
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        Api._status_proxy_target = url
        log_info(f"Proxy target changed to: {url}")
        return {"success": True, "target": url}

    def stop_server_status_proxy(self):
        """手动关闭反向代理服务"""
        if Api._status_proxy_server:
            try:
                Api._status_proxy_server.shutdown()
                log_info(f"Server status reverse proxy on port {Api._status_proxy_port} stopped")
            except Exception as e:
                log_error(f"stop_server_status_proxy failed: {e}")
            Api._status_proxy_server = None
            Api._status_proxy_port = None
            return {"success": True}
        return {"success": True, "message": "反向代理未运行"}

    def open_server_status_window(self):
        """在独立 pywebview 窗口中打开服务器状态页面（备用方案）"""
        try:
            webview.create_window('服务器状态 - server.tcymc.space',
                                  'https://server.tcymc.space',
                                  width=1000, height=700)
            return {"success": True}
        except Exception as e:
            log_error(f"open_server_status_window failed: {e}")
            return {"success": False, "error": str(e)}

    def scan_versions(self):
        try: return [os.path.basename(f) for f in glob.glob(os.path.join(self.game_root, "update*.zip"))]
        except: return []

    def _parse_mod_metadata(self, file_path):
        import zipfile
        import json
        import re
        result = {"valid": False, "id": "", "name": "", "version": "", "description": "", "authors": "", "dependencies": []}
        try:
            with zipfile.ZipFile(file_path, 'r') as zf:
                file_list = zf.namelist()

                # Fabric / Quilt
                if 'fabric.mod.json' in file_list or 'quilt.mod.json' in file_list:
                    target_file = 'fabric.mod.json' if 'fabric.mod.json' in file_list else 'quilt.mod.json'
                    with zf.open(target_file) as f:
                        data = json.loads(f.read().decode('utf-8', errors='ignore'))
                    result["valid"] = True
                    result["id"] = data.get("id", "")
                    result["name"] = data.get("name", "")
                    result["version"] = data.get("version", "")
                    result["description"] = data.get("description", "")

                    authors = data.get("authors", "")
                    if isinstance(authors, list):
                        parsed_authors = []
                        for author in authors:
                            if isinstance(author, str):
                                parsed_authors.append(author)
                            elif isinstance(author, dict) and "name" in author:
                                parsed_authors.append(author["name"])
                        result["authors"] = ", ".join(parsed_authors)
                    elif isinstance(authors, str):
                        result["authors"] = authors

                    depends = data.get("depends", {})
                    if isinstance(depends, dict):
                        result["dependencies"] = list(depends.keys())

                # Forge / NeoForge
                elif 'META-INF/mods.toml' in file_list:
                    with zf.open('META-INF/mods.toml') as f:
                        content_toml = f.read().decode('utf-8', errors='ignore')
                    result["valid"] = True

                    mod_id = re.search(r'modId\s*=\s*"([^"]+)"', content_toml)
                    display_name = re.search(r'displayName\s*=\s*"([^"]+)"', content_toml)
                    version = re.search(r'version\s*=\s*"([^"]+)"', content_toml)

                    description_match = re.search(r'description\s*=\s*\'\'\'(.*?)\'\'\'', content_toml, re.DOTALL)
                    if not description_match:
                        description_match = re.search(r'description\s*=\s*"""(.*?)"""', content_toml, re.DOTALL)
                    if not description_match:
                        description_match = re.search(r'description\s*=\s*"([^"]+)"', content_toml)

                    authors_match = re.search(r'authors\s*=\s*"([^"]+)"', content_toml)

                    deps_blocks = re.findall(r'\[\[dependencies\..*?\]\](.*?)(\[\[|$)', content_toml, re.DOTALL)
                    dependencies = []
                    for block, _ in deps_blocks:
                        dep_id_match = re.search(r'modId\s*=\s*"([^"]+)"', block)
                        if dep_id_match:
                            dependencies.append(dep_id_match.group(1))

                    result['id'] = mod_id.group(1) if mod_id else ""
                    result['name'] = display_name.group(1) if display_name else ""
                    result['version'] = version.group(1) if version and version.group(1) != "${file.jarVersion}" else ""
                    result['description'] = description_match.group(1).strip() if description_match else ""
                    result['authors'] = authors_match.group(1) if authors_match else ""
                    result['dependencies'] = dependencies
        except Exception as e:
            return {"valid": False, "error": str(e)}
        return result

    def _load_conflict_rules(self):
        """加载本地冲突规则文件，文件不存在或格式错误时返回空列表"""
        rules_path = os.path.join(current_dir, "conflict_rules.json")
        if not os.path.exists(rules_path):
            return []
        try:
            with open(rules_path, "r", encoding="utf-8") as f:
                data = json.loads(f.read())
            rules = data.get("rules", []) if isinstance(data, dict) else []
            # 校验每条规则基本结构
            valid = []
            for r in rules:
                if isinstance(r, dict) and r.get("id") and isinstance(r.get("mods"), list) and len(r["mods"]) > 0:
                    valid.append(r)
            return valid
        except Exception:
            return []

    def get_conflict_rules(self):
        """前端API：获取冲突规则列表"""
        return self._load_conflict_rules()

    def get_mods_metadata(self):
        sub_path = "mods"
        base_dir = os.path.join(self.game_root, ".minecraft", "versions", TARGET_VERSION_NAME, sub_path)
        if not os.path.exists(base_dir):
            base_dir = os.path.join(self.game_root, "versions", TARGET_VERSION_NAME, sub_path)

        mods_list = []
        if not os.path.exists(base_dir):
            return mods_list

        try:
            raw_mods = []
            enabled_mod_ids = set()
            for f in os.listdir(base_dir):
                if f.endswith('.jar') or f.endswith('.jar.disabled'):
                    file_path = os.path.join(base_dir, f)
                    if not os.path.isfile(file_path):
                        continue

                    is_enabled = f.endswith('.jar')
                    metadata = self._parse_mod_metadata(file_path)

                    if is_enabled and metadata.get("valid") and metadata.get("id"):
                        enabled_mod_ids.add(metadata.get("id"))

                    raw_mods.append((f, is_enabled, file_path, metadata))

            ignored_deps = {"minecraft", "fabricloader", "fabric-api", "forge", "java", "neoforge", "fabric", "quilt_loader", "quilt"}
            dep_ignores = self.cfg_mgr.config.get("mod_dep_ignores", {})
            if not isinstance(dep_ignores, dict):
                dep_ignores = {}

            for f, is_enabled, file_path, metadata in raw_mods:
                deps_all = metadata.get("dependencies", []) if isinstance(metadata.get("dependencies", []), list) else []
                missing_deps_raw = []
                if is_enabled:
                    for dep in deps_all:
                        if dep not in ignored_deps and dep not in enabled_mod_ids:
                            missing_deps_raw.append(dep)

                mod_id = metadata.get("id", "") if metadata.get("valid") else ""
                ignore_key = mod_id if mod_id else f
                ignored_for_mod = dep_ignores.get(ignore_key, [])
                if not isinstance(ignored_for_mod, list):
                    ignored_for_mod = []

                ignored_missing_deps = [d for d in missing_deps_raw if d in ignored_for_mod]
                missing_deps = [d for d in missing_deps_raw if d not in ignored_for_mod]

                if missing_deps:
                    missing_status = "missing"
                elif ignored_missing_deps:
                    missing_status = "missing_ignored"
                else:
                    missing_status = "ok"

                mod_info = {
                    "filename": f,
                    "enabled": is_enabled,
                    "is_enabled": is_enabled,
                    "has_metadata": metadata.get("valid", False),
                    "valid": metadata.get("valid", False),
                    "id": mod_id,
                    "name": metadata.get("name", "") if metadata.get("valid") and metadata.get("name") else f,
                    "version": metadata.get("version", ""),
                    "description": metadata.get("description", ""),
                    "authors": metadata.get("authors", ""),
                    "dependencies": deps_all,
                    "missing_deps_raw": missing_deps_raw,
                    "missing_deps": missing_deps,
                    "ignored_missing_deps": ignored_missing_deps,
                    "missing_status": missing_status,
                    "ignore_key": ignore_key,
                    "path": file_path
                }
                mods_list.append(mod_info)
        except Exception as e:
            logging.error(f"Error scanning mods metadata: {e}")

        # 冲突规则匹配
        try:
            rules = self._load_conflict_rules()
            if rules:
                enabled_ids = {m["id"] for m in mods_list if m.get("is_enabled") and m.get("id")}
                mod_by_id = {}
                for m in mods_list:
                    if m.get("id"):
                        mod_by_id[m["id"]] = m
                        m["conflict_rules"] = []

                for rule in rules:
                    rule_mods = rule.get("mods", [])
                    # 检查规则是否命中：所有涉及的 mod 都已启用
                    if all(mid in enabled_ids for mid in rule_mods):
                        hit = {"id": rule.get("id", ""), "type": rule.get("type", ""),
                               "description": rule.get("description", ""), "severity": rule.get("severity", "warning")}
                        for mid in rule_mods:
                            if mid in mod_by_id:
                                mod_by_id[mid]["conflict_rules"].append(hit)
        except Exception:
            pass  # 冲突规则加载失败不影响主流程

        return mods_list

    def set_mod_dependency_ignore(self, mod_key, dep_name, ignored):
        if not mod_key or not dep_name:
            return {"success": False, "error": "参数不能为空"}

        try:
            cfg = self.cfg_mgr.load_config()
            dep_ignores = cfg.get("mod_dep_ignores", {})
            if not isinstance(dep_ignores, dict):
                dep_ignores = {}

            deps = dep_ignores.get(mod_key, [])
            if not isinstance(deps, list):
                deps = []

            if ignored:
                if dep_name not in deps:
                    deps.append(dep_name)
                    self._add_activity_log("mod_dep_ignore_set", {"mod_key": mod_key, "dep": dep_name})
            else:
                deps = [d for d in deps if d != dep_name]
                self._add_activity_log("mod_dep_ignore_cleared", {"mod_key": mod_key, "dep": dep_name})

            if deps:
                dep_ignores[mod_key] = deps
            elif mod_key in dep_ignores:
                dep_ignores.pop(mod_key, None)

            self.cfg_mgr.save_config({"mod_dep_ignores": dep_ignores})
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def clear_mod_dependency_ignores(self, mod_key):
        if not mod_key:
            return {"success": False, "error": "未提供mod_key"}

        try:
            cfg = self.cfg_mgr.load_config()
            dep_ignores = cfg.get("mod_dep_ignores", {})
            if isinstance(dep_ignores, dict) and mod_key in dep_ignores:
                dep_ignores.pop(mod_key, None)
                self.cfg_mgr.save_config({"mod_dep_ignores": dep_ignores})
            self._add_activity_log("mod_dep_ignore_cleared", {"mod_key": mod_key, "dep": "*"})
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_mod_dependency_graph(self):
        mods = self.get_mods_metadata()
        nodes = []
        edges = []
        node_seen = set()

        def add_node(node_id, node_type, label, state):
            if node_id in node_seen:
                return
            node_seen.add(node_id)
            nodes.append({
                "id": node_id,
                "type": node_type,
                "label": label,
                "state": state
            })

        for m in mods:
            mod_node_id = f"mod:{m.get('ignore_key', m.get('filename', ''))}"
            mod_label = m.get('name') or m.get('filename') or m.get('id') or "unknown"
            add_node(mod_node_id, "mod", mod_label, m.get("missing_status", "ok"))

        enabled_mod_ids = {m.get("id") for m in mods if m.get("is_enabled") and m.get("id")}

        for m in mods:
            mod_node_id = f"mod:{m.get('ignore_key', m.get('filename', ''))}"
            for dep in m.get("dependencies", []):
                dep_node_id = f"dep:{dep}"

                if dep in enabled_mod_ids:
                    dep_state = "ok"
                elif dep in m.get("ignored_missing_deps", []):
                    dep_state = "missing_ignored"
                elif dep in m.get("missing_deps", []):
                    dep_state = "missing"
                else:
                    dep_state = "ok"

                add_node(dep_node_id, "dependency", dep, dep_state)
                edges.append({
                    "from": mod_node_id,
                    "to": dep_node_id,
                    "state": dep_state
                })

        return {"nodes": nodes, "edges": edges}

    def list_files(self, folder_type):
        sub_path = "mods" if folder_type == "mods" else "config"
        base_dir = self._get_game_subdir(sub_path)

        def _scan_recursive(current_path, relative_root=""):
            items = []
            if not os.path.exists(current_path): return []
            try:
                all_items = sorted(os.listdir(current_path), key=lambda x: (not os.path.isdir(os.path.join(current_path, x)), x.lower()))
                for f in all_items:
                    full_path = os.path.join(current_path, f)
                    rel_path = os.path.join(relative_root, f).replace("\\", "/")
                    if os.path.isdir(full_path):
                        items.append({"type": "folder", "name": f, "path": rel_path, "children": _scan_recursive(full_path, rel_path)})
                    else:
                        size = f"{os.path.getsize(full_path)/1024:.1f} KB"
                        mtime = datetime.fromtimestamp(os.path.getmtime(full_path)).strftime('%Y-%m-%d %H:%M')
                        items.append({"type": "file", "name": f, "path": rel_path, "size": size, "date": mtime})
            except: pass
            return items
        return _scan_recursive(base_dir)

    def list_crash_logs(self):
        """Return crash-reports and logs files sorted by mtime descending."""
        result = {"crash_reports": [], "logs": []}
        for dir_key, sub in [("crash_reports", "crash-reports"), ("logs", "logs")]:
            # Priority: .minecraft root → game_root → version subfolder
            base = os.path.join(self.game_root, ".minecraft", sub)
            if not os.path.exists(base):
                base = os.path.join(self.game_root, sub)
            if not os.path.exists(base):
                base = self._get_game_subdir(sub)
            files = []
            try:
                for f in os.listdir(base):
                    fp = os.path.join(base, f)
                    if os.path.isfile(fp) and any(f.endswith(ext) for ext in ('.txt', '.log', '.gz')):
                        files.append({
                            "filename": f,
                            "size": f"{os.path.getsize(fp) / 1024:.1f} KB",
                            "date": datetime.fromtimestamp(os.path.getmtime(fp)).strftime('%Y-%m-%d %H:%M'),
                            "mtime": os.path.getmtime(fp)
                        })
            except Exception:
                pass
            files.sort(key=lambda x: x["mtime"], reverse=True)
            result[dir_key] = files
        return json.dumps(result)

    def load_crash_log(self, file_type, filename):
        """Load a crash report or log file. Caps log files at 500KB."""
        if ".." in filename:
            return json.dumps({"success": False, "error": "非法文件名"})
        if file_type == "crash_report":
            base = os.path.join(self.game_root, ".minecraft", "crash-reports")
            if not os.path.exists(base):
                base = os.path.join(self.game_root, "crash-reports")
            if not os.path.exists(base):
                base = self._get_game_subdir("crash-reports")
        else:
            base = os.path.join(self.game_root, ".minecraft", "logs")
            if not os.path.exists(base):
                base = os.path.join(self.game_root, "logs")
            if not os.path.exists(base):
                base = self._get_game_subdir("logs")
        file_path = os.path.join(base, filename)
        if not os.path.isfile(file_path):
            return json.dumps({"success": False, "error": "文件不存在"})
        # Refuse .gz — list them but show badge in frontend
        if filename.endswith('.gz'):
            return json.dumps({"success": False, "error": "gz_compressed"})
        try:
            size = os.path.getsize(file_path)
            MAX_BYTES = 500 * 1024
            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                if file_type == "log" and size > MAX_BYTES:
                    f.seek(max(0, size - MAX_BYTES))
                    f.readline()  # skip partial first line
                content = f.read()
            return json.dumps({"success": True, "content": content, "truncated": file_type == "log" and size > MAX_BYTES})
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)})

    def analyze_crash_log(self, raw_text):
        """
        Track A: Local rule engine.
        Returns JSON: {suspicious_mods, patterns, caused_by_chain, summary}
        """
        try:
            installed_mods = {m["id"]: m for m in self.get_mods_metadata() if m.get("id")}
        except Exception:
            installed_mods = {}

        # Java common packages to exclude from mod matching
        JAVA_BUILTINS = {
            'java', 'javax', 'sun', 'com', 'net', 'org', 'io', 'minecraft',
            'mojang', 'lang', 'util', 'io', 'nio', 'reflect', 'jvm'
        }

        results = {
            "suspicious_mods": [],
            "patterns": [],
            "caused_by_chain": [],
            "summary": ""
        }

        # === OOM ===
        if re.search(r'java\.lang\.OutOfMemoryError', raw_text):
            results["patterns"].append({
                "id": "OOM",
                "label": "内存溢出 (OOM)",
                "detail": "检测到 java.lang.OutOfMemoryError，建议增大 JVM -Xmx 参数。"
            })

        # === Mixin conflict ===
        mixin_mods = set(re.findall(r'\$\$\$([a-zA-Z0-9_\-]+)\$', raw_text))
        mixin_mods |= set(re.findall(r'(?<!\$)\$([a-zA-Z0-9_\-]+)\$(?!\$)', raw_text))
        mixin_mods -= JAVA_BUILTINS
        if mixin_mods:
            results["patterns"].append({
                "id": "Mixin",
                "label": "Mixin 冲突",
                "detail": f"检测到 Mixin 注入痕迹，可疑 mod ID: {', '.join(sorted(mixin_mods))}"
            })

        # === Missing dependency ===
        missing_dep_matches = list(set(re.findall(r'requires\s+\[?([a-zA-Z0-9_\-]+)[@\s\[]', raw_text)))
        if missing_dep_matches or re.search(r'Missing (Mods|Dependencies)', raw_text, re.IGNORECASE):
            detail = f"检测到依赖缺失: {', '.join(missing_dep_matches)}" if missing_dep_matches else "检测到 Missing Mods/Dependencies 提示"
            results["patterns"].append({
                "id": "MissingDep",
                "label": "缺少依赖",
                "detail": detail
            })

        # === Extract mod IDs from stack frames ===
        frame_pattern = re.compile(r'^\s+at\s+([\w\$\.]+)\(', re.MULTILINE)
        suspicious_ids = set()
        for match in frame_pattern.finditer(raw_text):
            fqcn = match.group(1)
            parts = [p.lower() for p in fqcn.split('.') if p and p not in JAVA_BUILTINS]
            for mod_id in installed_mods:
                if mod_id.lower() in parts:
                    suspicious_ids.add(mod_id)

        for mod_id in suspicious_ids:
            mod = installed_mods[mod_id]
            results["suspicious_mods"].append({
                "id": mod_id,
                "filename": mod.get("filename", ""),
                "name": mod.get("name", mod_id),
                "enabled": mod.get("enabled", True)
            })

        # === Caused by chain ===
        results["caused_by_chain"] = re.findall(r'Caused by:\s*(.+)', raw_text)

        if results["patterns"]:
            labels = [p["label"] for p in results["patterns"]]
            results["summary"] = "检测到以下问题: " + "、".join(labels)
        elif results["suspicious_mods"]:
            results["summary"] = f"未识别到常见崩溃模式，但发现 {len(results['suspicious_mods'])} 个可疑 mod。"
        else:
            results["summary"] = "未识别到明确崩溃原因，建议使用 AI 辅助分析。"

        return json.dumps(results, ensure_ascii=False)

    def build_ai_payload(self, file_type, raw_text):
        """
        Preprocess log for AI — returns structured preview JSON.
        {segments: [{label, rule, content}], mod_list_context, total_chars}
        """
        segments = []
        try:
            installed_mods = self.get_mods_metadata()
        except Exception:
            installed_mods = []

        if file_type == "crash_report":
            head_match = re.search(
                r'(---- Minecraft Crash Report ----.*?)(?=-- Affected level --|-- System Details --|\Z)',
                raw_text, re.DOTALL
            )
            if head_match:
                segments.append({
                    "label": "崩溃报告头部 (Crash Report Head)",
                    "rule": "提取从 '---- Minecraft Crash Report ----' 到 '-- Affected level --' 之间的内容（含完整堆栈跟踪）",
                    "content": head_match.group(1).strip()[:4000]
                })
            caused_by = re.findall(r'Caused by:.+', raw_text)
            if caused_by:
                segments.append({
                    "label": "Caused by 异常链",
                    "rule": "提取所有 'Caused by:' 行，展示异常根因链",
                    "content": "\n".join(caused_by)
                })
            sys_match = re.search(r'-- System Details --(.*?)(?=\Z)', raw_text, re.DOTALL)
            if sys_match:
                segments.append({
                    "label": "系统详情 (截断至1000字符)",
                    "rule": "提取 '-- System Details --' 段落，包含 Fabric Mods 列表和 Java 版本",
                    "content": sys_match.group(1).strip()[:1000]
                })
        else:
            lines = raw_text.splitlines()
            tail = lines[-100:] if len(lines) > 100 else lines
            segments.append({
                "label": f"最近 {len(tail)} 行日志",
                "rule": "从 latest.log 末尾提取最多 100 行",
                "content": "\n".join(tail)
            })
            error_lines = [l for l in lines if re.search(r'\[ERROR\]|\[FATAL\]|Exception|Error:', l)]
            if error_lines:
                segments.append({
                    "label": "错误行 (ERROR/FATAL/Exception)",
                    "rule": "从完整日志中筛选包含 [ERROR]、[FATAL]、Exception、Error: 的行",
                    "content": "\n".join(error_lines[:50])
                })

        mod_lines = []
        for m in installed_mods:
            if m.get("id"):
                status = "启用" if m.get("enabled", True) else "禁用"
                mod_lines.append(f"  {m['id']} ({m.get('name', '')}) [{status}]")
        mod_context = "已安装 Mod 列表:\n" + "\n".join(mod_lines[:100])

        total = sum(len(s["content"]) for s in segments) + len(mod_context)
        return json.dumps({"segments": segments, "mod_list_context": mod_context, "total_chars": total}, ensure_ascii=False)

    def send_to_ai(self, payload_json):
        """
        Track B: POST preprocessed payload to user-configured OpenAI-compatible endpoint.
        Runs in a background thread. Result pushed via global_window.evaluate_js().
        Returns immediately with {"queued": true} or error.
        """
        cfg = self.cfg_mgr.config
        api_url = cfg.get("ai_api_url", "").strip()
        api_key = cfg.get("ai_api_key", "").strip()
        model = cfg.get("ai_model", "gpt-3.5-turbo").strip()

        if not api_url:
            return json.dumps({"success": False, "error": "AI API URL 未配置，请在设置页填写。"})

        try:
            payload = json.loads(payload_json)
        except Exception:
            return json.dumps({"success": False, "error": "payload 格式错误"})

        def _call():
            system_prompt = (
                "你是一个 Minecraft Java 整合包崩溃分析专家。"
                "请分析以下崩溃日志，指出可能的根本原因、可疑 mod 及建议操作。"
                "请用中文回答，结构清晰。"
            )
            user_parts = []
            for seg in payload.get("segments", []):
                user_parts.append(f"=== {seg['label']} ===\n{seg['content']}")
            user_parts.append(f"\n{payload.get('mod_list_context', '')}")
            user_message = "\n\n".join(user_parts)

            request_body = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                "max_tokens": 1500,
                "temperature": 0.3
            }
            data = json.dumps(request_body).encode("utf-8")

            # Normalize URL
            url = api_url
            if not url.endswith("/chat/completions"):
                if url.endswith("/"):
                    url = url + "v1/chat/completions"
                elif url.endswith("/v1"):
                    url = url + "/chat/completions"
                else:
                    url = url + "/v1/chat/completions"

            req = urllib.request.Request(
                url, data=data,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                    "User-Agent": "TCYClientUpdater/1.0"
                },
                method="POST"
            )
            try:
                with self._urlopen_with_policy(req, timeout=60, url=api_url) as resp:
                    result = json.loads(resp.read().decode("utf-8"))
                # Robust response parsing
                content = (
                    result.get("choices", [{}])[0].get("message", {}).get("content")
                    or result.get("choices", [{}])[0].get("text")
                    or str(result)
                )
                safe = json.dumps({"success": True, "content": content}, ensure_ascii=False)
            except Exception as e:
                safe = json.dumps({"success": False, "error": str(e)})

            if global_window:
                global_window.evaluate_js(f"onAiAnalysisResult({safe})")

        threading.Thread(target=_call, daemon=True).start()
        return json.dumps({"queued": True})

    def open_folder(self, folder_type):
        sub_path = "mods" if folder_type == "mods" else "config"
        target_dir = self._get_game_subdir(sub_path)
        try: os.startfile(target_dir)
        except: pass

    def _get_game_subdir(self, sub_path):

        """Resolve a subdirectory under the target version.

        Prefer .minecraft/versions layout; fallback to versions layout.
        """
        target_dir = os.path.join(self.game_root, ".minecraft", "versions", TARGET_VERSION_NAME, sub_path)
        if not os.path.exists(target_dir):
            target_dir = os.path.join(self.game_root, "versions", TARGET_VERSION_NAME, sub_path)
        os.makedirs(target_dir, exist_ok=True)
        return target_dir

    def _safe_backup_name(self, name):
        if not name or type(name) != str or not name.strip():
            return None
        n = name.strip()
        # Windows-safe, filesystem-safe backup label
        n = re.sub(r"[\\/:*?\"<>|]", "_", n)
        n = re.sub(r"\s+", " ", n).strip()
        if len(n) > 48:
            n = n[:48].strip()
        if not n:
            return None
        return n

    def list_config_subfolders(self):
        """Return selectable items under config root.

        Backward-compat note:
        - Historically returned a string[] of first-level folders.
        - Phase 07-04 extends it to return a dict with both folders and root-level files:
          {"folders": [...], "root_files": [...]}
        """
        config_root = self._get_game_subdir("config")
        folders = []
        root_files = []
        try:
            config_root_real = os.path.realpath(config_root)
            for entry in sorted(os.listdir(config_root), key=lambda x: x.lower()):
                full_path = os.path.join(config_root, entry)

                # hide internal backup folders
                if entry.startswith("_backup_"):
                    continue

                # Only allow first-level names
                if ("/" in entry) or ("\\" in entry) or (".." in entry):
                    continue

                # folders
                if os.path.isdir(full_path):
                    folders.append(entry)
                    continue

                # root-level files (exclude symlinks; ensure realpath stays inside config_root)
                if os.path.isfile(full_path) and (not os.path.islink(full_path)):
                    full_real = os.path.realpath(full_path)
                    if not (full_real == config_root_real or full_real.startswith(config_root_real + os.sep)):
                        continue
                    root_files.append(entry)
        except Exception as e:
            self.log(f"读取 config 可选项失败: {e}")

        return {"folders": folders, "root_files": root_files}

    def create_config_backup(self, name, selected_folders, selected_files=None):
        """Create a named backup from selected config items.

        Notes:
        - selected_folders are treated as *intended scope* (first-level folder names).
        - selected_files are root-level file names under config root.
        - If a selected folder/file is missing on disk, we DO NOT hard-fail. Instead we
          record it in manifest as warnings/missing_folders/missing_files.
        - Security boundary: all operations must remain under config root.
        """
        safe_name = self._safe_backup_name(name)
        if not safe_name:
            return {"success": False, "error": "备份名称不能为空"}

        if not isinstance(selected_folders, (list, tuple)):
            return {"success": False, "error": "目录范围参数不合法"}

        if selected_files is None:
            selected_files = []
        if not isinstance(selected_files, (list, tuple)):
            return {"success": False, "error": "文件范围参数不合法"}

        # sanitize + de-dup while preserving order
        cleaned = []
        seen = set()
        for x in selected_folders:
            if not isinstance(x, str):
                continue
            s = x.strip()
            if not s or s in seen:
                continue
            # no nested paths allowed
            if ("/" in s) or ("\\" in s) or (".." in s):
                continue
            cleaned.append(s)
            seen.add(s)

        # sanitize selected_files (must be single file name under config root)
        cleaned_files = []
        seen_files = set()
        for x in selected_files:
            if not isinstance(x, str):
                continue
            s = x.strip()
            if not s or s in seen_files:
                continue
            if ("/" in s) or ("\\" in s) or (".." in s):
                continue
            cleaned_files.append(s)
            seen_files.add(s)

        if not cleaned and not cleaned_files:
            return {"success": False, "error": "请至少选择一个 config 子目录或根目录文件"}

        config_root = self._get_game_subdir("config")

        ts = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        backup_id = f"_backup_{safe_name}_{ts}"
        backup_dir = os.path.join(config_root, backup_id)
        manifest_path = os.path.join(backup_dir, "manifest.json")

        try:
            os.makedirs(backup_dir, exist_ok=False)
        except FileExistsError:
            return {"success": False, "error": "备份目录已存在，请重试"}
        except Exception as e:
            return {"success": False, "error": f"创建备份目录失败: {e}"}

        file_count = 0
        missing_folders = []
        missing_files = []
        warnings = []

        try:
            config_root_real = os.path.realpath(config_root)
            backup_dir_real = os.path.realpath(backup_dir)
            if not (backup_dir_real == config_root_real or backup_dir_real.startswith(config_root_real + os.sep)):
                raise RuntimeError("备份目录路径校验失败")

            for folder in cleaned:
                src = os.path.join(config_root, folder)
                dst = os.path.join(backup_dir, folder)

                # Safety boundary: ensure dst stays under backup_dir, and src stays under config_root
                src_real = os.path.realpath(src)
                dst_real = os.path.realpath(dst)
                if not (src_real == config_root_real or src_real.startswith(config_root_real + os.sep)):
                    raise RuntimeError("路径校验失败（源目录不在 config 根目录内）")
                if not (dst_real == backup_dir_real or dst_real.startswith(backup_dir_real + os.sep)):
                    raise RuntimeError("路径校验失败（目标目录不在备份目录内）")

                if not os.path.exists(src):
                    # Missing on disk: represent as empty directory snapshot
                    os.makedirs(dst, exist_ok=True)
                    missing_folders.append(folder)
                    continue

                if not os.path.isdir(src):
                    warnings.append(f"已跳过非目录项: {folder}")
                    continue

                shutil.copytree(src, dst)
                # count files
                for _root, _dirs, files in os.walk(dst):
                    file_count += len(files)

            # root-level files
            for fn in cleaned_files:
                src = os.path.join(config_root, fn)
                dst = os.path.join(backup_dir, fn)

                src_real = os.path.realpath(src)
                dst_real = os.path.realpath(dst)
                if not (src_real == config_root_real or src_real.startswith(config_root_real + os.sep)):
                    raise RuntimeError("路径校验失败（源文件不在 config 根目录内）")
                if not (dst_real == backup_dir_real or dst_real.startswith(backup_dir_real + os.sep)):
                    raise RuntimeError("路径校验失败（目标文件不在备份目录内）")

                if not os.path.exists(src):
                    missing_files.append(fn)
                    continue

                if (not os.path.isfile(src)) or os.path.islink(src):
                    warnings.append(f"已跳过非普通文件: {fn}")
                    continue

                shutil.copy2(src, dst)
                try:
                    file_count += 1
                except Exception:
                    pass

            if missing_folders:
                warnings.append(f"已自动处理缺失目录并继续：{', '.join(missing_folders)}")
            if missing_files:
                warnings.append(f"已自动跳过缺失文件并继续：{', '.join(missing_files)}")

            manifest = {
                "id": backup_id,
                "name": safe_name,
                "created_at": datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
                "selected_folders": cleaned,
                "selected_files": cleaned_files,
                "file_count": file_count,
                "missing_folders": missing_folders,
                "missing_files": missing_files,
                "warnings": warnings
            }
            with open(manifest_path, 'w', encoding='utf-8') as f:
                json.dump(manifest, f, ensure_ascii=False, indent=2)

            self.log(f"已创建 config 备份: {backup_id} (folders={len(cleaned)}, root_files={len(cleaned_files)}, files={file_count})")
            if missing_folders:
                self.log(f"注意：备份时发现部分目录缺失，已按空目录快照处理：{', '.join(missing_folders)}")
            if missing_files:
                self.log(f"注意：备份时发现部分文件缺失，已跳过并继续：{', '.join(missing_files)}")

            return {"success": True, "backup": manifest}
        except Exception as e:
            # best-effort rollback
            try:
                shutil.rmtree(backup_dir, ignore_errors=True)
            except Exception:
                pass
            self.log(f"创建 config 备份失败: {e}")
            return {"success": False, "error": str(e)}

    def list_config_backups(self):
        """List available config backups (manifest-aware)."""
        config_root = self._get_game_subdir("config")
        backups = []
        try:
            for entry in os.listdir(config_root):
                if not entry.startswith("_backup_"):
                    continue
                bdir = os.path.join(config_root, entry)
                if not os.path.isdir(bdir):
                    continue
                manifest_path = os.path.join(bdir, "manifest.json")
                if not os.path.exists(manifest_path):
                    continue
                try:
                    with open(manifest_path, 'r', encoding='utf-8') as f:
                        manifest = json.load(f)
                    # Minimal shape enforcement
                    backups.append({
                        "id": manifest.get("id", entry),
                        "name": manifest.get("name", entry),
                        "created_at": manifest.get("created_at", ""),
                        "selected_folders": manifest.get("selected_folders", []),
                        "selected_files": manifest.get("selected_files", []),
                        "file_count": manifest.get("file_count", 0)
                    })
                except Exception:
                    continue
        except Exception as e:
            self.log(f"读取 config 备份列表失败: {e}")

        def _sort_key(x):
            return x.get("created_at", "")

        backups.sort(key=_sort_key, reverse=True)
        return backups

    def _resolve_config_backup_dir(self, backup_id):
        """Resolve a config backup directory safely.

        - Reject path traversal / absolute paths
        - Ensure resolved path stays under config root
        - Ensure manifest.json exists
        """
        if not isinstance(backup_id, str) or not backup_id.strip():
            return None, "backup_id 不合法"
        bid = backup_id.strip()
        # quick rejects
        if (".." in bid) or ("/" in bid) or ("\\" in bid):
            return None, "backup_id 含非法路径"
        if not bid.startswith("_backup_"):
            return None, "backup_id 不存在"

        config_root = self._get_game_subdir("config")
        backup_dir = os.path.join(config_root, bid)

        try:
            config_root_real = os.path.realpath(config_root)
            backup_dir_real = os.path.realpath(backup_dir)
            if not (backup_dir_real == config_root_real or backup_dir_real.startswith(config_root_real + os.sep)):
                return None, "backup_id 非法（路径穿越）"
        except Exception:
            return None, "backup_id 解析失败"

        if not os.path.isdir(backup_dir):
            return None, "备份不存在"

        manifest_path = os.path.join(backup_dir, "manifest.json")
        if not os.path.exists(manifest_path):
            return None, "备份清单不存在"

        return backup_dir, None

    def _load_config_backup_manifest(self, backup_id):
        backup_dir, err = self._resolve_config_backup_dir(backup_id)
        if err:
            return None, err
        manifest_path = os.path.join(backup_dir, "manifest.json")
        try:
            with open(manifest_path, 'r', encoding='utf-8') as f:
                manifest = json.load(f)
            # basic shape
            if not isinstance(manifest, dict):
                return None, "备份清单格式错误"
            return manifest, None
        except Exception as e:
            return None, f"读取备份清单失败: {e}"

    def _list_relative_files(self, root_dir):
        """List relative file paths under root_dir (files only), using '/' separators."""
        out = []
        for base, _dirs, files in os.walk(root_dir):
            for fn in files:
                abs_path = os.path.join(base, fn)
                try:
                    rel = os.path.relpath(abs_path, root_dir)
                except Exception:
                    continue
                rel = rel.replace("\\", "/")
                out.append(rel)
        return out

    def preview_config_restore(self, backup_id):
        """Preview what would change if restoring a config backup.

        Returns lists of relative paths (folder/file) under config root:
        - overwrite: exists both in current config and backup
        - add: only in backup
        - only_current: only in current config (would be removed for selected folders)
        """
        manifest, err = self._load_config_backup_manifest(backup_id)
        if err:
            return {"success": False, "error": err}

        selected_folders = manifest.get("selected_folders", [])
        if not isinstance(selected_folders, list):
            selected_folders = []

        selected_files = manifest.get("selected_files", [])
        if not isinstance(selected_files, list):
            selected_files = []

        config_root = self._get_game_subdir("config")
        backup_dir, err2 = self._resolve_config_backup_dir(backup_id)
        if err2:
            return {"success": False, "error": err2}

        # sanitize selected_folders (must be first-level folder names)
        cleaned = []
        for x in selected_folders:
            if not isinstance(x, str):
                continue
            s = x.strip()
            if not s or ("/" in s) or ("\\" in s) or (".." in s):
                continue
            cleaned.append(s)

        # sanitize selected_files (must be root-level file names)
        cleaned_files = []
        for x in selected_files:
            if not isinstance(x, str):
                continue
            s = x.strip()
            if not s or ("/" in s) or ("\\" in s) or (".." in s):
                continue
            cleaned_files.append(s)

        backup_set = set()
        current_set = set()
        for folder in cleaned:
            bsrc = os.path.join(backup_dir, folder)
            csrc = os.path.join(config_root, folder)

            # include the folder itself as a path marker
            backup_set.add(folder + "/")
            current_set.add(folder + "/")

            if os.path.isdir(bsrc):
                for rel in self._list_relative_files(bsrc):
                    backup_set.add(folder + "/" + rel)
            if os.path.isdir(csrc):
                for rel in self._list_relative_files(csrc):
                    current_set.add(folder + "/" + rel)

        # root-level files (relative path is just filename)
        for fn in cleaned_files:
            bfile = os.path.join(backup_dir, fn)
            cfile = os.path.join(config_root, fn)
            if os.path.isfile(bfile) and (not os.path.islink(bfile)):
                backup_set.add(fn)
            if os.path.isfile(cfile) and (not os.path.islink(cfile)):
                current_set.add(fn)

        overwrite = sorted(list(backup_set & current_set))
        add = sorted(list(backup_set - current_set))
        only_current = sorted(list(current_set - backup_set))

        return {
            "success": True,
            "backup": {
                "id": manifest.get("id", backup_id),
                "name": manifest.get("name", backup_id),
                "created_at": manifest.get("created_at", ""),
                "selected_folders": cleaned,
                "selected_files": cleaned_files,
                "file_count": manifest.get("file_count", 0)
            },
            "preview": {
                "overwrite": overwrite,
                "add": add,
                "only_current": only_current,
                "counts": {
                    "overwrite": len(overwrite),
                    "add": len(add),
                    "only_current": len(only_current)
                }
            }
        }

    def restore_config_backup(self, backup_id, confirmed):
        """Restore a config backup with mandatory confirmation and pre-restore safety backup."""
        if not confirmed:
            return {"success": False, "error": "需要二次确认后才能执行还原"}

        manifest, err = self._load_config_backup_manifest(backup_id)
        if err:
            return {"success": False, "error": err}

        selected_folders = manifest.get("selected_folders", [])
        if not isinstance(selected_folders, list):
            selected_folders = []

        selected_files = manifest.get("selected_files", [])
        if not isinstance(selected_files, list):
            selected_files = []

        # sanitize selected_folders (must be first-level folder names)
        cleaned = []
        for x in selected_folders:
            if not isinstance(x, str):
                continue
            s = x.strip()
            if not s or ("/" in s) or ("\\" in s) or (".." in s):
                continue
            cleaned.append(s)

        # sanitize selected_files (must be root-level file names)
        cleaned_files = []
        for x in selected_files:
            if not isinstance(x, str):
                continue
            s = x.strip()
            if not s or ("/" in s) or ("\\" in s) or (".." in s):
                continue
            cleaned_files.append(s)

        if not cleaned and not cleaned_files:
            return {"success": False, "error": "备份范围为空，无法还原"}

        # pre-restore backup (include both folders and root-level files)
        pre_name = f"pre-restore_{manifest.get('name') or 'backup'}"
        pre_res = self.create_config_backup(pre_name, cleaned, cleaned_files)
        if not isinstance(pre_res, dict) or not pre_res.get("success"):
            return {"success": False, "error": f"创建 pre-restore 备份失败: {pre_res.get('error') if isinstance(pre_res, dict) else pre_res}"}

        config_root = self._get_game_subdir("config")
        backup_dir, err2 = self._resolve_config_backup_dir(backup_id)
        if err2:
            return {"success": False, "error": err2, "pre_restore_backup": pre_res.get("backup")}

        # Controlled restore: stage to temp dir then replace
        tmp_root = os.path.join(config_root, f"_restore_tmp_{int(time.time())}")
        try:
            os.makedirs(tmp_root, exist_ok=False)
        except FileExistsError:
            return {"success": False, "error": "还原临时目录已存在，请重试", "pre_restore_backup": pre_res.get("backup")}
        except Exception as e:
            return {"success": False, "error": f"创建还原临时目录失败: {e}", "pre_restore_backup": pre_res.get("backup")}

        warnings = []

        try:
            config_real = os.path.realpath(config_root)
            backup_real = os.path.realpath(backup_dir)
            tmp_real = os.path.realpath(tmp_root)
            if not (tmp_real == config_real or tmp_real.startswith(config_real + os.sep)):
                raise RuntimeError("路径校验失败（临时目录不在 config 根目录内）")

            # Stage selected folders
            for folder in cleaned:
                src_folder = os.path.join(backup_dir, folder)
                staged = os.path.join(tmp_root, folder)

                # Safety: ensure staged path stays under tmp_root
                staged_real = os.path.realpath(staged)
                if not (staged_real == tmp_real or staged_real.startswith(tmp_real + os.sep)):
                    raise RuntimeError("路径校验失败（staging 目录不在临时目录内）")

                if not os.path.exists(src_folder):
                    # Backup snapshot may represent missing folder as empty
                    os.makedirs(staged, exist_ok=True)
                    warnings.append(f"备份中目录缺失，已按空目录还原：{folder}")
                    continue

                if not os.path.isdir(src_folder):
                    os.makedirs(staged, exist_ok=True)
                    warnings.append(f"备份中范围项不是目录，已跳过并按空目录处理：{folder}")
                    continue

                src_real = os.path.realpath(src_folder)
                if not (src_real == backup_real or src_real.startswith(backup_real + os.sep)):
                    raise RuntimeError("路径校验失败（源目录不在备份根目录内）")

                shutil.copytree(src_folder, staged)

            # Stage selected root-level files
            for fn in cleaned_files:
                src_file = os.path.join(backup_dir, fn)
                staged_file = os.path.join(tmp_root, fn)

                staged_real = os.path.realpath(staged_file)
                if not (staged_real == tmp_real or staged_real.startswith(tmp_real + os.sep)):
                    raise RuntimeError("路径校验失败（staging 文件不在临时目录内）")

                if not os.path.exists(src_file):
                    warnings.append(f"备份中根目录文件缺失，已跳过：{fn}")
                    continue

                if (not os.path.isfile(src_file)) or os.path.islink(src_file):
                    warnings.append(f"备份中根目录文件不是普通文件，已跳过：{fn}")
                    continue

                src_real = os.path.realpath(src_file)
                if not (src_real == backup_real or src_real.startswith(backup_real + os.sep)):
                    raise RuntimeError("路径校验失败（源文件不在备份根目录内）")

                os.makedirs(os.path.dirname(staged_file), exist_ok=True)
                shutil.copy2(src_file, staged_file)

            # Replace current folders atomically-ish (per folder)
            for folder in cleaned:
                current_folder = os.path.join(config_root, folder)
                staged = os.path.join(tmp_root, folder)

                # safety: ensure target stays under config root
                current_real = os.path.realpath(current_folder)
                if not (current_real == config_real or current_real.startswith(config_real + os.sep)):
                    raise RuntimeError("路径校验失败（目标不在 config 根目录内）")

                # Ensure destination parent exists (missing target folders should not fail)
                os.makedirs(os.path.dirname(current_folder), exist_ok=True)

                # remove existing then move staged into place
                if os.path.exists(current_folder):
                    shutil.rmtree(current_folder)
                shutil.move(staged, current_folder)

            # Replace current root-level files
            for fn in cleaned_files:
                current_file = os.path.join(config_root, fn)
                staged_file = os.path.join(tmp_root, fn)

                current_real = os.path.realpath(current_file)
                if not (current_real == config_real or current_real.startswith(config_real + os.sep)):
                    raise RuntimeError("路径校验失败（目标文件不在 config 根目录内）")

                # Ensure destination parent exists
                os.makedirs(os.path.dirname(current_file), exist_ok=True)

                # only restore when backup has the file staged
                if not os.path.exists(staged_file):
                    continue

                if os.path.exists(current_file):
                    try:
                        os.remove(current_file)
                    except Exception:
                        # fallback: if it's unexpectedly a folder, remove tree
                        shutil.rmtree(current_file, ignore_errors=True)
                shutil.move(staged_file, current_file)

            self.log(f"config 还原完成: backup_id={backup_id}, pre_restore={pre_res.get('backup', {}).get('id')}")
            if warnings:
                for w in warnings:
                    self.log(f"[还原提示] {w}")

            self._add_activity_log("config_restore", {
                "backup_id": backup_id,
                "backup_name": manifest.get("name", ""),
                "selected_folders": cleaned,
                "selected_files": cleaned_files,
                "pre_restore_backup_id": pre_res.get("backup", {}).get("id", ""),
                "warnings": warnings
            })

            result = {
                "success": True,
                "backup_id": backup_id,
                "pre_restore_backup": pre_res.get("backup"),
                "restored_folders": cleaned,
                "restored_files": cleaned_files
            }
            if warnings:
                result["warnings"] = warnings
            return result
        except Exception as e:
            self.log(f"config 还原失败: {e}")
            return {"success": False, "error": str(e), "pre_restore_backup": pre_res.get("backup")}
        finally:
            try:
                shutil.rmtree(tmp_root, ignore_errors=True)
            except Exception:
                pass

    def open_shortcut_folder(self, folder_type):
        paths = {
            "resourcepacks": "resourcepacks",
            "shaderpacks": "shaderpacks",
            "screenshots": "screenshots"
        }
        if folder_type in paths:
            target_dir = os.path.join(self.game_root, ".minecraft", "versions", TARGET_VERSION_NAME, paths[folder_type])
            if not os.path.exists(target_dir):
                target_dir = os.path.join(self.game_root, "versions", TARGET_VERSION_NAME, paths[folder_type])
            os.makedirs(target_dir, exist_ok=True)
            try: os.startfile(target_dir)
            except Exception as e: log_error(f"打开文件夹失败: {e}")

    def save_mod_preset(self, name):
        if not name or type(name) != str or not name.strip():
            return json.dumps({"success": False, "error": "预设名不能为空"})
        try:
            # 获取当前模组状态
            mods_json = self.get_mods_metadata()
            mods_data = json.loads(mods_json) if isinstance(mods_json, str) else mods_json

            # 使用字典存储文件名和是否启用状态
            mods_snapshot = {}
            for mod in mods_data:
                mods_snapshot[mod['filename']] = mod['enabled']

            # 构建预设对象
            preset = {
                "name": name.strip(),
                "created": time.strftime('%Y-%m-%d %H:%M:%S'),
                "mods": mods_snapshot
            }

            # 加载并更新预设列表，如果名存在则替换
            cfg = self.cfg_mgr.load_config()
            presets = cfg.get("mod_presets", [])
            presets = [p for p in presets if p.get("name") != preset["name"]]
            presets.append(preset)
            self.cfg_mgr.save_config({"mod_presets": presets})
            self.log(f"成功保存模组预设: {preset['name']}，包含 {len(mods_snapshot)} 个模组")
            return json.dumps({"success": True})
        except Exception as e:
            self.log(f"保存模组预设失败: {e}")
            return json.dumps({"success": False, "error": str(e)})

    def load_mod_preset(self, name):
        if not name:
            return json.dumps({"success": False, "error": "未提供预设名"})
        try:
            cfg = self.cfg_mgr.load_config()
            presets = cfg.get("mod_presets", [])
            preset = next((p for p in presets if p.get("name") == name), None)

            if not preset:
                return json.dumps({"success": False, "error": f"预设 '{name}' 不存在"})

            # 定位到 mods 目录
            mods_dir = os.path.join(self.game_root, ".minecraft", "versions", TARGET_VERSION_NAME, "mods")
            if not os.path.exists(mods_dir):
                mods_dir = os.path.join(self.game_root, "versions", TARGET_VERSION_NAME, "mods")
                if not os.path.exists(mods_dir):
                     return json.dumps({"success": False, "error": "找不到 mods 目录"})

            changed_count = 0
            for filename, should_be_enabled in preset["mods"].items():
                # 安全检查，防止路径穿越
                if ".." in filename:
                    continue

                # 确定可能存在的文件名 (启用或禁用状态)
                if filename.endswith(".disabled"):
                    base_name = filename[:-9]
                    enabled_name = base_name
                    disabled_name = filename
                else:
                    base_name = filename
                    enabled_name = filename
                    disabled_name = filename + ".disabled"

                enabled_path = os.path.join(mods_dir, enabled_name)
                disabled_path = os.path.join(mods_dir, disabled_name)

                # 检查文件当前状态
                is_currently_enabled = os.path.exists(enabled_path)
                is_currently_disabled = os.path.exists(disabled_path)

                # 如果文件根本不存在跳过 (可能是更新删除了，或者用户手动删除了)
                if not is_currently_enabled and not is_currently_disabled:
                    continue

                # 需要启用，但当前是禁用状态
                if should_be_enabled and is_currently_disabled and not is_currently_enabled:
                    os.rename(disabled_path, enabled_path)
                    changed_count += 1
                # 需要禁用，但当前是启用状态
                elif not should_be_enabled and is_currently_enabled and not is_currently_disabled:
                    os.rename(enabled_path, disabled_path)
                    changed_count += 1

            self.log(f"成功加载模组预设: {name}，更改了 {changed_count} 个模组状态")
            self._add_activity_log("preset_load", {"preset_name": name, "changed_count": changed_count})
            return json.dumps({"success": True})
        except Exception as e:
            self.log(f"加载模组预设失败: {e}")
            return json.dumps({"success": False, "error": str(e)})

    def delete_mod_preset(self, name):
        if not name:
            return json.dumps({"success": False, "error": "未提供预设名"})
        try:
            cfg = self.cfg_mgr.load_config()
            presets = cfg.get("mod_presets", [])
            initial_len = len(presets)
            presets = [p for p in presets if p.get("name") != name]

            if len(presets) == initial_len:
                return json.dumps({"success": False, "error": f"预设 '{name}' 不存在"})

            self.cfg_mgr.save_config({"mod_presets": presets})
            self.log(f"成功删除模组预设: {name}")
            return json.dumps({"success": True})
        except Exception as e:
            self.log(f"删除模组预设失败: {e}")
            return json.dumps({"success": False, "error": str(e)})

    def export_mod_preset(self, name):
        """将指定预设导出为 JSON 文件"""
        if not name or type(name) != str or not name.strip():
            return json.dumps({"success": False, "error": "未提供预设名"})
        try:
            cfg = self.cfg_mgr.load_config()
            presets = cfg.get("mod_presets", [])
            preset = next((p for p in presets if p.get("name") == name), None)

            if not preset:
                return json.dumps({"success": False, "error": f"预设 '{name}' 不存在"})

            if global_window:
                save_path = global_window.create_file_dialog(
                    webview.SAVE_DIALOG,
                    save_filename=f'{name}.json',
                    file_types=('JSON files (*.json)', 'All files (*.*)')
                )
                if not save_path:
                    return json.dumps({"success": False, "error": "已取消导出"})

                dest = save_path if isinstance(save_path, str) else save_path[0]
                with open(dest, 'w', encoding='utf-8') as f:
                    json.dump(preset, f, ensure_ascii=False, indent=2)

                self.log(f"成功导出模组预设: {name} -> {dest}")
                return json.dumps({"success": True, "path": dest})
            else:
                return json.dumps({"success": False, "error": "窗口未初始化"})
        except Exception as e:
            self.log(f"导出模组预设失败: {e}")
            return json.dumps({"success": False, "error": str(e)})

    def import_mod_preset(self):
        """从 JSON 文件导入模组预设"""
        try:
            if not global_window:
                return json.dumps({"success": False, "error": "窗口未初始化"})

            result = global_window.create_file_dialog(
                webview.OPEN_DIALOG,
                allow_multiple=False,
                file_types=('JSON files (*.json)', 'All files (*.*)')
            )
            if not result:
                return json.dumps({"success": False, "error": "已取消导入"})

            file_path = result[0] if isinstance(result, (tuple, list)) else result

            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except json.JSONDecodeError:
                return json.dumps({"success": False, "error": "文件不是有效的 JSON 格式"})

            # 验证数据结构
            if not isinstance(data, dict):
                return json.dumps({"success": False, "error": "文件格式无效：顶层必须是 JSON 对象"})

            if "name" not in data or not isinstance(data["name"], str) or not data["name"].strip():
                return json.dumps({"success": False, "error": "文件格式无效：缺少有效的 name 字段"})

            if "mods" not in data or not isinstance(data["mods"], dict):
                return json.dumps({"success": False, "error": "文件格式无效：缺少有效的 mods 字段"})

            for key, val in data["mods"].items():
                if not isinstance(key, str):
                    return json.dumps({"success": False, "error": "文件格式无效：mods 键必须为字符串"})
                if not isinstance(val, bool):
                    return json.dumps({"success": False, "error": "文件格式无效：mods 值必须为布尔类型"})
                if ".." in key:
                    return json.dumps({"success": False, "error": "文件格式无效：mod 文件名包含非法字符"})

            # 构建安全的预设对象（只保留允许的字段）
            preset = {
                "name": data["name"].strip(),
                "created": data.get("created", time.strftime('%Y-%m-%d %H:%M:%S')),
                "mods": data["mods"]
            }

            # 加载并更新预设列表，同名则替换
            cfg = self.cfg_mgr.load_config()
            presets = cfg.get("mod_presets", [])
            presets = [p for p in presets if p.get("name") != preset["name"]]
            presets.append(preset)
            self.cfg_mgr.save_config({"mod_presets": presets})

            self.log(f"成功导入模组预设: {preset['name']}")
            return json.dumps({"success": True, "name": preset["name"]})
        except json.JSONDecodeError:
            return json.dumps({"success": False, "error": "文件不是有效的 JSON 格式"})
        except Exception as e:
            self.log(f"导入模组预设失败: {e}")
            return json.dumps({"success": False, "error": str(e)})

    def toggle_mod(self, filename):
        if ".." in filename:
            return {"success": False, "error": "Invalid filename"}

        target_path = os.path.join(self.game_root, ".minecraft", "versions", TARGET_VERSION_NAME, "mods", filename)
        if not os.path.exists(target_path):
             target_path = os.path.join(self.game_root, "versions", TARGET_VERSION_NAME, "mods", filename)

        if not os.path.exists(target_path) or not os.path.isfile(target_path):
            return {"success": False, "error": "Mod file not found"}

        try:
            if filename.endswith(".jar"):
                new_path = target_path + ".disabled"
                os.rename(target_path, new_path)
                # 原来直接 return，改为先记录日志再返回
                self._add_activity_log("mod_toggle", {"mod_name": filename, "action": "disabled"})
                return {"success": True}
            elif filename.endswith(".jar.disabled"):
                new_path = target_path[:-9] # len(".disabled") is 9
                os.rename(target_path, new_path)
                self._add_activity_log("mod_toggle", {"mod_name": filename, "action": "enabled"})
                return {"success": True}
            else:
                return {"success": False, "error": "Unknown mod extension"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def batch_set_mod_enabled(self, operations):
        """批量设置 mod 启用/禁用状态。operations: [{filename, target_enabled}, ...]"""
        import json as _json
        try:
            ops = _json.loads(operations) if isinstance(operations, str) else operations
        except Exception:
            return {"success": False, "error": "Invalid operations format"}

        # 解析 mods 目录
        mods_dir = os.path.join(self.game_root, ".minecraft", "versions", TARGET_VERSION_NAME, "mods")
        if not os.path.isdir(mods_dir):
            mods_dir = os.path.join(self.game_root, "versions", TARGET_VERSION_NAME, "mods")
        if not os.path.isdir(mods_dir):
            return {"success": False, "error": "Mods directory not found"}

        results = []
        succeeded = 0
        failed = 0

        for op in ops:
            fn = op.get("filename", "")
            target_enabled = op.get("target_enabled", True)

            if ".." in fn:
                results.append({"filename": fn, "ok": False, "error": "非法文件名"})
                failed += 1
                continue

            # 解析 enabled/disabled 两种可能的文件名
            if fn.endswith(".jar.disabled"):
                enabled_name = fn[:-9]  # 去掉 .disabled
                disabled_name = fn
            elif fn.endswith(".jar"):
                enabled_name = fn
                disabled_name = fn + ".disabled"
            else:
                results.append({"filename": fn, "ok": False, "error": "未知文件扩展名"})
                failed += 1
                continue

            enabled_path = os.path.join(mods_dir, enabled_name)
            disabled_path = os.path.join(mods_dir, disabled_name)

            try:
                if target_enabled:
                    if os.path.exists(enabled_path):
                        results.append({"filename": fn, "ok": True, "error": None})  # 已启用
                        succeeded += 1
                    elif os.path.exists(disabled_path):
                        os.rename(disabled_path, enabled_path)
                        results.append({"filename": fn, "ok": True, "error": None})
                        succeeded += 1
                    else:
                        results.append({"filename": fn, "ok": False, "error": "文件不存在"})
                        failed += 1
                else:
                    if os.path.exists(disabled_path):
                        results.append({"filename": fn, "ok": True, "error": None})  # 已禁用
                        succeeded += 1
                    elif os.path.exists(enabled_path):
                        os.rename(enabled_path, disabled_path)
                        results.append({"filename": fn, "ok": True, "error": None})
                        succeeded += 1
                    else:
                        results.append({"filename": fn, "ok": False, "error": "文件不存在"})
                        failed += 1
            except Exception as e:
                results.append({"filename": fn, "ok": False, "error": str(e)})
                failed += 1

        total = len(ops)
        action = "batch_enable" if all(op.get("target_enabled") for op in ops) else \
                 "batch_disable" if not any(op.get("target_enabled") for op in ops) else "batch_mixed"
        self._add_activity_log("mod_batch_toggle", {
            "action": action, "total": total, "succeeded": succeeded, "failed": failed
        })

        return {"success": True, "results": results, "summary": {"total": total, "succeeded": succeeded, "failed": failed}}

    def delete_file(self, folder_type, relative_path):
        if folder_type != 'mods': return False
        try:
            target_path = self._resolve_game_relative_path("mods", relative_path)
            if os.path.exists(target_path) and os.path.isfile(target_path):
                os.remove(target_path)
                return True
        except Exception:
            pass
        return False
    def open_file(self, folder_type, relative_path):
        if folder_type != 'config': return
        try:
            target_path = self._resolve_game_relative_path("config", relative_path)
        except ValueError:
            return
        if os.path.exists(target_path):
            try: os.startfile(target_path)
            except: pass

    def export_log(self):
        """将日志文件复制到用户选择的位置"""
        try:
            if global_window:
                save_path = global_window.create_file_dialog(
                    webview.SAVE_DIALOG,
                    save_filename='TCYUpdater_log.txt',
                    file_types=('Text files (*.txt)', 'All files (*.*)')
                )
                if save_path:
                    dest = save_path if isinstance(save_path, str) else save_path[0]
                    shutil.copy2(log_file_path, dest)
                    self.log(f"日志已导出到: {dest}")
                    return True
        except Exception as e:
            self.log(f"导出日志失败: {e}")
        return False

    # === 多源轮询获取 JSON 的通用方法 ===

    def _fetch_single_json_url(self, url):
        started_at = time.time()
        try:
            req = urllib.request.Request(
                url,
                headers={'User-Agent': 'TCYClientUpdater/1.0'}
            )
            with self._urlopen_with_policy(req, timeout=8, url=url) as resp:
                data = json.loads(resp.read().decode('utf-8'))
            return {
                "ok": True,
                "data": data,
                "elapsed_ms": int((time.time() - started_at) * 1000),
            }
        except Exception as e:
            return {
                "ok": False,
                "error": str(e),
                "elapsed_ms": int((time.time() - started_at) * 1000),
                "timeout": self._is_network_timeout_error(e),
            }

    def _fetch_json_from_urls(self, url_list, fetch_label="版本信息"):
        """
        检查 url_list 中的每个地址，全部都尝试，收集所有结果。
        返回 (data, success_urls, failed_urls)
        data 取第一个成功的结果，None 表示全部失败。
        """
        urls = list(url_list or [])
        if not urls:
            return None, [], []

        max_workers = bounded_worker_count(len(urls), JSON_FETCH_MAX_WORKERS)
        started_at = time.time()
        self.log(f"[轮询阶段] {fetch_label}：开始检查 {len(urls)} 个地址（并发={max_workers}）")
        results_by_url = {}
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(self._fetch_single_json_url, url): url
                for url in urls
            }
            for future in as_completed(futures):
                url = futures[future]
                try:
                    result = future.result()
                except Exception as e:
                    result = {
                        "ok": False,
                        "error": str(e),
                        "elapsed_ms": None,
                        "timeout": self._is_network_timeout_error(e),
                    }
                results_by_url[url] = result
                elapsed_ms = result.get("elapsed_ms")
                elapsed_text = f"{elapsed_ms}ms" if isinstance(elapsed_ms, int) else "unknown"
                if result.get("ok"):
                    self.log(f"[轮询][{fetch_label}][OK][{elapsed_text}] {url}")
                else:
                    status = "TIMEOUT" if result.get("timeout") else "FAIL"
                    self.log(f"[轮询][{fetch_label}][{status}][{elapsed_text}] {url} -> {result.get('error', 'unknown')}")

        first_data, success_urls, failed_urls = summarize_url_fetch_results(urls, results_by_url)
        timing_stats = summarize_elapsed_ms([item.get("elapsed_ms") for item in results_by_url.values()])
        total_elapsed_ms = int((time.time() - started_at) * 1000)
        if timing_stats["count"] > 0:
            stats_text = f"{timing_stats['min_ms']}/{timing_stats['avg_ms']}/{timing_stats['max_ms']}ms"
        else:
            stats_text = "n/a"
        self.log(
            f"[轮询阶段] {fetch_label}：完成，成功 {len(success_urls)}/{len(urls)}，失败 {len(failed_urls)}，"
            f"总耗时 {total_elapsed_ms}ms，URL耗时(min/avg/max)={stats_text}"
        )
        return first_data, success_urls, failed_urls

    def _build_url_list(self, default_url, github_url, custom_url=""):
        """
        构建轮询列表：自定义URL（若有）> 默认URL > GitHub原始URL > GitHub加速URL
        """
        mirror = self.cfg_mgr.config.get("mirror_prefix", DEFAULT_MIRROR_PREFIX).strip()
        return build_url_list(default_url, github_url, custom_url, mirror)

    # === 更新器自我更新逻辑 ===

    def check_launcher_self_update(self):
        """
        检查更新器自身是否需要更新，多源轮询 Updater-latest.json
        仅用于在 _check_update_thread 外单独调用的场景（目前未使用）
        """
        custom_url = self.cfg_mgr.config.get("custom_updater_url", "").strip()
        url_list = self._build_url_list(DEFAULT_UPDATER_JSON_URL, GITHUB_UPDATER_JSON_URL, custom_url)
        launcher_info, success_urls, failed_urls = self._fetch_json_from_urls(url_list, fetch_label="更新器版本")
        return launcher_info, success_urls, failed_urls

    def perform_self_update(self, url, version):
        """下载新版 EXE 并执行替换脚本（修复：正确关闭自身进程）"""
        import subprocess
        try:
            self.log(f"正在下载新版更新器: {version}...")

            launcher_dir = os.path.dirname(os.path.abspath(sys.executable))
            current_exe_path = os.path.abspath(sys.executable)
            temp_download_path = os.path.join(launcher_dir, "TCY-Client-Updater.new")
            new_exe_name = f"TCYClientUpdater-{version}.exe"
            new_exe_path = os.path.join(launcher_dir, new_exe_name)
            current_pid = os.getpid()
            bat_script_path = os.path.join(launcher_dir, f"update_self_{current_pid}.bat")
            status_log_path = os.path.join(launcher_dir, "self_update_status.log")
            launch_log_path = os.path.join(launcher_dir, "self_update_launch.log")

            def report(block_num, block_size, total_size):
                if total_size > 0:
                    percent = min(100, int(block_num * block_size * 100 / total_size))
                    if percent % 10 == 0: self.log(f"自更新下载中... {percent}%")

            self._download_url_to_path(url, temp_download_path, progress_cb=report, connect_timeout=15, stall_timeout=20)
            if not os.path.exists(temp_download_path):
                raise FileNotFoundError(f"未找到已下载的临时更新文件: {temp_download_path}")
            temp_size = os.path.getsize(temp_download_path)
            self.log(f"自更新临时文件已下载: {temp_download_path} ({temp_size} bytes)")

            batch_script = build_self_update_batch_script(
                current_exe_path,
                temp_download_path,
                new_exe_path,
                current_pid,
                status_log_path,
            )
            with open(bat_script_path, "w", encoding="gbk", newline="\r\n") as f:
                f.write(batch_script)
            if not os.path.exists(bat_script_path):
                raise FileNotFoundError(f"未找到已写入的自更新脚本: {bat_script_path}")

            launch_note = (
                f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] version={version} "
                f"old_exe={current_exe_path} temp={temp_download_path} "
                f"new_exe={new_exe_path} bat={bat_script_path} status_log={status_log_path}\n"
            )
            try:
                with open(launch_log_path, "a", encoding="utf-8") as f:
                    f.write(launch_note)
            except Exception:
                pass

            self.log(f"下载完成，准备重启至: {new_exe_path}")
            self.log(f"自更新脚本路径: {bat_script_path}")
            self.log(f"自更新状态日志路径: {status_log_path}")
            self.log(f"自更新启动记录路径: {launch_log_path}")

            # 使用 subprocess.Popen 让 bat 脱离父进程
            CREATE_NEW_PROCESS_GROUP = 0x00000200
            DETACHED_PROCESS = 0x00000008
            proc = subprocess.Popen(
                ["cmd.exe", "/c", bat_script_path],
                cwd=launcher_dir,
                creationflags=CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS,
                close_fds=True,
                shell=False
            )
            self.log(f"已启动自更新脚本进程，PID={getattr(proc, 'pid', 'unknown')}")
            self.log("若更新未完成，请先检查 self_update_status.log；若该文件不存在，再检查 self_update_launch.log 与 launcher_debug.log。")
            flush_log_handlers()

            # 退出当前进程
            if global_window:
                global_window.destroy()
            os._exit(0)

        except Exception as e:
            self.log(f"自我更新失败: {e}")
            log_error(f"自我更新异常: {traceback.format_exc()}")
            if global_window:
                global_window.evaluate_js(f"alert('自我更新失败: {str(e)}')")

    # === 在线更新相关逻辑 (序列化) ===

    def get_local_version(self):
        return self.cfg_mgr.config.get("current_version", INITIAL_VERSION)

    def record_skipped_version(self, version):
        self.add_skipped_version(version)

    def check_online_update(self, startup_mode=False):
        threading.Thread(target=self._check_update_thread, args=(startup_mode,)).start()

    def check_online_update_manual(self):
        self.check_online_update(startup_mode=True)
        return {"success": True}

    def _show_update_island_loading(self, message):
        if not global_window:
            return
        try:
            global_window.evaluate_js(f"showUpdateIslandLoading({json.dumps(message, ensure_ascii=False)})")
        except Exception:
            pass

    def _check_update_thread(self, startup_mode=False):
        self.log("正在从多个来源获取版本信息，请稍候...")
        self._show_update_island_loading("正在并发检查客户端版本和更新器版本…")

        # === 构建轮询列表 ===
        custom_latest = self.cfg_mgr.config.get("custom_latest_url", "").strip()
        latest_urls = self._build_url_list(DEFAULT_LATEST_JSON_URL, GITHUB_LATEST_JSON_URL, custom_latest)

        custom_updater = self.cfg_mgr.config.get("custom_updater_url", "").strip()
        updater_urls = self._build_url_list(DEFAULT_UPDATER_JSON_URL, GITHUB_UPDATER_JSON_URL, custom_updater)

        # === 全部检查，收集每个地址的结果 ===
        fetch_results = {}
        with ThreadPoolExecutor(max_workers=2) as executor:
            future_map = {
                executor.submit(self._fetch_json_from_urls, latest_urls, "客户端版本"): {
                    "type": "client",
                    "label": "客户端版本",
                    "started_at": time.time(),
                },
                executor.submit(self._fetch_json_from_urls, updater_urls, "更新器版本"): {
                    "type": "updater",
                    "label": "更新器版本",
                    "started_at": time.time(),
                },
            }
            completed_types = set()
            for future in as_completed(future_map):
                future_info = future_map[future]
                fetch_type = future_info["type"]
                fetch_label = future_info["label"]
                try:
                    fetch_results[fetch_type] = future.result()
                except Exception as e:
                    self.log(f"[轮询] {fetch_label}检查异常: {e}")
                    fetch_results[fetch_type] = (None, [], [])
                group_elapsed_ms = int((time.time() - future_info["started_at"]) * 1000)
                self.log(f"[轮询阶段] {fetch_label}任务完成，耗时 {group_elapsed_ms}ms")

                completed_types.add(fetch_type)
                pending_types = {"client", "updater"} - completed_types
                if pending_types:
                    done_labels = []
                    if "client" in completed_types:
                        done_labels.append("客户端版本")
                    if "updater" in completed_types:
                        done_labels.append("更新器版本")

                    pending_labels = []
                    if "client" in pending_types:
                        pending_labels.append("客户端版本")
                    if "updater" in pending_types:
                        pending_labels.append("更新器版本")

                    self._show_update_island_loading(
                        f"{'、'.join(done_labels)}已完成，正在检查{'、'.join(pending_labels)}…"
                    )

            client_data, client_ok_urls, client_fail_urls = fetch_results.get("client", (None, [], []))
            updater_data, updater_ok_urls, updater_fail_urls = fetch_results.get("updater", (None, [], []))

        # === 全部失败则不继续 ===
        if client_data is None and updater_data is None:
            self.log("所有版本信息来源均获取失败")
            if startup_mode and global_window:
                try:
                    global_window.evaluate_js("showUpdateIslandIdle('版本检测失败，点我重试', 'retry')")
                except Exception:
                    pass
            return

        # === 处理更新器自身版本 ===
        updater_info_for_modal = None
        if updater_data:
            remote_ver = updater_data.get("version", "0.0.0")
            if is_version_newer(remote_ver, LAUNCHER_INTERNAL_VERSION):
                updater_info_for_modal = {
                    "remote_ver": remote_ver,
                    "desc": updater_data.get("desc", "无"),
                    "url": updater_data.get("url", "")
                }

        # === 缓存更新历史到本地 (供更新日志时间线视图使用) ===
        if client_data and 'history' in client_data and isinstance(client_data['history'], list):
            self.cfg_mgr.save_config({"cached_history": client_data['history']})
            self.log(f"已缓存 {len(client_data['history'])} 条更新历史到本地")

        # === 处理客户端更新队列 ===
        updates_queue = []
        if client_data:
            local_ver = self.get_local_version()
            original_skipped = self.cfg_mgr.config.get("skipped_versions", [])
            if 'history' in client_data and isinstance(client_data['history'], list):
                updates_queue, cleaned_skipped = select_pending_updates(
                    client_data['history'],
                    local_ver,
                    original_skipped,
                )
                if cleaned_skipped != sorted(set(original_skipped), key=version_sort_key):
                    self.cfg_mgr.save_config({"skipped_versions": cleaned_skipped})

        # === 将版本信息发给前端展示 ===
        modal_payload = {
            "updates": updates_queue,
            "updater_info": updater_info_for_modal,
            "local_ver": self.get_local_version(),
            "launcher_ver": LAUNCHER_INTERNAL_VERSION
        }

        if global_window:
            if startup_mode:
                updater_found = bool(updater_info_for_modal)
                client_found = bool(updates_queue)
                if updater_found or client_found:
                    island_text_parts = []
                    if updater_found:
                        island_text_parts.append("检测到更新器有更新")
                    if client_found:
                        island_text_parts.append("检测到客户端版本有更新")
                    island_text = " / ".join(island_text_parts)
                    try:
                        global_window.evaluate_js(f"setPendingVersionModal({json.dumps(modal_payload)})")
                        global_window.evaluate_js(f"showUpdateIslandReady({json.dumps(island_text)})")
                    except Exception:
                        pass
                else:
                    try:
                        global_window.evaluate_js("hideUpdateIslandSoon('当前已是最新版本')")
                    except Exception:
                        pass
            else:
                global_window.evaluate_js(f"setPendingVersionModal({json.dumps(modal_payload)})")

    # ===批量更新执行逻辑 ===
    # 前端会发回一个列表：[{version:..., url:..., ...}, {...}] (用户勾选的 + 强制的)
    def _normalize_update_list(self, update_list_json):
        updates = json.loads(update_list_json)
        if not isinstance(updates, list):
            raise ValueError("更新列表格式错误")
        return updates

    def _extract_ordered_versions(self, updates):
        versions = []
        for item in updates:
            if isinstance(item, dict):
                versions.append(str(item.get('version', '')))
            else:
                versions.append('')
        return versions

    def _extract_affected_paths(self, updates):
        affected = set()

        def collect(path_like):
            if not isinstance(path_like, str):
                return
            normalized = path_like.replace('\\', '/').strip('/')
            if not normalized:
                return
            top = normalized.split('/')[0].strip()
            if top:
                affected.add(f"{top}/")

        for item in updates:
            if not isinstance(item, dict):
                continue
            actions = item.get('actions', [])
            if isinstance(actions, list):
                for action in actions:
                    if isinstance(action, dict):
                        collect(action.get('path'))
                        collect(action.get('target'))
                        collect(action.get('from'))
                        collect(action.get('to'))
            external_files = item.get('external_files', [])
            if isinstance(external_files, list):
                for f in external_files:
                    if isinstance(f, dict):
                        collect(f.get('path'))
                        collect(f.get('target'))
                    elif isinstance(f, str):
                        collect(f)

        return sorted(list(affected))[:8]

    def _compute_preview_summary(self, updates):
        versions = self._extract_ordered_versions(updates)
        file_count = 0
        total_bytes = 0

        for item in updates:
            if not isinstance(item, dict):
                continue

            external_files = item.get('external_files')
            if isinstance(external_files, list):
                file_count += len(external_files)
                for f in external_files:
                    if isinstance(f, dict):
                        size = f.get('size')
                        if isinstance(size, (int, float)):
                            total_bytes += int(size)

            count_hint = item.get('file_count')
            if file_count == 0 and isinstance(count_hint, int) and count_hint > 0:
                file_count += count_hint

            bytes_hint = item.get('total_bytes')
            if total_bytes == 0 and isinstance(bytes_hint, (int, float)) and bytes_hint > 0:
                total_bytes += int(bytes_hint)

        return {
            "versions": versions,
            "file_count": file_count,
            "total_bytes": total_bytes,
            "affected_paths": self._extract_affected_paths(updates)
        }

    def preview_update_plan(self, update_list_json, source_type):
        try:
            updates = self._normalize_update_list(update_list_json)
        except Exception as e:
            return json.dumps({"ok": False, "error": f"更新列表解析失败: {e}"})

        summary = self._compute_preview_summary(updates)
        token = str(uuid.uuid4())
        created_ts = time.time()
        created_at = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
        payload_hash = hashlib.sha256(
            json.dumps(updates, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        ).hexdigest()

        self._pending_update_preview = {
            "token": token,
            "source_type": source_type,
            "versions": summary["versions"],
            "update_list_hash": payload_hash,
            "created_at": created_ts
        }

        try:
            self._add_activity_log("update_preview_opened", {
                "versions": summary["versions"],
                "source_type": source_type,
                "file_count": summary["file_count"],
                "total_bytes": summary["total_bytes"],
                "affected_paths": summary["affected_paths"]
            })
        except Exception:
            pass

        return json.dumps({
            "ok": True,
            "versions": summary["versions"],
            "file_count": summary["file_count"],
            "total_bytes": summary["total_bytes"],
            "affected_paths": summary["affected_paths"],
            "plan_token": token,
            "created_at": created_at
        }, ensure_ascii=False)

    def _is_pending_preview_valid(self, update_list_json, source_type, plan_token):
        pending = self._pending_update_preview
        if not pending:
            return False, "未找到预览上下文，请先预览更新"

        if plan_token != pending.get("token"):
            return False, "预览令牌不匹配，请重新预览"

        if source_type != pending.get("source_type"):
            return False, "更新来源已变更，请重新预览"

        created_at = pending.get("created_at", 0)
        if time.time() - created_at > self._preview_ttl_seconds:
            return False, "预览已过期，请重新预览"

        try:
            updates = self._normalize_update_list(update_list_json)
        except Exception as e:
            return False, f"更新列表解析失败: {e}"

        versions = self._extract_ordered_versions(updates)
        if versions != pending.get("versions", []):
            return False, "更新版本列表已变化，请重新预览"

        payload_hash = hashlib.sha256(
            json.dumps(updates, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        ).hexdigest()
        if payload_hash != pending.get("update_list_hash"):
            return False, "更新内容已变化，请重新预览"

        return True, updates

    def start_update_sequence_confirmed(self, update_list_json, source_type, plan_token, confirmed):
        if not confirmed:
            return False

        ok, result = self._is_pending_preview_valid(update_list_json, source_type, plan_token)
        if not ok:
            self.log(f"更新确认校验失败: {result}")
            if global_window:
                global_window.evaluate_js(f"alert('{result}')")
            return False

        updates = result
        threading.Thread(target=self._sequence_thread, args=(update_list_json, source_type)).start()

        try:
            self._add_activity_log("update_preview_confirmed", {
                "versions": self._extract_ordered_versions(updates),
                "source_type": source_type
            })
        except Exception:
            pass

        self._pending_update_preview = None
        return True

    def start_update_sequence(self, update_list_json, source_type):
        self.log("拒绝直接启动更新：需要先预览并确认")
        if global_window:
            global_window.evaluate_js("alert('请先预览更新摘要并点击继续更新。')")
        return False

    def _sequence_thread(self, update_list_json, source_type):
        try:
            updates = json.loads(update_list_json)
            total_updates = len(updates)
            
            self.log(f"开始批量更新流程，共 {total_updates} 个版本...")
            
            # 获取当前所有可用的"可选版本"列表，用于计算稍后要存入 skipped 的内容
            # 这里简单处理：如果安装成功，从 skipped 移除；如果未安装且在 skipped，保持。
            # 更精确的逻辑在循环结束后处理。
            
            successful_versions = []
            
            for i, update_item in enumerate(updates):
                ver = update_item.get('version')
                self.log(f"=== 正在处理版本 {ver} ({i+1}/{total_updates}) ===")
                
                # 获取下载链接
                dl_urls = update_item.get('download_urls', {})
                url = dl_urls.get(source_type)
                
                if not url:
                    self.log(f"错误: 版本 {ver} 缺少 {source_type} 下载链接，跳过。")
                    continue
                
                # 执行单次更新 (复用之前的逻辑，稍作修改以抛出异常)
                try:
                    self._perform_single_update(url, source_type)
                    successful_versions.append(ver)
                    self._add_activity_log("update_success", {"version": ver})
                except Exception as e:
                    self.log(f"版本 {ver} 更新失败: {e}")
                    if self.cancel_event.is_set():
                        self._add_activity_log("update_cancelled", {"version": ver, "reason": "user_cancelled"})
                    else:
                        self._add_activity_log("update_failed", {"version": ver, "error": str(e)})
                    if self._is_network_timeout_error(e):
                        self._safe_js_alert(f"版本 {ver} 下载超时/阻塞，已中止。可切换全球节点重试。")
                    else:
                        self._safe_js_alert(f"版本 {ver} 更新失败，流程中止。")
                    break # 中断后续更新
            
            # 更新完成后，处理版本号和跳过列表
            if successful_versions:
                newest_ver = max(successful_versions, key=version_sort_key)
                current_ver = self.get_local_version()
                
                # 只有当新安装的版本确实比当前版本新时，才更新 version
                if is_version_newer(newest_ver, current_ver):
                    self.cfg_mgr.save_config({"current_version": newest_ver})
                    self.log(f"客户端版本已更新为: {newest_ver}")
                
                # 处理 skipped_versions
                # 1. 读取旧的 skipped
                old_skipped = self.cfg_mgr.config.get("skipped_versions", [])
                new_skipped = set(old_skipped)
                
                # 2. 将安装成功的从 skipped 中移除
                for v in successful_versions:
                    if v in new_skipped:
                        new_skipped.remove(v)
                
                # 3. 这里的逻辑略复杂：我们怎么知道哪些被用户"取消勾选"了？
                # 实际上，_check_update_thread 里找到的所有 candidates，减去 successful_versions，剩下的就是被跳过的
                # 但这里我们在后端拿不到完整的 candidates。
                # 简化逻辑：前端发过来的 update_list_json 已经是用户"确认要装"的。
                # 所以我们只需要把"装成功的"移除。
                # 那"新增的跳过"怎么加？
                # 答：需要前端传另一个参数，或者由前端调用 record_skip。
                # 为了简单可靠，我们在前端处理"记录跳过"。(见前端代码)
                
                self.cfg_mgr.save_config({"skipped_versions": list(new_skipped)})
                
            self.log("🎉 所有选定更新已处理完毕！")
            self.update_stage = 0
            if global_window:
                global_window.evaluate_js("updateDownloadProgress(100)")
                global_window.evaluate_js("onClientUpdateFinished('客户端更新已完成，请重启客户端。')")
                global_window.evaluate_js("resetUpdateModalState()")
                global_window.evaluate_js(f"document.getElementById('current-ver-display').innerText = '{self.get_local_version()}'")

        except Exception as e:
            self.log(f"批量更新流程异常: {e}")
            if global_window: global_window.evaluate_js("resetUpdateModalState()")
        finally:
            self.update_stage = 0

    def _perform_single_update(self, url, source_type):
        """
        原子性更新：
        阶段1 - 下载所有文件到暂存区并校验
        阶段2 - 备份旧文件 → 执行 actions → 移动新文件
        失败时自动回滚
        """
        candidates = self._build_download_candidates(url, source_type)
        primary_url = candidates[0] if candidates else url

        path = urlparse(primary_url).path
        filename = os.path.basename(path)
        if not filename.lower().endswith(".zip"):
            filename = "update_temp.zip"

        save_path = os.path.join(self.game_root, filename)
        staging_dir = os.path.join(self.game_root, "temp_staging")
        temp_dir = os.path.join(self.game_root, "temp_update_tcy")
        backup_dir = None

        try:
            # 清理旧的暂存目录
            for d in [staging_dir, temp_dir]:
                if os.path.exists(d):
                    shutil.rmtree(d)
            os.makedirs(staging_dir, exist_ok=True)

            # ======== 阶段1：下载骨架包 ========
            self.log("=== 阶段1：下载并校验 ===")
            log_info(f"开始下载骨架包: {primary_url}")

            dl_state = {'start': time.time(), 'last_update': 0}

            def report_dl(block_num, block_size, total_size):
                if self.cancel_event.is_set():
                    raise Exception("Update cancelled by user")
                if total_size > 0:
                    downloaded = block_num * block_size
                    percent = min(100, int(downloaded * 100 / total_size))
                    elapsed = time.time() - dl_state['start']
                    speed_str = "0 KB/s"
                    if elapsed > 0.1:
                        speed = downloaded / elapsed
                        if speed > 1024*1024: speed_str = f"{speed/1024/1024:.1f} MB/s"
                        else: speed_str = f"{speed/1024:.0f} KB/s"
                    if time.time() - dl_state['last_update'] > 0.1 or percent >= 100:
                        dl_state['last_update'] = time.time()
                        if global_window:
                            global_window.evaluate_js(f"updateProgressDetails({percent}, '{speed_str}', '正在获取配置包...')")

            self.log(f"下载配置包: {filename}")

            self.update_stage = 1
            self.cancel_event.clear()

            self._download_with_candidates_resumable(
                candidates,
                save_path,
                progress_cb=report_dl,
                connect_timeout=8,
                stall_timeout=15,
                log_context=f"skeleton_zip:{filename}"
            )

            # 解压骨架包
            with zipfile.ZipFile(os.path.abspath(save_path), 'r') as zf:
                for file in zf.namelist():
                    zf.extract(file, temp_dir)

            manifest_path = os.path.join(temp_dir, "manifest.json")
            data = {}
            if os.path.exists(manifest_path):
                with open(manifest_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

            actions = data.get('actions', [])
            external_files = data.get('external_files', [])
            total_ops = len(actions) + len(external_files)
            current_op = [0]
            progress_lock = threading.Lock()
            
            dl_status = {}
            last_payload_time = [0]

            def push_detailed_payload(overall_pct, speed_str, total_dl, total_size, eta_str):
                now = time.time()
                if now - last_payload_time[0] < 0.15 and overall_pct < 100:
                    return
                last_payload_time[0] = now
                
                files_list = []
                for k, v in dl_status.items():
                    dl_kb = v['downloaded'] // 1024
                    tot_kb = v['total'] // 1024
                    files_list.append({
                        'name': v['name'],
                        'percent': v['percent'],
                        'size': f"{tot_kb}KB",
                        'downloaded': f"{dl_kb}KB",
                        'state': v['state']
                    })
                
                payload = {
                    'percent': overall_pct,
                    'speed': speed_str,
                    'downloaded': f"{total_dl // 1024 // 1024} MB" if total_dl > 1024*1024 else f"{total_dl // 1024} KB",
                    'total': f"{total_size // 1024 // 1024} MB" if total_size > 1024*1024 else f"{total_size // 1024} KB",
                    'eta': eta_str,
                    'files': files_list
                }
                
                import json
                import re
                if global_window:
                    try:
                        global_window.evaluate_js(f"updateDetailedProgress({json.dumps(payload)})")
                    except Exception:
                        pass

            def report_step(name, speed="--"):
                with progress_lock:
                    msg = f"({current_op[0]}/{total_ops}): {name}"
                    p = int((current_op[0] / total_ops) * 100) if total_ops > 0 else 100
                    if global_window:
                        safe_msg = msg.replace("'", "\\'")
                        global_window.evaluate_js(f"updateProgressDetails({p}, '{speed}', '{safe_msg}')")

            # 下载 external_files 到暂存区
            files_to_download = []

            for item in external_files:
                target_path = os.path.join(self.game_root, item['path'])
                
                dl_status[item['name']] = {
                    'name': item['name'],
                    'downloaded': 0,
                    'total': item.get('size', 0),
                    'state': 'pending',
                    'percent': 0
                }

                # 检查文件是否已存在且完整
                expected_sha = item.get('sha256', '')
                if os.path.exists(target_path):
                    if expected_sha:
                        match, _ = self._verify_sha256(target_path, expected_sha)
                        if match:
                            current_op[0] += 1
                            dl_status[item['name']]['state'] = 'skipped'
                            dl_status[item['name']]['percent'] = 100
                            dl_status[item['name']]['downloaded'] = item.get('size', 0)
                            report_step(f"跳过(hash匹配): {item['name']}")
                            log_info(f"跳过已存在文件(SHA256匹配): {item['name']}")
                            continue
                    elif abs(os.path.getsize(target_path) - item.get('size', 0)) < 1024:
                        current_op[0] += 1
                        dl_status[item['name']]['state'] = 'skipped'
                        dl_status[item['name']]['percent'] = 100
                        dl_status[item['name']]['downloaded'] = item.get('size', 0)
                        report_step(f"跳过已存在: {item['name']}")
                        continue

                files_to_download.append(item)

            # 并行下载到暂存区
            max_workers = self.cfg_mgr.config.get("parallel_downloads", 3)
            download_errors = []
            total_downloaded_bytes = [0]
            total_bytes = sum(f.get('size', 0) for f in files_to_download)
            dl_start_time = time.time()

            def download_single(item):
                d_url = item['url']
                candidates_for_file = self._build_download_candidates(d_url, source_type)

                staging_path = os.path.join(staging_dir, item['path'])
                os.makedirs(os.path.dirname(staging_path), exist_ok=True)

                file_dl_state = {'downloaded': 0}

                def file_report(block_num, block_size, total_size):
                    if self.cancel_event.is_set():
                        raise Exception("Update cancelled by user")
                    downloaded = min(block_num * block_size, total_size if total_size > 0 else block_num * block_size)
                    delta = downloaded - file_dl_state['downloaded']
                    if delta <= 0: return
                    file_dl_state['downloaded'] = downloaded

                    with progress_lock:
                        total_downloaded_bytes[0] += delta
                        
                        f_total = total_size if total_size > 0 else item.get('size', 1)
                        dl_status[item['name']]['downloaded'] = file_dl_state['downloaded']
                        dl_status[item['name']]['total'] = f_total
                        dl_status[item['name']]['percent'] = min(100, int((file_dl_state['downloaded'] / f_total) * 100))
                        dl_status[item['name']]['state'] = 'downloading'
                        
                        elapsed = time.time() - dl_start_time
                        speed_str = "0 KB/s"
                        if elapsed > 0.1:
                            speed = total_downloaded_bytes[0] / elapsed
                            if speed > 1024*1024: speed_str = f"{speed/1024/1024:.1f} MB/s"
                            else: speed_str = f"{speed/1024:.0f} KB/s"

                        overall_pct = int(total_downloaded_bytes[0] * 100 / total_bytes) if total_bytes > 0 else 0
                        overall_pct = min(99, overall_pct)
                        remaining = "--"
                        if elapsed > 1 and total_downloaded_bytes[0] > 0:
                            eta = (total_bytes - total_downloaded_bytes[0]) / (total_downloaded_bytes[0] / elapsed)
                            if eta < 60: remaining = f"{int(eta)}s"
                            else: remaining = f"{int(eta/60)}m{int(eta%60)}s"
                        
                        push_detailed_payload(overall_pct, speed_str, total_downloaded_bytes[0], total_bytes, remaining)

                # 下载并校验（带重试）
                expected_sha = item.get('sha256', '')
                max_retries = 2
                for retry in range(max_retries + 1):
                    try:
                        file_dl_state['downloaded'] = 0
                        with progress_lock:
                            if retry > 0:
                                dl_status[item['name']]['state'] = f'retry {retry}'
                                push_detailed_payload(min(99, int(total_downloaded_bytes[0] * 100 / total_bytes) if total_bytes > 0 else 0), "--", total_downloaded_bytes[0], total_bytes, "--")
                                
                        self._download_with_candidates_resumable(
                            candidates_for_file,
                            staging_path,
                            progress_cb=file_report,
                            connect_timeout=8,
                            stall_timeout=12,
                            log_context=f"external:{item['name']}"
                        )

                        if expected_sha:
                            self.log(f"开始SHA256校验: {item['name']}")
                            match, actual = self._verify_sha256(staging_path, expected_sha)
                            if not match:
                                if retry < max_retries:
                                    self.log(f"校验失败 (重试 {retry+1}): {item['name']}")
                                    log_warning(f"SHA256校验失败，重试: {item['name']}, 期望={expected_sha[:16]}, 实际={actual[:16]}")
                                    os.remove(staging_path)
                                    continue
                                else:
                                    raise Exception(f"SHA256校验失败: {item['name']}")
                            else:
                                self.log(f"SHA256校验通过: {item['name']}")
                                log_info(f"SHA256校验通过: {item['name']}")

                        with progress_lock:
                            current_op[0] += 1
                            dl_status[item['name']]['state'] = 'done'
                            push_detailed_payload(min(99, int(total_downloaded_bytes[0] * 100 / total_bytes) if total_bytes > 0 else 0), "--", total_downloaded_bytes[0], total_bytes, "--")
                        self.log(f"已暂存: {item['name']}")
                        return True
                    except Exception as e:
                        if "cancelled" in str(e).lower() or self.cancel_event.is_set():
                            raise Exception("Update cancelled by user")
                        if retry >= max_retries:
                            with progress_lock:
                                dl_status[item['name']]['state'] = 'error'
                                push_detailed_payload(min(99, int(total_downloaded_bytes[0] * 100 / total_bytes) if total_bytes > 0 else 0), "--", total_downloaded_bytes[0], total_bytes, "--")
                            raise
                return False

            if files_to_download:
                self.log(f"开始下载 {len(files_to_download)} 个文件 (并发: {max_workers})...")
                log_info(f"并行下载启动: {len(files_to_download)} 个文件, max_workers={max_workers}")
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    futures = {executor.submit(download_single, item): item for item in files_to_download}
                    for future in as_completed(futures):
                        item = futures[future]
                        try:
                            future.result()
                        except Exception as e:
                            download_errors.append(f"{item['name']}: {e}")
                            self.log(f"下载失败: {item['name']} - {e}")
                            log_error(f"文件下载失败: {item['name']} - {e}")

            if self.cancel_event.is_set() or any("cancelled" in str(e).lower() for e in download_errors):
                self.log("更新已被用户取消。清理暂存区...")
                if global_window:
                    global_window.evaluate_js("onUpdateCancelled()")
                return

            if download_errors:
                raise Exception(f"以下文件下载失败:\n" + "\n".join(download_errors))

            self.update_stage = 2
            if global_window:
                global_window.evaluate_js("disableCancelButton()")

            self.log("阶段1完成：所有文件已下载并校验通过")
            log_info("阶段1完成: 所有文件下载校验通过")

            # ======== 阶段2：备份旧文件 → 应用更新 ========
            self.log("=== 阶段2：应用更新 ===")
            if global_window:
                global_window.evaluate_js("onUpdateApplying()")

            # 收集所有受影响的文件路径（用于备份）
            affected_paths = []
            for action in actions:
                if action.get('type') == 'delete_keyword':
                    t_folder = os.path.join(self.game_root, action.get('folder', ''))
                    keyword = action.get('keyword', '')
                    if os.path.exists(t_folder) and keyword:
                        for f in os.listdir(t_folder):
                            if keyword.lower() in f.lower():
                                affected_paths.append(os.path.join(t_folder, f))
                elif action.get('type') == 'delete':
                    p = os.path.join(self.game_root, action.get('path', ''))
                    affected_paths.append(p)
                elif action.get('type') == 'copy_folder':
                    dest = os.path.join(self.game_root, action.get('dest', ''))
                    if os.path.exists(dest):
                        for root, dirs, files in os.walk(dest):
                            for f in files:
                                affected_paths.append(os.path.join(root, f))

            for item in files_to_download:
                target_path = os.path.join(self.game_root, item['path'])
                if os.path.exists(target_path):
                    affected_paths.append(target_path)

            # 创建备份
            version_str = data.get('version', time.strftime('%y.%m.%d.%H.%M'))
            if affected_paths:
                backup_dir = self._create_backup(version_str, affected_paths)

            try:
                # 执行 Actions
                for action in actions:
                    current_op[0] += 1
                    op_name = "清理旧文件"
                    if action.get('type') == 'copy_folder': op_name = "覆盖配置"
                    report_step(op_name)

                    if action.get('type') == 'delete_keyword':
                        t_folder = os.path.join(self.game_root, action.get('folder', ''))
                        keyword = action.get('keyword', '')
                        if os.path.exists(t_folder) and keyword:
                            for f in os.listdir(t_folder):
                                if keyword.lower() in f.lower():
                                    try:
                                        os.remove(os.path.join(t_folder, f))
                                        self.log(f"删: {f}")
                                        log_info(f"删除文件: {f}")
                                    except: pass
                    elif action.get('type') == 'delete':
                        try:
                            target = os.path.join(self.game_root, action.get('path'))
                            os.remove(target)
                            log_info(f"删除文件: {action.get('path')}")
                        except: pass
                    elif action.get('type') == 'copy_folder':
                        src = os.path.join(temp_dir, action.get('src'))
                        dest = os.path.join(self.game_root, action.get('dest'))
                        if os.path.exists(src):
                            try:
                                shutil.copytree(src, dest, dirs_exist_ok=True)
                                self.log(f"合并配置: {action.get('src')} -> {dest}")
                                log_info(f"合并配置文件夹: {action.get('src')} -> {dest}")
                            except Exception as e:
                                self.log(f"合并失败: {e}")
                                log_error(f"合并文件夹失败: {e}")

                # 从暂存区移动文件到目标位置
                for item in files_to_download:
                    staging_path = os.path.join(staging_dir, item['path'])
                    target_path = os.path.join(self.game_root, item['path'])
                    if os.path.exists(staging_path):
                        os.makedirs(os.path.dirname(target_path), exist_ok=True)
                        shutil.move(staging_path, target_path)
                        self.log(f"已安装: {item['name']}")
                        log_info(f"文件安装完成: {item['name']} -> {item['path']}")

                self.log("阶段2完成：更新已成功应用")
                log_info("阶段2完成: 更新成功应用")

            except Exception as e:
                self.log(f"更新应用失败: {e}，正在自动回滚...")
                log_error(f"更新应用阶段异常: {traceback.format_exc()}")
                if backup_dir:
                    self._restore_backup(backup_dir)
                raise

        finally:
            for d in [temp_dir, staging_dir]:
                if os.path.exists(d):
                    try: shutil.rmtree(d)
                    except: pass
            if os.path.exists(save_path):
                try: os.remove(save_path)
                except: pass

    # 供前端调用：记录跳过的版本
    def add_skipped_version(self, version):
        skipped = self.cfg_mgr.config.get("skipped_versions", [])
        if version not in skipped:
            skipped.append(version)
            self.cfg_mgr.save_config({"skipped_versions": skipped})
            self.log(f"已标记跳过: {version}")

    def get_cached_history(self):
        """从本地缓存读取更新历史记录，供更新日志时间线视图使用"""
        cached = self.cfg_mgr.config.get("cached_history", [])
        if cached:
            # 按版本号从新到旧排序
            cached_sorted = sort_versioned_items(cached, reverse=True)
            return json.dumps(cached_sorted)
        return json.dumps([])

    def get_activity_log(self):
        """获取操作日志列表（最新的在前）"""
        try:
            cfg = self.cfg_mgr.load_config()
            log_list = cfg.get("activity_log", [])
            log_list.reverse()  # 最新的在前
            return json.dumps(log_list)
        except Exception:
            return json.dumps([])

    def clear_activity_log(self):
        """清空操作日志"""
        try:
            self.cfg_mgr.save_config({"activity_log": []})
            return json.dumps({"success": True})
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)})

    def get_all_history(self):
        """获取所有历史版本列表，供强制拉取功能使用"""
        threading.Thread(target=self._get_all_history_thread).start()

    def _get_all_history_thread(self):
        self.log("正在获取全部历史版本列表...")
        custom_latest = self.cfg_mgr.config.get("custom_latest_url", "").strip()
        url_list = self._build_url_list(DEFAULT_LATEST_JSON_URL, GITHUB_LATEST_JSON_URL, custom_latest)
        data, success_urls, failed_urls = self._fetch_json_from_urls(url_list, fetch_label="历史版本列表")

        if data is None:
            if global_window:
                global_window.evaluate_js("alert('获取历史版本列表失败，请检查网络连接。')")
            return

        history = data.get('history', [])
        if not history:
            if global_window:
                global_window.evaluate_js("alert('未找到任何历史版本记录。')")
            return

        # 按版本号从小到大排序
        history_sorted = sort_versioned_items(history)
        self.log(f"获取到 {len(history_sorted)} 个历史版本")
        if global_window:
            global_window.evaluate_js(f"showForceUpdateModal({json.dumps(history_sorted)})")

    # ── Modrinth Mod Search ──────────────────────────────────────────────────

    def _get_installed_mod_filenames(self):
        """Return a set of filenames present in the mods directory.

        Includes both .jar and .jar.disabled entries, plus base names
        (stripped .disabled) for cross-matching with Modrinth version filenames.
        """
        mods_dir = self._get_game_subdir("mods")
        result = set()
        try:
            for f in os.listdir(mods_dir):
                if f.endswith(".jar") or f.endswith(".jar.disabled"):
                    result.add(f)
                    if f.endswith(".jar.disabled"):
                        result.add(f[:-len(".disabled")])
        except Exception:
            pass
        return result

    def get_mods_dir_path(self):
        """Return the absolute path of the mods directory."""
        return self._get_game_subdir("mods")

    def modrinth_search(self, query, mc_version="", loader="", category="", offset=0, sort_index="relevance"):
        """Search Modrinth for mods matching query with optional filters.

        sort_index: one of 'relevance', 'downloads', 'follows', 'newest', 'updated'.
        """
        try:
            facets = [["project_type:mod"]]
            if mc_version:
                facets.append([f"versions:{mc_version}"])
            if loader:
                facets.append([f"categories:{loader}"])
            if category:
                facets.append([f"categories:{category}"])

            valid_sorts = ("relevance", "downloads", "follows", "newest", "updated")
            if sort_index not in valid_sorts:
                sort_index = "relevance"

            params = urllib.parse.urlencode({
                "query": query,
                "facets": json.dumps(facets),
                "index": sort_index,
                "offset": str(offset),
                "limit": "20",
            })
            url = f"https://api.modrinth.com/v2/search?{params}"
            req = urllib.request.Request(url, headers={"User-Agent": "TCYClientUpdater/1.0.7 (tcymc.space)"})
            with self._urlopen_with_policy(req, timeout=15, url=url) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            hits = data.get("hits", [])
            total_hits = data.get("total_hits", len(hits))
            return json.dumps({"success": True, "hits": hits, "total_hits": total_hits})
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)})

    def modrinth_get_project(self, project_id):
        """Fetch full project metadata from Modrinth for the given project_id."""
        try:
            url = f"https://api.modrinth.com/v2/project/{urllib.parse.quote(project_id)}"
            req = urllib.request.Request(url, headers={"User-Agent": "TCYClientUpdater/1.0.7 (tcymc.space)"})
            with self._urlopen_with_policy(req, timeout=15, url=url) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return json.dumps({"success": True, "project": data})
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)})

    def modrinth_get_projects_batch(self, project_ids_json):
        """Batch-fetch multiple project metadata from Modrinth.

        project_ids_json: JSON string of a list, e.g. '["P7dR8mSH","abc123"]'.
        Returns {success, projects: {id: {title, icon_url, slug, ...}, ...}}.
        """
        try:
            ids = json.loads(project_ids_json) if isinstance(project_ids_json, str) else project_ids_json
            if not ids:
                return json.dumps({"success": True, "projects": {}})
            params = urllib.parse.urlencode({"ids": json.dumps(ids)})
            url = f"https://api.modrinth.com/v2/projects?{params}"
            req = urllib.request.Request(url, headers={"User-Agent": "TCYClientUpdater/1.0.7 (tcymc.space)"})
            with self._urlopen_with_policy(req, timeout=15, url=url) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            projects = {}
            for p in data:
                projects[p["id"]] = {
                    "id": p["id"],
                    "title": p.get("title", ""),
                    "slug": p.get("slug", ""),
                    "icon_url": p.get("icon_url", ""),
                    "description": p.get("description", ""),
                }
            return json.dumps({"success": True, "projects": projects})
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)})

    def modrinth_get_versions(self, project_id, mc_version="", loader=""):
        """Fetch version list for a Modrinth project, annotated with installed flag."""
        try:
            params = []
            if loader:
                params.append(("loaders", json.dumps([loader])))
            if mc_version:
                params.append(("game_versions", json.dumps([mc_version])))
            query_str = urllib.parse.urlencode(params)
            url = f"https://api.modrinth.com/v2/project/{urllib.parse.quote(project_id)}/version"
            if query_str:
                url = f"{url}?{query_str}"
            req = urllib.request.Request(url, headers={"User-Agent": "TCYClientUpdater/1.0.7 (tcymc.space)"})
            with self._urlopen_with_policy(req, timeout=15, url=url) as resp:
                versions = json.loads(resp.read().decode("utf-8"))

            installed = self._get_installed_mod_filenames()
            trimmed = []
            for v in versions:
                files = v.get("files", [])
                if not files:
                    continue
                primary_file = next((f for f in files if f.get("primary")), files[0])
                trimmed.append({
                    "id": v["id"],
                    "name": v.get("name", ""),
                    "version_number": v.get("version_number", ""),
                    "version_type": v.get("version_type", "release"),
                    "game_versions": v.get("game_versions", []),
                    "loaders": v.get("loaders", []),
                    "date_published": v.get("date_published", ""),
                    "downloads": v.get("downloads", 0),
                    "filename": primary_file["filename"],
                    "url": primary_file["url"],
                    "size": primary_file["size"],
                    "installed": primary_file["filename"] in installed,
                    "dependencies": v.get("dependencies", []),
                })
            return json.dumps({"success": True, "versions": trimmed})
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)})

    def modrinth_download_mod(self, file_url, filename, force=False):
        """Download a mod file from Modrinth CDN to the mods directory.

        Streams in 64 KB chunks; pushes onModDownloadProgress events to the
        frontend via global_window.evaluate_js during the download.  Returns
        immediately after spawning a daemon thread.
        """
        # Validate filename — no path traversal
        if ".." in filename or "/" in filename or "\\" in filename:
            return json.dumps({"success": False, "error": "非法文件名"})

        dest_path = os.path.join(self._get_game_subdir("mods"), filename)

        # Duplicate check
        if os.path.exists(dest_path) and not force:
            return json.dumps({"success": False, "already_exists": True, "error": "文件已存在"})

        if force and os.path.exists(dest_path):
            os.remove(dest_path)

        def _push(data):
            if global_window:
                global_window.evaluate_js(f"onModDownloadProgress({json.dumps(data)})")

        def _do_download():
            try:
                req = urllib.request.Request(
                    file_url,
                    headers={"User-Agent": "TCYClientUpdater/1.0.7 (tcymc.space)"},
                )
                with self._urlopen_with_policy(req, timeout=15, url=file_url) as resp:
                    try:
                        total_size = int(resp.headers.get("Content-Length", -1))
                    except Exception:
                        total_size = -1
                    downloaded = 0
                    start_ts = time.time()
                    with open(dest_path, "wb") as out:
                        while True:
                            chunk = resp.read(64 * 1024)
                            if not chunk:
                                break
                            out.write(chunk)
                            downloaded += len(chunk)
                            percent = int(downloaded * 100 / total_size) if total_size > 0 else -1
                            elapsed = time.time() - start_ts
                            speed = downloaded / elapsed if elapsed > 0 else 0
                            if speed < 1024 * 1024:
                                speed_str = f"{speed / 1024:.1f} KB/s"
                            else:
                                speed_str = f"{speed / 1024 / 1024:.2f} MB/s"
                            _push({"filename": filename, "percent": percent, "speed": speed_str, "done": False, "error": None})
                _push({"filename": filename, "percent": 100, "speed": "", "done": True, "error": None})
            except Exception as e:
                _push({"filename": filename, "percent": 0, "speed": "", "done": True, "error": str(e)})

        threading.Thread(target=_do_download, daemon=True).start()
        return json.dumps({"success": True, "message": "下载已开始"})

    # ==================== Save Management ====================

    def _get_saves_dir(self):
        """Resolve the Minecraft saves directory.

        Uses the same layout as _get_game_subdir: prefers
        .minecraft/versions/<TARGET>/saves, falls back to versions/<TARGET>/saves.
        Creates the directory if it does not exist.
        """
        return self._get_game_subdir("saves")

    def _parse_level_dat_metadata(self, level_dat_path, parse_version="auto"):
        """Parse a level.dat and extract display metadata.

        parse_version controls seed extraction strategy:
          - "auto": use DataVersion threshold 2566 to decide
          - "pre1.16": always use Data/RandomSeed
          - "1.16+": always use Data/WorldGenSettings/seed
        On any exception returns an error dict with level_name='(解析失败)'.
        """
        try:
            nbt = NbtIO.read(level_dat_path)
            # Root is TAG_COMPOUND; navigate to the 'Data' child compound
            data_compound = next(
                (c["value"] for c in nbt["value"] if c["name"] == "Data"), []
            )

            def get(name):
                node = next((c for c in data_compound if c["name"] == name), None)
                return node["value"] if node else None

            data_version = get("DataVersion") or 0
            level_name = get("LevelName") or "(Unknown)"
            game_type_int = get("GameType") or 0
            last_played_ms = get("LastPlayed") or 0

            # LastPlayed is a Long — serialized as string by NbtIO
            try:
                last_played_ms = int(last_played_ms)
            except (TypeError, ValueError):
                last_played_ms = 0

            mc_version_name = None
            version_node = get("Version")  # compound list
            if isinstance(version_node, list):
                ver_name_node = next((c for c in version_node if c["name"] == "Name"), None)
                mc_version_name = ver_name_node["value"] if ver_name_node else None

            GAME_MODES = {0: "生存", 1: "创造", 2: "冒险", 3: "旁观"}
            game_mode = GAME_MODES.get(game_type_int, str(game_type_int))

            # Seed path differs by version
            seed = None
            use_new_path = (parse_version == "1.16+") or (parse_version == "auto" and data_version >= 2566)
            use_old_path = (parse_version == "pre1.16") or (parse_version == "auto" and data_version < 2566)
            if use_new_path:
                wgs_node = get("WorldGenSettings")
                if isinstance(wgs_node, list):
                    seed_node = next((c for c in wgs_node if c["name"] == "seed"), None)
                    seed = seed_node["value"] if seed_node else None
            if seed is None and (use_old_path or parse_version == "auto"):
                seed = get("RandomSeed")

            last_played_str = ""
            if last_played_ms:
                last_played_str = datetime.fromtimestamp(last_played_ms / 1000).strftime('%Y-%m-%d %H:%M')

            return {
                "level_name": level_name,
                "game_mode": game_mode,
                "seed": str(seed) if seed is not None else "(未知)",
                "mc_version": mc_version_name or "(未知)",
                "data_version": data_version,
                "last_played": last_played_str,
            }
        except Exception as e:
            return {
                "level_name": "(解析失败)",
                "game_mode": "?",
                "seed": "?",
                "mc_version": "?",
                "data_version": 0,
                "last_played": "?",
                "error": str(e),
            }

    def list_saves(self, parse_version="auto"):
        """Scan the saves directory and return world metadata for every valid world folder.

        parse_version: 'auto', 'pre1.16', or '1.16+' — controls seed extraction strategy.
        """
        saves_dir = self._get_saves_dir()
        if not os.path.exists(saves_dir):
            return json.dumps({"success": True, "saves": [], "saves_dir": saves_dir})

        saves = []
        try:
            for entry in sorted(os.listdir(saves_dir)):
                world_path = os.path.join(saves_dir, entry)
                if not os.path.isdir(world_path):
                    continue
                level_dat = os.path.join(world_path, "level.dat")
                if not os.path.exists(level_dat):
                    continue

                meta = self._parse_level_dat_metadata(level_dat, parse_version)

                # icon.png → base64 data URL (or empty string)
                icon_data = ""
                icon_path = os.path.join(world_path, "icon.png")
                if os.path.exists(icon_path):
                    try:
                        with open(icon_path, "rb") as f:
                            icon_data = "data:image/png;base64," + base64.b64encode(f.read()).decode()
                    except Exception:
                        pass

                # Folder size via os.walk
                folder_size = 0
                for dirpath, dirnames, filenames in os.walk(world_path):
                    for fn in filenames:
                        try:
                            folder_size += os.path.getsize(os.path.join(dirpath, fn))
                        except Exception:
                            pass
                size_mb = folder_size / (1024 * 1024)
                size_str = f"{size_mb:.1f} MB" if size_mb >= 1 else f"{folder_size // 1024} KB"

                saves.append({
                    "folder": entry,
                    "level_name": meta["level_name"],
                    "game_mode": meta["game_mode"],
                    "seed": meta["seed"],
                    "mc_version": meta["mc_version"],
                    "data_version": meta["data_version"],
                    "last_played": meta["last_played"],
                    "size": size_str,
                    "icon": icon_data,
                })
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)})

        # Sort by last_played descending (most recent first)
        saves.sort(key=lambda s: s.get("last_played", ""), reverse=True)
        return json.dumps({"success": True, "saves": saves, "saves_dir": saves_dir}, ensure_ascii=False)

    def save_backup(self, world_folder_name):
        """Zip a world folder to saves_dir in a background thread.

        Pushes onSaveBackupComplete({success, zip_name|error}) via evaluate_js when done.
        Guards against concurrent backup of the same world via _active_backups.
        """
        saves_dir = self._get_saves_dir()
        world_path = os.path.join(saves_dir, world_folder_name)
        if not os.path.isdir(world_path):
            return json.dumps({"success": False, "error": "存档文件夹不存在"})

        if world_folder_name in self._active_backups:
            return json.dumps({"success": False, "error": "该存档正在备份中"})

        self._active_backups.add(world_folder_name)

        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        safe_name = re.sub(r'[\\/:*?"<>|]', '_', world_folder_name)
        zip_name = f"{safe_name}_backup_{ts}.zip"
        zip_path = os.path.join(saves_dir, zip_name)

        active_backups = self._active_backups

        def _do_backup():
            try:
                with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                    for dirpath, dirnames, filenames in os.walk(world_path):
                        for fn in filenames:
                            fp = os.path.join(dirpath, fn)
                            arcname = os.path.relpath(fp, saves_dir)
                            zf.write(fp, arcname)
                payload = json.dumps({"success": True, "zip_name": zip_name}, ensure_ascii=False)
                if global_window:
                    global_window.evaluate_js(f"onSaveBackupComplete({payload})")
            except Exception as e:
                payload = json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)
                if global_window:
                    global_window.evaluate_js(f"onSaveBackupComplete({payload})")
            finally:
                active_backups.discard(world_folder_name)

        threading.Thread(target=_do_backup, daemon=True).start()
        return json.dumps({"queued": True})

    def save_delete(self, world_folder_name):
        """Delete a world folder after confirming no backup is in progress."""
        saves_dir = self._get_saves_dir()
        world_path = os.path.join(saves_dir, world_folder_name)
        if not os.path.isdir(world_path):
            return json.dumps({"success": False, "error": "存档文件夹不存在"})
        if world_folder_name in self._active_backups:
            return json.dumps({"success": False, "error": "该存档正在备份中，无法删除"})
        try:
            shutil.rmtree(world_path)
            return json.dumps({"success": True})
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)})

    def save_open_folder(self, world_folder_name):
        """Open a world folder in the OS file explorer."""
        saves_dir = self._get_saves_dir()
        world_path = os.path.join(saves_dir, world_folder_name)
        try:
            os.startfile(world_path)
        except AttributeError:
            # Non-Windows fallback
            import subprocess
            try:
                subprocess.Popen(["xdg-open", world_path])
            except Exception:
                pass
        except Exception:
            pass
        return json.dumps({"success": True})

    def save_import_folder(self):
        """Open a FOLDER_DIALOG and validate level.dat presence.

        Returns folder_path and parsed metadata on success.
        """
        if not global_window:
            return json.dumps({"success": False, "error": "窗口未初始化"})
        result = global_window.create_file_dialog(webview.FOLDER_DIALOG)
        if not result:
            return json.dumps({"success": False, "cancelled": True})
        folder_path = result[0] if isinstance(result, (tuple, list)) else result
        level_dat = os.path.join(folder_path, "level.dat")
        if not os.path.exists(level_dat):
            return json.dumps({"success": False, "error": "所选目录中未找到 level.dat，不是有效的 Minecraft 存档文件夹"})
        meta = self._parse_level_dat_metadata(level_dat)
        return json.dumps({"success": True, "folder_path": folder_path, "meta": meta}, ensure_ascii=False)

    def open_nbt_editor_for_save(self, world_folder_name):
        """Open the independent NBT editor window for a save folder."""
        saves_dir = self._get_saves_dir()
        return open_nbt_editor(saves_dir, world_folder_name)

    def open_nbt_editor_empty(self):
        """Open the independent NBT editor in empty workspace mode."""
        return open_nbt_editor_empty()


def main():
    freeze_support()
    global global_window
    try:
        api = Api()
        # === ✅读取保存的窗口大小 ===
        # 获取配置字符串，例如 "1280x720"
        size_str = api.cfg_mgr.config.get("window_size", "950x700")
        try:
            # 解析宽高
            init_w, init_h = map(int, size_str.split('x'))
        except:
            init_w, init_h = 950, 700

        html_file = get_resource_path("index.html")
        if not os.path.exists(html_file): return
        html_url = f"file:///{os.path.abspath(html_file).replace(os.sep, '/')}"
        
        global_window = webview.create_window(
            title='TCY Client Updater',
            url=html_url,
            js_api=api,
            width=init_w, height=init_h,  # 这里使用变量，而不是写死
            resizable=False,      # 既然窗口大小是固定档位，建议设为 False 禁止系统边缘拖动，避免冲突
            frameless=True,       
            easy_drag=False,
            transparent=True,     
            background_color='#000000'
        )
        webview.start(debug=False)
    except Exception as e: pass

if __name__ == '__main__':
    main()
