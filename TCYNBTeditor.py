# -*- coding: utf-8 -*-
"""
TCY NBT Editor — 独立 NBT 编辑器模块
从 TCYServer_MCUpdater.py 分离，提供 NBT 解析/写入 + 独立编辑器窗口。

调用方式:
    from TCYNBTeditor import NbtIO, open_nbt_editor
    NbtIO.read(path)           # 在主程序中解析 level.dat
    open_nbt_editor(api, ...)  # 打开独立 NBT 编辑器窗口
"""

import os
import sys
import json
import gzip
import struct
import io
import threading

import webview


# ============================================================
# Resource path helper (same as main app)
# ============================================================

def _get_resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


# ============================================================
# NbtIO — Self-contained NBT binary parser and writer
# ============================================================

class NbtIO:
    """NBT binary parser/writer using Python stdlib only.

    Handles all 13 NBT tag types (Java Edition big-endian format).
    Long values are serialized as strings to avoid JS Number.MAX_SAFE_INTEGER overflow.
    """

    TAG_END = 0
    TAG_BYTE = 1
    TAG_SHORT = 2
    TAG_INT = 3
    TAG_LONG = 4
    TAG_FLOAT = 5
    TAG_DOUBLE = 6
    TAG_BYTE_ARRAY = 7
    TAG_STRING = 8
    TAG_LIST = 9
    TAG_COMPOUND = 10
    TAG_INT_ARRAY = 11
    TAG_LONG_ARRAY = 12

    STRUCT_FMTS = {1: '>b', 2: '>h', 3: '>i', 4: '>q', 5: '>f', 6: '>d'}
    STRUCT_SIZES = {1: 1, 2: 2, 3: 4, 4: 8, 5: 4, 6: 8}

    @classmethod
    def read(cls, path):
        """Read a gzip-compressed (or uncompressed) NBT file. Returns JSON-serializable dict."""
        with open(path, 'rb') as f:
            raw = f.read()
        try:
            raw = gzip.decompress(raw)
        except OSError:
            pass  # uncompressed NBT
        buf = io.BytesIO(raw)
        tag_type = struct.unpack('>b', buf.read(1))[0]
        name = cls._read_str(buf)
        value = cls._read_val(buf, tag_type)
        return {"type": tag_type, "name": name, "value": value}

    @classmethod
    def _read_str(cls, buf):
        length = struct.unpack('>H', buf.read(2))[0]
        return buf.read(length).decode('utf-8', errors='replace')

    @classmethod
    def _read_val(cls, buf, t):
        if t in cls.STRUCT_FMTS:
            val = struct.unpack(cls.STRUCT_FMTS[t], buf.read(cls.STRUCT_SIZES[t]))[0]
            if t == cls.TAG_LONG:
                return str(val)
            return val
        if t == cls.TAG_STRING:
            return cls._read_str(buf)
        if t == cls.TAG_BYTE_ARRAY:
            n = struct.unpack('>i', buf.read(4))[0]
            return {"array_type": "byte", "values": list(struct.unpack(f'>{n}b', buf.read(n)))}
        if t == cls.TAG_INT_ARRAY:
            n = struct.unpack('>i', buf.read(4))[0]
            return {"array_type": "int", "values": list(struct.unpack(f'>{n}i', buf.read(n * 4)))}
        if t == cls.TAG_LONG_ARRAY:
            n = struct.unpack('>i', buf.read(4))[0]
            return {"array_type": "long", "values": [str(v) for v in struct.unpack(f'>{n}q', buf.read(n * 8))]}
        if t == cls.TAG_LIST:
            et = struct.unpack('>b', buf.read(1))[0]
            n = struct.unpack('>i', buf.read(4))[0]
            items = []
            for i in range(n):
                val = cls._read_val(buf, et)
                items.append({"type": et, "name": "", "value": val})
            return {"list_type": et, "items": items}
        if t == cls.TAG_COMPOUND:
            children = []
            while True:
                ct = struct.unpack('>b', buf.read(1))[0]
                if ct == cls.TAG_END:
                    break
                cn = cls._read_str(buf)
                cv = cls._read_val(buf, ct)
                children.append({"type": ct, "name": cn, "value": cv})
            return children
        return None

    @classmethod
    def write(cls, path, nbt_dict):
        """Serialize NBT dict back to a gzip-compressed binary file."""
        buf = io.BytesIO()
        cls._write_named(buf, nbt_dict)
        with gzip.open(path, 'wb') as f:
            f.write(buf.getvalue())

    @classmethod
    def _write_named(cls, buf, node):
        t = node["type"]
        buf.write(struct.pack('>b', t))
        name_bytes = (node.get("name") or "").encode('utf-8')
        buf.write(struct.pack('>H', len(name_bytes)))
        buf.write(name_bytes)
        cls._write_val(buf, t, node["value"])

    @classmethod
    def _write_str(cls, buf, s):
        b = str(s).encode('utf-8')
        buf.write(struct.pack('>H', len(b)))
        buf.write(b)

    @classmethod
    def _write_val(cls, buf, t, v):
        if t in cls.STRUCT_FMTS:
            if t in (1, 2, 3, 4):
                buf.write(struct.pack(cls.STRUCT_FMTS[t], int(v)))
            else:
                buf.write(struct.pack(cls.STRUCT_FMTS[t], float(v)))
            return
        if t == cls.TAG_STRING:
            cls._write_str(buf, v)
            return
        if t == cls.TAG_BYTE_ARRAY:
            vals = v["values"]
            buf.write(struct.pack('>i', len(vals)))
            buf.write(struct.pack(f'>{len(vals)}b', *vals))
            return
        if t == cls.TAG_INT_ARRAY:
            vals = v["values"]
            buf.write(struct.pack('>i', len(vals)))
            buf.write(struct.pack(f'>{len(vals)}i', *vals))
            return
        if t == cls.TAG_LONG_ARRAY:
            vals = [int(x) for x in v["values"]]
            buf.write(struct.pack('>i', len(vals)))
            buf.write(struct.pack(f'>{len(vals)}q', *vals))
            return
        if t == cls.TAG_LIST:
            et = v["list_type"]
            items = v["items"]
            buf.write(struct.pack('>b', et))
            buf.write(struct.pack('>i', len(items)))
            for item in items:
                # Items are wrapped as {type, name, value} dicts
                val = item["value"] if isinstance(item, dict) and "value" in item else item
                cls._write_val(buf, et, val)
            return
        if t == cls.TAG_COMPOUND:
            for child in (v or []):
                cls._write_named(buf, child)
            buf.write(struct.pack('>b', cls.TAG_END))

    # ---- Region (.mca) file support ----

    @classmethod
    def read_mca(cls, path):
        """Read a .mca region file and return metadata for all non-empty chunks.

        Returns:
            list of {x, z, offset, size, timestamp} for each existing chunk.
        """
        with open(path, 'rb') as f:
            raw = f.read()
        if len(raw) < 8192:
            return []
        chunks = []
        for i in range(1024):
            z_rel = i // 32
            x_rel = i % 32
            loc = struct.unpack_from('>I', raw, i * 4)[0]
            offset = (loc >> 8) * 4096
            sectors = loc & 0xFF
            ts = struct.unpack_from('>I', raw, 4096 + i * 4)[0]
            if offset == 0 and sectors == 0:
                continue
            chunks.append({"x": x_rel, "z": z_rel, "offset": offset, "sectors": sectors, "timestamp": ts})
        return chunks

    @classmethod
    def read_mca_chunk(cls, path, offset):
        """Read a single chunk from a .mca file at the given byte offset.

        Returns:
            JSON-serializable NBT dict or None on failure.
        """
        with open(path, 'rb') as f:
            f.seek(offset)
            header = f.read(5)
            if len(header) < 5:
                return None
            length = struct.unpack('>I', header[:4])[0]
            compression = header[4]
            data = f.read(length - 1)

        if compression == 1:
            import zlib
            data = gzip.decompress(data)
        elif compression == 2:
            import zlib
            data = zlib.decompress(data)
        elif compression == 3:
            pass  # uncompressed
        else:
            return None

        buf = io.BytesIO(data)
        tag_type = struct.unpack('>b', buf.read(1))[0]
        name = cls._read_str(buf)
        value = cls._read_val(buf, tag_type)
        return {"type": tag_type, "name": name, "value": value}

    # ---- JSON export helper ----

    @classmethod
    def nbt_to_json(cls, nbt_dict):
        """Convert NBT tree to a human-readable JSON-compatible dict."""
        return cls._node_to_json(nbt_dict)

    @classmethod
    def _node_to_json(cls, node):
        t = node["type"]
        name = node.get("name", "")
        v = node["value"]
        if t == cls.TAG_COMPOUND:
            children = {}
            for child in (v or []):
                key = child.get("name", "")
                children[key] = cls._node_to_json(child)
            return {"_type": "Compound", "_name": name, "_value": children}
        elif t == cls.TAG_LIST:
            items = [cls._node_to_json(item) for item in (v.get("items", []) if v else [])]
            return {"_type": "List", "_name": name, "_listType": v.get("list_type", 0) if v else 0, "_value": items}
        elif t in (cls.TAG_BYTE_ARRAY, cls.TAG_INT_ARRAY, cls.TAG_LONG_ARRAY):
            atype = {7: "ByteArray", 11: "IntArray", 12: "LongArray"}[t]
            return {"_type": atype, "_name": name, "_value": v.get("values", []) if v else []}
        else:
            tname = {1: "Byte", 2: "Short", 3: "Int", 4: "Long", 5: "Float", 6: "Double", 8: "String"}.get(t, str(t))
            return {"_type": tname, "_name": name, "_value": v}

    @classmethod
    def json_to_nbt(cls, json_dict):
        """Convert a JSON dict (from nbt_to_json) back to NBT tree structure."""
        return cls._json_to_node(json_dict)

    @classmethod
    def _json_to_node(cls, d):
        type_map = {"Byte": 1, "Short": 2, "Int": 3, "Long": 4, "Float": 5, "Double": 6,
                     "ByteArray": 7, "String": 8, "List": 9, "Compound": 10, "IntArray": 11, "LongArray": 12}
        tname = d.get("_type", "Compound")
        t = type_map.get(tname, 10)
        name = d.get("_name", "")
        v = d.get("_value")
        if t == 10:  # Compound
            children = []
            if isinstance(v, dict):
                for key, child in v.items():
                    children.append(cls._json_to_node(child))
            return {"type": t, "name": name, "value": children}
        elif t == 9:  # List
            lt = d.get("_listType", 1)
            items = [cls._json_to_node(item) for item in (v or [])]
            return {"type": t, "name": name, "value": {"list_type": lt, "items": items}}
        elif t in (7, 11, 12):
            atype = {7: "byte", 11: "int", 12: "long"}[t]
            vals = v if isinstance(v, list) else []
            return {"type": t, "name": name, "value": {"array_type": atype, "values": vals}}
        else:
            return {"type": t, "name": name, "value": v}


