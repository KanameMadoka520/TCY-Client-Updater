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
import traceback
import json
import zipfile
import shutil
import glob
import threading
import base64
import time
from datetime import datetime
import webbrowser
from multiprocessing import freeze_support

# === 网络请求相关库 ===
import urllib.request
import urllib.error
from urllib.parse import urlparse
import ssl

import ctypes
from ctypes import windll, c_long, c_int, byref

# 窗口样式常量
GWL_STYLE = -16
WS_THICKFRAME = 0x00040000  # 关键：这是允许窗口调整大小的样式位
WS_CAPTION = 0x00C00000     # 标题栏样式（我们需要移除它，防止出现系统标题栏）

# 系统命令常量
WM_SYSCOMMAND = 0x0112
SC_SIZE = 0xF000

# === 忽略 SSL 证书验证 (防止旧系统/内网报错) ===
ssl._create_default_https_context = ssl._create_unverified_context

# === 开启 GPU 加速 (注释掉禁用代码) ===
# os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = "--disable-gpu --disable-d3d11 --disable-accelerated-video-decode"

if getattr(sys, 'frozen', False):
    current_dir = os.path.dirname(sys.executable)
    sys.stdout = open(os.devnull, 'w')
    sys.stderr = open(os.devnull, 'w')
else:
    current_dir = os.path.dirname(os.path.abspath(__file__))