# ============================================================
# NbtEditorApi — pywebview JS API for the editor window
# ============================================================

class NbtEditorApi:
    """Lightweight API exposed to the NBT editor window via pywebview js_api."""

    _config_lock = threading.Lock()

    def nbt_open_file(self, abs_path):
        """Load a .dat/.dat_old NBT file and return its tree as JSON."""
        if abs_path.lower().endswith('.mca'):
            return self.nbt_open_mca_file(abs_path)
        if not (abs_path.endswith('.dat') or abs_path.endswith('.dat_old')):
            return json.dumps({"success": False, "error": "只支持 .dat / .dat_old / .mca 文件"})
        try:
            nbt_tree = NbtIO.read(abs_path)
            self._add_recent_file(abs_path)
            return json.dumps({"success": True, "tree": nbt_tree, "path": abs_path}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)})

    def nbt_save_file(self, abs_path, nbt_json):
        """Write an edited NBT tree back to disk."""
        if not (abs_path.endswith('.dat') or abs_path.endswith('.dat_old')):
            return json.dumps({"success": False, "error": "只支持 .dat / .dat_old 文件"})
        try:
            nbt_tree = json.loads(nbt_json)
            NbtIO.write(abs_path, nbt_tree)
            return json.dumps({"success": True})
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)})

    def nbt_save_as(self, nbt_json):
        """Save NBT tree to a new file chosen by the user via a save dialog."""
        try:
            # Find the NBT editor window
            nbt_win = None
            for w in webview.windows:
                if 'NBT' in (w.title or ''):
                    nbt_win = w
                    break
            if not nbt_win:
                nbt_win = webview.windows[-1] if webview.windows else None
            if not nbt_win:
                return json.dumps({"success": False, "error": "找不到编辑器窗口"})

            result = nbt_win.create_file_dialog(
                webview.SAVE_DIALOG,
                file_types=('NBT Files (*.dat;*.dat_old)', 'All Files (*.*)')
            )
            if not result:
                return json.dumps({"success": False, "error": "cancelled"})
            save_path = result if isinstance(result, str) else result[0]
            nbt_tree = json.loads(nbt_json)
            NbtIO.write(save_path, nbt_tree)
            self._add_recent_file(save_path)
            return json.dumps({"success": True, "path": save_path})
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)})

    def nbt_export_json(self, nbt_json):
        """Export the current NBT tree as JSON to a user-chosen file."""
        try:
            nbt_win = None
            for w in webview.windows:
                if 'NBT' in (w.title or ''):
                    nbt_win = w
                    break
            if not nbt_win:
                nbt_win = webview.windows[-1] if webview.windows else None
            if not nbt_win:
                return json.dumps({"success": False, "error": "找不到编辑器窗口"})

            result = nbt_win.create_file_dialog(
                webview.SAVE_DIALOG,
                file_types=('JSON Files (*.json)', 'All Files (*.*)')
            )
            if not result:
                return json.dumps({"success": False, "error": "cancelled"})
            save_path = result if isinstance(result, str) else result[0]
            nbt_tree = json.loads(nbt_json)
            json_data = NbtIO.nbt_to_json(nbt_tree)
            with open(save_path, 'w', encoding='utf-8') as f:
                json.dump(json_data, f, indent=2, ensure_ascii=False)
            return json.dumps({"success": True, "path": save_path})
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)})

    def nbt_import_json(self):
        """Import a JSON file and convert it to an NBT tree."""
        try:
            nbt_win = None
            for w in webview.windows:
                if 'NBT' in (w.title or ''):
                    nbt_win = w
                    break
            if not nbt_win:
                nbt_win = webview.windows[-1] if webview.windows else None
            if not nbt_win:
                return json.dumps({"success": False, "error": "找不到编辑器窗口"})

            result = nbt_win.create_file_dialog(
                webview.OPEN_DIALOG,
                file_types=('JSON Files (*.json)', 'All Files (*.*)')
            )
            if not result:
                return json.dumps({"success": False, "error": "cancelled"})
            file_path = result if isinstance(result, str) else result[0]
            with open(file_path, 'r', encoding='utf-8') as f:
                json_data = json.load(f)
            nbt_tree = NbtIO.json_to_nbt(json_data)
            return json.dumps({"success": True, "tree": nbt_tree, "path": file_path}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)})

    def nbt_open_mca_file(self, abs_path):
        """Read a .mca region file and return chunk metadata."""
        if not abs_path.lower().endswith('.mca'):
            return json.dumps({"success": False, "error": "不是 .mca 文件"})
        try:
            chunks = NbtIO.read_mca(abs_path)
            return json.dumps({"success": True, "chunks": chunks, "path": abs_path}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)})

    def nbt_read_mca_chunk(self, mca_path, offset):
        """Read a single chunk from a .mca file."""
        try:
            tree = NbtIO.read_mca_chunk(mca_path, offset)
            if tree is None:
                return json.dumps({"success": False, "error": "无法读取区块数据"})
            return json.dumps({"success": True, "tree": tree}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)})

    def nbt_write_log(self, log_text, file_hint):
        """Write operation log to NBTEditor-log/ directory."""
        try:
            if hasattr(sys, '_MEIPASS'):
                base = os.path.dirname(sys.executable)
            else:
                base = os.path.abspath(".")
            log_dir = os.path.join(base, "NBTEditor-log")
            os.makedirs(log_dir, exist_ok=True)
            # Generate filename from date and optional file hint
            from datetime import datetime
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_hint = "".join(c if c.isalnum() or c in '-_.' else '_' for c in (file_hint or "session"))
            log_path = os.path.join(log_dir, f"nbt_log_{ts}_{safe_hint}.log")
            with open(log_path, 'w', encoding='utf-8') as f:
                f.write(log_text)
            return json.dumps({"success": True, "path": log_path})
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)})

    def nbt_append_log(self, line):
        """Append a single log line to today's session log file."""
        try:
            if hasattr(sys, '_MEIPASS'):
                base = os.path.dirname(sys.executable)
            else:
                base = os.path.abspath(".")
            log_dir = os.path.join(base, "NBTEditor-log")
            os.makedirs(log_dir, exist_ok=True)
            from datetime import datetime
            today = datetime.now().strftime("%Y%m%d")
            log_path = os.path.join(log_dir, f"nbt_session_{today}.log")
            with open(log_path, 'a', encoding='utf-8') as f:
                f.write(line + "\n")
            return json.dumps({"success": True})
        except Exception:
            return json.dumps({"success": False})

    def nbt_scan_folder(self, saves_dir, world_folder):
        """Recursively scan a save folder and return a tree structure for the file explorer."""
        world_path = os.path.join(saves_dir, world_folder)
        if not os.path.isdir(world_path):
            return json.dumps({"success": False, "error": "存档文件夹不存在"})
        try:
            tree = self._scan_dir(world_path, world_folder)
            return json.dumps({"success": True, "tree": tree}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)})

    # ---- Recent files & Bookmarks ----

    def _get_config_path(self):
        if hasattr(sys, '_MEIPASS'):
            base = os.path.dirname(sys.executable)
        else:
            base = os.path.abspath(".")
        return os.path.join(base, "launcher_settings.json")

    def _read_config(self):
        path = self._get_config_path()
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _write_config_fields(self, updates):
        """Merge updates into launcher_settings.json (thread-safe)."""
        with self._config_lock:
            cfg = self._read_config()
            cfg.update(updates)
            try:
                with open(self._get_config_path(), 'w', encoding='utf-8') as f:
                    json.dump(cfg, f, indent=4, ensure_ascii=False)
            except Exception:
                pass

    def _add_recent_file(self, abs_path):
        cfg = self._read_config()
        recent = cfg.get("nbt_recent_files", [])
        # Remove duplicate then prepend
        recent = [r for r in recent if r != abs_path]
        recent.insert(0, abs_path)
        recent = recent[:20]  # keep max 20
        self._write_config_fields({"nbt_recent_files": recent})

    def nbt_get_recent_files(self):
        cfg = self._read_config()
        recent = cfg.get("nbt_recent_files", [])
        # Filter to only existing files
        valid = [r for r in recent if os.path.exists(r)]
        return json.dumps({"success": True, "files": valid})

    def nbt_get_bookmarks(self):
        cfg = self._read_config()
        bookmarks = cfg.get("nbt_bookmarks", [])
        return json.dumps({"success": True, "bookmarks": bookmarks})

    def nbt_add_bookmark(self, abs_path, label):
        cfg = self._read_config()
        bookmarks = cfg.get("nbt_bookmarks", [])
        # No duplicates by path
        if any(b["path"] == abs_path for b in bookmarks):
            return json.dumps({"success": False, "error": "already_bookmarked"})
        bookmarks.append({"path": abs_path, "label": label})
        self._write_config_fields({"nbt_bookmarks": bookmarks})
        return json.dumps({"success": True})

    def nbt_remove_bookmark(self, abs_path):
        cfg = self._read_config()
        bookmarks = cfg.get("nbt_bookmarks", [])
        bookmarks = [b for b in bookmarks if b["path"] != abs_path]
        self._write_config_fields({"nbt_bookmarks": bookmarks})
        return json.dumps({"success": True})

    def nbt_get_theme(self):
        """Read theme settings from launcher_settings.json for the NBT editor."""
        cfg = self._read_config()
        theme = {
            "accent_color": cfg.get("accent_color", "#f59e0b"),
            "text_color": cfg.get("text_color", "#333333"),
            "font_family": cfg.get("font_family", "'Segoe UI', system-ui, sans-serif"),
            "visual_effect": cfg.get("visual_effect", "glass"),
            "bg_image": cfg.get("custom_bg_data", ""),
            "bg_type": cfg.get("bg_type", "default"),
        }
        return json.dumps({"success": True, "theme": theme})

    def _scan_dir(self, dir_path, display_name):
        """Build a tree node for a directory."""
        node = {"type": "folder", "name": display_name, "path": dir_path, "children": []}
        try:
            entries = sorted(os.listdir(dir_path))
        except PermissionError:
            return node

        # Separate folders and files
        folders = []
        files = []
        for entry in entries:
            full = os.path.join(dir_path, entry)
            if os.path.isdir(full):
                # Only include folders that contain .dat files (recursively)
                child = self._scan_dir(full, entry)
                if self._has_dat_files(child):
                    folders.append(child)
            elif entry.lower().endswith('.dat') or entry.lower().endswith('.dat_old') or entry.lower().endswith('.mca'):
                files.append({
                    "type": "file",
                    "name": entry,
                    "path": full
                })

        node["children"] = folders + files
        return node

    def _has_dat_files(self, node):
        """Check if a folder node contains any .dat files (directly or nested)."""
        if not node.get("children"):
            return False
        for child in node["children"]:
            if child["type"] == "file":
                return True
            if child["type"] == "folder" and self._has_dat_files(child):
                return True
        return False


# ============================================================
# open_nbt_editor — Launch the editor window
# ============================================================

def open_nbt_editor(saves_dir, world_folder):
    """Open the NBT editor in a separate pywebview window.

    Args:
        saves_dir: Absolute path to the saves directory.
        world_folder: Name of the world folder inside saves_dir.

    Returns:
        JSON string with {success: True/False, error?: str}
    """
    world_path = os.path.join(saves_dir, world_folder)
    if not os.path.isdir(world_path):
        return json.dumps({"success": False, "error": "存档文件夹不存在"})

    try:
        html_path = _get_resource_path("TCYNBTeditor.html")
        if not os.path.exists(html_path):
            return json.dumps({"success": False, "error": "找不到 NBT 编辑器前端文件"})

        html_url = f"file:///{os.path.abspath(html_path).replace(os.sep, '/')}"
        api = NbtEditorApi()

        nbt_win = webview.create_window(
            f'NBT Editor — {world_folder}',
            url=html_url,
            js_api=api,
            width=1100,
            height=750,
            resizable=True,
        )

        saves_dir_json = json.dumps(saves_dir, ensure_ascii=False)
        folder_json = json.dumps(world_folder, ensure_ascii=False)

        def _on_loaded():
            import time
            time.sleep(0.3)
            try:
                nbt_win.evaluate_js(f"initExplorer({saves_dir_json}, {folder_json})")
            except Exception:
                pass

        nbt_win.events.loaded += _on_loaded
        return json.dumps({"success": True})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