log_file_path = os.path.join(current_dir, "launcher_debug.log")
logging.basicConfig(filename=log_file_path, level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s', filemode='w', encoding='utf-8')

def log_info(msg): logging.info(msg)
def log_error(msg): logging.error(msg)

try:
    import webview
except Exception as e:
    with open(os.path.join(current_dir, "CRASH_IMPORT.txt"), "w") as f: f.write(traceback.format_exc())
    sys.exit(1)

TARGET_VERSION_NAME = "异界战斗幻想"
CONFIG_FILE = "launcher_settings.json"

# ===整合包初始版本 (客户端内容版本) ===
INITIAL_VERSION = "26.02.06.15.24" 
# ===更新器自身版本 (传统版本号) ===
LAUNCHER_INTERNAL_VERSION = "1.0.0" 

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
            "mirror_prefix": "https://gh-proxy.org/",
            # === 默认窗口大小 (宽x高) ===
            "window_size": "950x600",
            # ===跳过的可选版本记录 ===
            "skipped_versions": []
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
    
    def __init__(self):
        self.game_root = self.find_game_root()
        self.cfg_mgr = ConfigManager()
        self.log(f"核心初始化完成，根目录定位: {self.game_root}")

    def min_window(self):
        if global_window: global_window.minimize()
    def max_window(self):
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
                "launcherVersion": LAUNCHER_INTERNAL_VERSION
            }
            if global_window: global_window.evaluate_js(f"initApp({json.dumps(init_data)})")
            
            # ===启动时自动触发检查更新 ===
            self.check_online_update()
            
        except Exception: pass

    def find_game_root(self):
        # 强制返回当前运行目录，不做任何智能探测，防止误判为 .minecraft 内部
        return os.path.abspath(current_dir)
    
     # ===启动时的目录严格校验 ===
    def check_game_directory_exists(self):
        """
        严格检测目录结构：
        检查当前运行目录的下级是否存在：.minecraft/versions/异界战斗幻想
        """
        # 1. 定义我们要找的目标路径 (相对路径)
        # 这意味着更新器必须和 .minecraft 文件夹在同一级
        target_path = os.path.join(".minecraft", "versions", "异界战斗幻想")
        
        # 2. 获取绝对路径（仅用于日志显示，方便调试）
        abs_path = os.path.abspath(target_path)
        
        # 3. 打印日志 (注意：此时前端可能还没加载完，日志主要看控制台或日志文件)
        print(f"[Init Check] 正在校验目录结构: {abs_path}")
        
        # 4. 执行检测
        if os.path.exists(target_path):
            print("[Init Check] 目录校验通过！成功找到异界战斗幻想版本文件夹。")
            return True
        else:
            print("[Init Check] 目录校验失败！未找到异界战斗幻想文件夹。请检查更新器是否放对位置?找糖醋鱼反馈!")
            return False

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
    def save_settings(self, settings_json):
        try:
            data = json.loads(settings_json)
            self.cfg_mgr.save_config(data)
            return True
        except: return False
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
    def open_url(self, url): webbrowser.open(url)
    
    def scan_versions(self):
        try: return [os.path.basename(f) for f in glob.glob(os.path.join(self.game_root, "update*.zip"))]
        except: return []
    def list_files(self, folder_type):
        sub_path = "mods" if folder_type == "mods" else "config"
        # 优先尝试 .minecraft 结构
        base_dir = os.path.join(self.game_root, ".minecraft", "versions", TARGET_VERSION_NAME, sub_path)
        if not os.path.exists(base_dir):
            base_dir = os.path.join(self.game_root, "versions", TARGET_VERSION_NAME, sub_path)

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
    def open_folder(self, folder_type):
        sub_path = "mods" if folder_type == "mods" else "config"
        target_dir = os.path.join(self.game_root, ".minecraft", "versions", TARGET_VERSION_NAME, sub_path)
        if not os.path.exists(target_dir):
             target_dir = os.path.join(self.game_root, "versions", TARGET_VERSION_NAME, sub_path)
        os.makedirs(target_dir, exist_ok=True)
        try: os.startfile(target_dir)
        except: pass
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
    def delete_file(self, folder_type, relative_path):
        if folder_type != 'mods' or ".." in relative_path: return False
        try:
            # 同样适配两种路径
            target_path = os.path.join(self.game_root, ".minecraft", "versions", TARGET_VERSION_NAME, "mods", relative_path)
            if not os.path.exists(target_path):
                 target_path = os.path.join(self.game_root, "versions", TARGET_VERSION_NAME, "mods", relative_path)
            
            if os.path.exists(target_path) and os.path.isfile(target_path):
                os.remove(target_path)
                return True
        except: pass
        return False
    def open_file(self, folder_type, relative_path):
        if folder_type != 'config' or ".." in relative_path: return
        target_path = os.path.join(self.game_root, ".minecraft", "versions", TARGET_VERSION_NAME, "config", relative_path)
        if not os.path.exists(target_path):
             target_path = os.path.join(self.game_root, "versions", TARGET_VERSION_NAME, "config", relative_path)
        if os.path.exists(target_path):
            try: os.startfile(target_path)
            except: pass
    
    # === 更新器自我更新逻辑 ===

    def check_launcher_self_update(self):
        """
        检查更新器自身是否需要更新，访问 tcymc.space/update/Updater-latest.json
        """
        url = "https://tcymc.space/update/Updater-latest.json"
        try:
            req = urllib.request.Request(
                url, 
                headers={'User-Agent': 'TCYClientUpdater/1.0'}
            )
            context = ssl._create_unverified_context()
            with urllib.request.urlopen(req, timeout=5, context=context) as response:
                launcher_info = json.loads(response.read().decode('utf-8'))
            
            remote_ver = launcher_info.get("version", "0.0.0")
            
            if remote_ver != LAUNCHER_INTERNAL_VERSION: 
                self.log(f"发现更新器新版本: {remote_ver} (当前: {LAUNCHER_INTERNAL_VERSION})")
                
                msg = f"发现更新器新版本 ({remote_ver})！\n\n更新内容：\n{launcher_info.get('desc', '无')}\n\n点击确定将自动下载并重启。"
                if global_window:
                    do_update = global_window.evaluate_js(f"confirm(`{msg}`)")
                    if do_update:
                        dl_url = launcher_info.get('url')
                        # 更新器更新也尝试走镜像加速
                        prefix = self.cfg_mgr.config.get("mirror_prefix", "https://gh-proxy.org/")
                        if "github.com" in dl_url and prefix:
                             if not dl_url.startswith(prefix):
                                dl_url = prefix + dl_url

                        # 👇 修改了这里：把 remote_ver 传进去
                        self.perform_self_update(dl_url, remote_ver)
                        return True 
        except Exception as e:
            self.log(f"自更新检查跳过: {e}")
        
        return False

    def perform_self_update(self, url, version):
        """下载新版 EXE 并执行替换脚本（强制重命名为 TCYClientUpdater-版本号.exe）"""
        try:
            self.log(f"正在下载新版更新器: {version}...")
            
            # 1. 定义文件名
            temp_download_name = "TCY-Client-Updater.new" # 下载时的临时名
            current_exe = os.path.basename(sys.executable) # 当前正在运行的文件名
            
            # 构建带有版本号的新文件名
            new_exe_name = f"TCYClientUpdater-{version}.exe" 
            
            def report(block_num, block_size, total_size):
                 if total_size > 0:
                    percent = min(100, int(block_num * block_size * 100 / total_size))
                    if percent % 10 == 0: self.log(f"自更新下载中... {percent}%")

            # 2. 下载到临时文件
            urllib.request.urlretrieve(url, temp_download_name, report)
            
            # 3. 生成批处理脚本
            # 逻辑：删除旧文件名 -> 把下载的临时文件重命名为“TCYClientUpdater-1.x.x.exe” -> 启动新文件
            bat_script = "update_self.bat"
            with open(bat_script, "w", encoding="gbk") as f:
                f.write("@echo off\n")
                f.write("echo 正在应用更新，请稍候...\n")
                # 等待主程序退出
                f.write("timeout /t 3 /nobreak > nul\n") 
                
                # 删除旧版本文件 (current_exe)
                f.write(f'if exist "{current_exe}" del "{current_exe}"\n')
                
                # 删除可能存在的同名旧版本目标文件 (防止重命名冲突)
                f.write(f'if exist "{new_exe_name}" del "{new_exe_name}"\n')
                
                # 将下载好的临时文件重命名为新的版本号文件名
                f.write(f'move "{temp_download_name}" "{new_exe_name}"\n')
                
                # 启动新的 exe
                f.write(f'start "" "{new_exe_name}"\n')
                
                # 删除脚本自己
                f.write(f'del "{bat_script}"\n')
            
            self.log(f"下载完成，准备重启至: {new_exe_name}")
            
            # 4. 执行脚本并退出
            os.system(f'start {bat_script}')
            sys.exit(0)
            
        except Exception as e:
            self.log(f"自我更新失败: {e}")
            if global_window:
                global_window.evaluate_js(f"alert('自我更新失败: {str(e)}')")

    # === 在线更新相关逻辑 (序列化) ===

    def get_local_version(self):
        return self.cfg_mgr.config.get("current_version", INITIAL_VERSION)

    def record_skipped_version(self, version):
        pass # 前端不再直接调用此方法，改为在批量更新后统一计算

    def check_online_update(self):
        threading.Thread(target=self._check_update_thread).start()

    def _check_update_thread(self):
        if self.check_launcher_self_update(): return

        url = "https://tcymc.space/update/latest.json"
        try:
            self.log("正在获取客户端版本信息...")
            req = urllib.request.Request(
                url, 
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 TCYClientUpdater/1.0'}
            )
            context = ssl._create_unverified_context()

            with urllib.request.urlopen(req, timeout=10, context=context) as response:
                data = json.loads(response.read().decode('utf-8'))
                
            local_ver = self.get_local_version()
            skipped_list = self.cfg_mgr.config.get("skipped_versions", [])
            
            # === [核心重构] 构建更新队列 ===
            # 我们需要找出所有“比当前版本新”或者“虽然旧但被跳过”的版本
            updates_queue = []
            
            if 'history' in data and isinstance(data['history'], list):
                # 假设 history 是按时间倒序（最新在最前），我们将其反转为正序处理
                # 或者直接遍历，只要版本匹配条件就加入
                
                # 为了按顺序展示，我们先收集所有候选，然后按版本号排序
                candidates = []
                for item in data['history']:
                    v = item.get('version')
                    # 判定条件：版本号 > 本地版本 OR 版本号在跳过列表中
                    # 注意：字符串比较版本号需谨慎，最好保证格式统一
                    if v > local_ver or v in skipped_list:
                        candidates.append(item)
                
                # 按版本号从小到大排序 (确保先装旧的补丁，再装新的)
                candidates.sort(key=lambda x: x.get('version', '0'))
                updates_queue = candidates

            if len(updates_queue) > 0:
                self.log(f"检测到 {len(updates_queue)} 个待更新版本")
                # 将队列发送给前端，前端生成列表供用户勾选
                if global_window:
                    global_window.evaluate_js(f"showUpdateListModal({json.dumps(updates_queue)})")
            else:
                self.log(f"当前已是最新版本 ({local_ver})。")
                if global_window:
                    global_window.evaluate_js("alert('当前已是最新版本！')")
                    
        except Exception as e:
            self.log(f"检查更新失败: {e}")
            if global_window:
                global_window.evaluate_js(f"alert('检查更新失败：{str(e)}')")
                global_window.evaluate_js("resetUpdateModalState()")

    # ===批量更新执行逻辑 ===
    # 前端会发回一个列表：[{version:..., url:..., ...}, {...}] (用户勾选的 + 强制的)
    def start_update_sequence(self, update_list_json, source_type):
        threading.Thread(target=self._sequence_thread, args=(update_list_json, source_type)).start()

    def _sequence_thread(self, update_list_json, source_type):
        try:
            updates = json.loads(update_list_json)
            total_updates = len(updates)
            
            self.log(f"开始批量更新流程，共 {total_updates} 个版本...")
            
            # 获取当前所有可用的“可选版本”列表，用于计算稍后要存入 skipped 的内容
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
                except Exception as e:
                    self.log(f"版本 {ver} 更新失败: {e}")
                    if global_window:
                        global_window.evaluate_js(f"alert('版本 {ver} 更新失败，流程中止。')")
                    break # 中断后续更新
            
            # 更新完成后，处理版本号和跳过列表
            if successful_versions:
                newest_ver = successful_versions[-1] # 假设列表是按顺序的
                current_ver = self.get_local_version()
                
                # 只有当新安装的版本确实比当前版本新时，才更新 version
                if newest_ver > current_ver:
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
                
                # 3. 这里的逻辑略复杂：我们怎么知道哪些被用户“取消勾选”了？
                # 实际上，_check_update_thread 里找到的所有 candidates，减去 successful_versions，剩下的就是被跳过的
                # 但这里我们在后端拿不到完整的 candidates。
                # 简化逻辑：前端发过来的 update_list_json 已经是用户“确认要装”的。
                # 所以我们只需要把“装成功的”移除。
                # 那“新增的跳过”怎么加？
                # 答：需要前端传另一个参数，或者由前端调用 record_skip。
                # 为了简单可靠，我们在前端处理“记录跳过”。(见前端代码)
                
                self.cfg_mgr.save_config({"skipped_versions": list(new_skipped)})
                
            self.log("🎉 所有选定更新已处理完毕！")
            if global_window:
                global_window.evaluate_js("updateDownloadProgress(100)")
                global_window.evaluate_js("alert('更新流程结束！请手动关闭本更新器,重启客户端生效。')")
                global_window.evaluate_js("resetUpdateModalState()")
                global_window.evaluate_js(f"document.getElementById('current-ver-display').innerText = '{self.get_local_version()}'")

        except Exception as e:
            self.log(f"批量更新流程异常: {e}")
            if global_window: global_window.evaluate_js("resetUpdateModalState()")