def open_nbt_editor_empty():
    """Open the NBT editor in empty workspace mode.

    Returns:
        JSON string with {success: True/False, error?: str}
    """
    try:
        html_path = _get_resource_path("TCYNBTeditor.html")
        if not os.path.exists(html_path):
            return json.dumps({"success": False, "error": "找不到 NBT 编辑器前端文件"})

        html_url = f"file:///{os.path.abspath(html_path).replace(os.sep, '/')}"
        api = NbtEditorApi()

        nbt_win = webview.create_window(
            'NBT Editor — 空白工作台',
            url=html_url,
            js_api=api,
            width=1100,
            height=750,
            resizable=True,
        )

        def _on_loaded():
            import time
            time.sleep(0.3)
            try:
                nbt_win.evaluate_js("initExplorer(null, '空白工作台')")
                nbt_win.evaluate_js("setStatus('请拖入nbt文件或nbt文件夹，以读取目录或读取文件进行编辑。')")
            except Exception:
                pass

        nbt_win.events.loaded += _on_loaded
        return json.dumps({"success": True})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


def open_nbt_editor_standalone(abs_path):
    """Open the NBT editor for a single .dat file (from recent/bookmark).

    Args:
        abs_path: Absolute path to a .dat file.

    Returns:
        JSON string with {success: True/False, error?: str}
    """
    if not os.path.isfile(abs_path):
        return json.dumps({"success": False, "error": "文件不存在"})

    try:
        html_path = _get_resource_path("TCYNBTeditor.html")
        if not os.path.exists(html_path):
            return json.dumps({"success": False, "error": "找不到 NBT 编辑器前端文件"})

        html_url = f"file:///{os.path.abspath(html_path).replace(os.sep, '/')}"
        api = NbtEditorApi()

        parent_dir = os.path.dirname(abs_path)
        folder_name = os.path.basename(parent_dir)

        nbt_win = webview.create_window(
            f'NBT Editor — {os.path.basename(abs_path)}',
            url=html_url,
            js_api=api,
            width=1100,
            height=750,
            resizable=True,
        )

        saves_dir_json = json.dumps(os.path.dirname(parent_dir), ensure_ascii=False)
        folder_json = json.dumps(folder_name, ensure_ascii=False)
        file_json = json.dumps(abs_path, ensure_ascii=False)

        def _on_loaded():
            import time
            time.sleep(0.3)
            try:
                nbt_win.evaluate_js(f"initExplorer({saves_dir_json}, {folder_json}, {file_json})")
            except Exception:
                pass

        nbt_win.events.loaded += _on_loaded
        return json.dumps({"success": True})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})