# 复用并改造原 _download_thread + _update_thread 为同步函数
    def _perform_single_update(self, url, source_type):
        # 1. 下载骨架包
        if source_type == 'cn':
            prefix = self.cfg_mgr.config.get("mirror_prefix", "https://gh-proxy.org/")
            if "github.com" in url and prefix:
                 if not url.startswith(prefix):
                    url = prefix + url
        
        path = urlparse(url).path
        filename = os.path.basename(path)
        if not filename.lower().endswith(".zip"): 
            filename = "update_temp.zip"
        
        save_path = os.path.join(self.game_root, filename)
        self.log(f"下载配置包: {filename}")
        
        # === [速度计算状态初始化] ===
        dl_state = {'start': time.time(), 'last_update': 0}

        def report_dl(block_num, block_size, total_size):
            if total_size > 0:
                downloaded = block_num * block_size
                percent = min(100, int(downloaded * 100 / total_size))
                
                # 计算瞬时速度
                elapsed = time.time() - dl_state['start']
                speed_str = "0 KB/s"
                if elapsed > 0.1:
                    speed = downloaded / elapsed
                    if speed > 1024*1024: speed_str = f"{speed/1024/1024:.1f} MB/s"
                    else: speed_str = f"{speed/1024:.0f} KB/s"
                
                # 限制刷新频率 (防止UI卡死)
                if time.time() - dl_state['last_update'] > 0.1 or percent >= 100:
                    dl_state['last_update'] = time.time()
                    if global_window:
                        # 调用前端新函数: updateProgressDetails(percent, speed, status)
                        global_window.evaluate_js(f"updateProgressDetails({percent}, '{speed_str}', '正在获取配置包...')")

        urllib.request.urlretrieve(url, save_path, report_dl)
        
        # 2. 解压与执行
        zip_full_path = os.path.abspath(save_path)
        temp_dir = os.path.join(self.game_root, "temp_update_tcy")
        
        try:
            if os.path.exists(temp_dir): shutil.rmtree(temp_dir)
            with zipfile.ZipFile(zip_full_path, 'r') as zf:
                for file in zf.namelist(): zf.extract(file, temp_dir)
            
            manifest_path = os.path.join(temp_dir, "manifest.json")
            data = {}
            if os.path.exists(manifest_path):
                with open(manifest_path, 'r', encoding='utf-8') as f: data = json.load(f)
            
            # === [统计总任务数] ===
            actions = data.get('actions', [])
            external_files = data.get('external_files', [])
            total_ops = len(actions) + len(external_files)
            current_op = 0
            
            # 辅助函数：更新进度文字
            def report_step(name, speed="--"):
                msg = f"正在处理 ({current_op}/{total_ops}): {name}"
                p = int((current_op / total_ops) * 100) if total_ops > 0 else 100
                if global_window:
                    global_window.evaluate_js(f"updateProgressDetails({p}, '{speed}', '{msg}')")

            # Actions
            for action in actions:
                current_op += 1
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
                                except: pass
                elif action.get('type') == 'delete':
                     try: os.remove(os.path.join(self.game_root, action.get('path')))
                     except: pass
                elif action.get('type') == 'copy_folder':
                    src = os.path.join(temp_dir, action.get('src'))
                    dest = os.path.join(self.game_root, action.get('dest'))
                    if os.path.exists(src):
                        try:
                            shutil.copytree(src, dest, dirs_exist_ok=True)
                            self.log(f"合并配置文件夹: {action.get('src')} -> {dest}")
                        except Exception as e:
                            self.log(f"合并文件夹失败: {e}")

            # External Files
            mirror_prefix = self.cfg_mgr.config.get("mirror_prefix", "https://gh-proxy.org/")
            
            for item in external_files:
                current_op += 1
                target_path = os.path.join(self.game_root, item['path'])
                
                # 检查文件是否存在且大小一致 (允许 1KB 误差)
                if os.path.exists(target_path):
                    if abs(os.path.getsize(target_path) - item.get('size', 0)) < 1024: 
                        report_step(f"跳过已存在: {item['name']}")
                        continue
                
                d_url = item['url']
                if source_type == 'cn' and "github.com" in d_url:
                    if mirror_prefix and not d_url.startswith(mirror_prefix): 
                        d_url = mirror_prefix + d_url
                
                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                self.log(f"补齐: {item['name']}")
                
                # === [带速度计算的文件下载回调] ===
                dl_state['start'] = time.time() # 重置计时器
                
                def file_report(block_num, block_size, total_size):
                    if total_size > 0:
                        downloaded = block_num * block_size
                        
                        # 计算速度
                        elapsed = time.time() - dl_state['start']
                        speed_str = "0 KB/s"
                        if elapsed > 0.1:
                            speed = downloaded / elapsed
                            if speed > 1024*1024: speed_str = f"{speed/1024/1024:.1f} MB/s"
                            else: speed_str = f"{speed/1024:.0f} KB/s"
                        
                        # 限制刷新频率
                        if time.time() - dl_state['last_update'] > 0.1:
                            dl_state['last_update'] = time.time()
                            if global_window:
                                # 计算当前文件的进度百分比 (仅用于视觉反馈)
                                sub_p = int(downloaded * 100 / total_size)
                                # 构造显示文本
                                msg = f"下载文件 ({current_op}/{total_ops}): {item['name']} ({sub_p}%)"
                                # 注意：这里百分比用 sub_p 让用户看到进度条在跑
                                global_window.evaluate_js(f"updateProgressDetails({sub_p}, '{speed_str}', '{msg}')")

                urllib.request.urlretrieve(d_url, target_path, file_report)

        finally:
            if os.path.exists(temp_dir): shutil.rmtree(temp_dir)
            if os.path.exists(zip_full_path): os.remove(zip_full_path)

    # 供前端调用：记录跳过的版本
    def add_skipped_version(self, version):
        skipped = self.cfg_mgr.config.get("skipped_versions", [])
        if version not in skipped:
            skipped.append(version)
            self.cfg_mgr.save_config({"skipped_versions": skipped})
            self.log(f"已标记跳过: {version}")

def main():
    freeze_support()
    global global_window
    try:
        api = Api()
        # === ✅读取保存的窗口大小 ===
        # 获取配置字符串，例如 "1280x720"
        size_str = api.cfg_mgr.config.get("window_size", "950x600")
        try:
            # 解析宽高
            init_w, init_h = map(int, size_str.split('x'))
        except:
            init_w, init_h = 950, 600

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