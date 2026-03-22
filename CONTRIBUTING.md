# CONTRIBUTING — 贡献指南

感谢你对 TCY Client Updater 的关注！无论你是经验丰富的开发者还是刚入门的新手，本文档都会一步步指导你如何参与贡献。

如果你是第一次接手这个项目，先读 [HANDOFF.md](HANDOFF.md) 的“先看这里（3 分钟接手版）”，再回来看本文，会更省时间。

---

## 目录

- [环境准备](#环境准备)
- [项目结构总览](#项目结构总览)
- [开发流程](#开发流程)
- [代码架构详解](#代码架构详解)
- [各模块修改指南](#各模块修改指南)
- [提交规范](#提交规范)
- [版本发布约定](#版本发布约定)
- [常见问题](#常见问题)

---

## 环境准备

### 1. 安装 Python

本项目需要 **Python 3.8+**（推荐 3.10 或以上）。

- Windows 用户：从 [python.org](https://www.python.org/downloads/) 下载安装器，**安装时务必勾选 "Add Python to PATH"**。
- 安装完成后打开 CMD / PowerShell，输入以下命令确认：
  ```bash
  python --version
  # 应该输出类似 Python 3.10.x
  ```

### 2. 安装依赖

本项目依赖：

- 必需：`pywebview`
- 打包：`pyinstaller`
- 可选（仅开发环境图片处理兜底 / 调试）：`Pillow`（import 名为 `PIL`）。当前默认截图缩略图路径走 WebView2 前端生成，不要求玩家额外安装 Pillow。

```bash
pip install pywebview pyinstaller
# 可选：仅在开发环境需要 Pillow 兜底时再安装
pip install pillow
```

- `pywebview`：用于创建桌面窗口并加载 HTML 页面（本项目的 GUI 框架）。
- `pyinstaller`：用于将 Python 脚本打包成单文件 `.exe`（仅打包发布时需要）。

### 3. 克隆代码

```bash
git clone https://github.com/KanameMadoka520/TCY-Client-Updater.git
cd TCY-Client-Updater
```

### 4. 验证能否运行

```bash
python TCYServer_MCUpdater.py
```

程序会打开一个桌面窗口。如果你没有放在正确的游戏目录下，会看到目录校验警告——这是正常行为，点击"强制跳过"即可进入界面。

---

## 项目结构总览

```text
TCY-Client-Updater/
├── TCYServer_MCUpdater.py    # 后端核心桥接 (~5500 行 Python)
├── jvm_advisor.py            # JVM 调优向导后端模块
├── system_overview.py        # 系统概览后端模块
├── TCYNBTeditor.py           # NBT 编辑器后端模块 (~746 行，独立于主程序)
├── TCYNBTeditor.html         # NBT 编辑器前端页面 (~2346 行，VSCode 风格布局)
├── index.html                # 主程序前端壳 (~9300 行，页面容器 + 样式 + 大部分全局 JS)
├── jvm_advisor.js            # JVM 调优向导前端模块
├── system_overview.js        # 系统概览前端模块
├── build.py                  # PyInstaller 打包脚本
├── lib/
│   └── d3.min.js             # d3.js v7 本地离线副本 (力向图渲染用)
├── conflict_rules.json       # 冲突规则模板 (默认空规则)
├── icon.ico                  # 程序图标
├── background.png            # 默认背景图
├── README.md                 # 项目说明文档
├── CONTRIBUTING.md           # 本文件
├── LICENSE                   # CC BY-NC-SA 4.0 协议
├── NBTEditor-log/            # NBT 编辑器操作日志目录 (运行时自动创建)
│   └── nbt_session_YYYY-MM-DD.log  # 按日期分割的会话日志
├── NBTEditor-DevGuide.md     # NBT 编辑器开发指南 (功能路线图与实现方案)
└── VersionJsonEditor/        # TCY Publish Manager (独立的更新发布管理器)
```

### 文件关系一句话总结

> `TCYServer_MCUpdater.py`（后端）启动 pywebview 窗口并加载 `index.html`（前端）。前端通过 `pywebview.api.xxx()` 调用后端方法，后端通过 `window.evaluate_js()` 向前端推送数据。随着功能增多，JVM 调优和系统概览已经拆成独立模块（`jvm_advisor.py/js`、`system_overview.py/js`）；NBT 编辑器仍是完全独立的窗口模块：`TCYNBTeditor.py`（后端）+ `TCYNBTeditor.html`（前端）。

---

## 开发流程

### 完整流程（从 Fork 到 PR）

```
1. Fork 仓库 → 2. 克隆到本地 → 3. 创建功能分支 → 4. 写代码 → 5. 本地测试 → 6. 提交 → 7. 推送 → 8. 发 PR
```

详细步骤：

#### 步骤 1：Fork 仓库
在 GitHub 页面点击右上角 "Fork" 按钮，将仓库复制到你的账号下。

#### 步骤 2：克隆到本地
```bash
git clone https://github.com/你的用户名/TCY-Client-Updater.git
cd TCY-Client-Updater
```

#### 步骤 3：创建功能分支
**永远不要直接在 main 分支上开发！** 请为每个功能或修复创建独立分支：
```bash
git checkout -b feat/你的功能名
# 例如：git checkout -b feat/add-download-speed-limit
# 例如：git checkout -b fix/mod-list-crash
```

#### 步骤 4：写代码
修改你需要改的文件。详见下方 [各模块修改指南](#各模块修改指南)。

#### 步骤 5：本地测试
```bash
# 基本语法检查
python -m py_compile TCYServer_MCUpdater.py jvm_advisor.py system_overview.py

# 运行程序进行手工验证
python TCYServer_MCUpdater.py
```

必须验证的事项（根据你改了什么而定）：
- 程序能正常启动，不报错
- 你改的功能能正常工作
- 没有破坏其他已有功能（重点关注：更新流程、Mod 管理、Config 备份、设置页面）

#### 步骤 6-8：提交 → 推送 → 发 PR
```bash
git add 你改的文件
git commit -m "feat: 你做了什么"
git push origin feat/你的功能名
```
然后在 GitHub 上发起 Pull Request。

---

## 代码架构详解

### 后端 (`TCYServer_MCUpdater.py` + feature modules + `TCYNBTeditor.py`)

主程序后端仍以 `TCYServer_MCUpdater.py` 为核心桥接（~5500 行），但 JVM 调优和系统概览已经拆成独立模块，避免继续把新逻辑堆回主文件。NBT 编辑器依然是完全独立模块（~746 行），持续扩展中。

```
┌─ TCYServer_MCUpdater.py ──────────────────┐
│                                             │
│  ┌─ 文件顶部 ───────────────────────────┐  │
│  │  常量定义 (版本号、URL、路径等)        │  │
│  │  全局变量                             │  │
│  │  from TCYNBTeditor import NbtIO,      │  │
│  │       open_nbt_editor                 │  │
│  └──────────────────────────────────────┘  │
│  ┌─ Api 类 ─────────────────────────────┐  │
│  │  这是核心类，所有公开方法都可被前端调用 │  │
│  │                                       │  │
│  │  ┌─ 初始化 ────────────────────────┐ │  │
│  │  │  __init__: 初始化设置、路径     │ │  │
│  │  └─────────────────────────────────┘ │  │
│  │  ┌─ Mod 管理相关 ──────────────────┐ │  │
│  │  │  get_mods_metadata()             │ │  │
│  │  │  set_mod_enabled()               │ │  │
│  │  │  batch_set_mod_enabled()         │ │  │
│  │  │  get_mod_dependency_graph()      │ │  │
│  │  │  set_mod_dependency_ignore()     │ │  │
│  │  │  _load_conflict_rules()          │ │  │
│  │  │  get_conflict_rules()            │ │  │
│  │  └─────────────────────────────────┘ │  │
│  │  ┌─ Config 备份还原 ───────────────┐ │  │
│  │  │  list_config_subfolders()        │ │  │
│  │  │  create_config_backup()          │ │  │
│  │  │  list_config_backups()           │ │  │
│  │  │  preview_config_restore()        │ │  │
│  │  │  restore_config_backup()         │ │  │
│  │  └─────────────────────────────────┘ │  │
│  │  ┌─ 存档管理 ──────────────────────┐ │  │
│  │  │  list_saves()                    │ │  │
│  │  │  open_nbt_editor_for_save()      │ │  │
│  │  │    → 调用 open_nbt_editor()      │ │  │
│  │  │  _parse_level_dat_metadata()     │ │  │
│  │  │    → 使用 NbtIO.read()           │ │  │
│  │  └─────────────────────────────────┘ │  │
│  │  ┌─ 更新系统 ──────────────────────┐ │  │
│  │  │  preview_update_plan()           │ │  │
│  │  │  start_update_sequence_confirmed│  │  │
│  │  │  _probe_resume_feasibility()     │ │  │
│  │  │  _download_with_resume()         │ │  │
│  │  └─────────────────────────────────┘ │  │
│  │  ┌─ 服务器状态 / 内置浏览器 ──────┐  │  │
│  │  │  get_server_status_url()         │ │  │
│  │  │  set_proxy_target()              │ │  │
│  │  │  stop_server_status_proxy()      │ │  │
│  │  │  open_server_status_window()     │ │  │
│  │  └─────────────────────────────────┘ │  │
│  │  ┌─ 系统概览 / 环境摘要 ──────────┐  │  │
│  │  │  get_system_overview()          │ │  │
│  │  │  → 复用 Java / 内存 / Mod /     │ │  │
│  │  │    存档 / 截图统计逻辑          │ │  │
│  │  └─────────────────────────────────┘ │  │
│  │  ┌─ Crash Log 分析器 ─────────────┐  │  │
│  │  │  list_crash_logs()               │ │  │
│  │  │  load_crash_log()                │ │  │
│  │  │  analyze_crash_log()             │ │  │
│  │  │  build_ai_payload() / send_to_ai│  │  │
│  │  └─────────────────────────────────┘ │  │
│  │  ┌─ Modrinth Mod 下载中心 ────────┐  │  │
│  │  │  modrinth_search()               │ │  │
│  │  │  modrinth_get_project()          │ │  │
│  │  │  modrinth_get_versions()         │ │  │
│  │  │  modrinth_download_mod()         │ │  │
│  │  └─────────────────────────────────┘ │  │
│  │  ┌─ 设置与工具 ───────────────────┐  │  │
│  │  │  get/save_launcher_settings()    │ │  │
│  │  │  enter/exit_fullscreen()         │ │  │
│  │  │  open_folder() / open_file()     │ │  │
│  │  └─────────────────────────────────┘ │  │
│  └──────────────────────────────────────┘  │
│  ┌─ 入口 ───────────────────────────────┐  │
│  │  if __name__ == "__main__":            │  │
│  │      创建 Api 实例 → pywebview 窗口   │  │
│  └──────────────────────────────────────┘  │
└─────────────────────────────────────────────┘

┌─ TCYNBTeditor.py (独立模块) ──────────────┐
│                                             │
│  ┌─ NbtIO 类 ──────────────────────────┐   │
│  │  纯 Python 标准库 NBT 二进制解析器     │   │
│  │  read(path) → JSON dict             │   │
│  │  write(path, dict) → gzip NBT       │   │
│  │  read_mca(path) → chunk 列表        │   │
│  │  read_mca_chunk(path,x,z) → dict   │   │
│  │  nbt_to_json(dict) → JSON string   │   │
│  │  json_to_nbt(json) → dict          │   │
│  │  支持全部 13 种标签类型                │   │
│  │  Long 值序列化为字符串 (JS 精度安全)   │   │
│  └─────────────────────────────────────┘   │
│  ┌─ NbtEditorApi 类 ──────────────────┐    │
│  │  pywebview js_api 暴露给前端        │    │
│  │  nbt_open_file(path) → JSON        │    │
│  │  nbt_save_file(path, json) → OK    │    │
│  │  nbt_save_as() → 另存为对话框       │    │
│  │  nbt_scan_folder(dir, folder) →    │    │
│  │    递归目录树 (含 .dat/.mca 文件)    │    │
│  │  nbt_open_mca_file(path) → chunks  │    │
│  │  nbt_read_mca_chunk(path,x,z)     │    │
│  │  nbt_export_json() / nbt_import_  │    │
│  │    json() → JSON 导出导入           │    │
│  │  nbt_append_log(line) → 追加日志    │    │
│  │  nbt_write_log(lines) → 写入日志    │    │
│  └─────────────────────────────────────┘   │
│  ┌─ open_nbt_editor() ────────────────┐    │
│  │  创建独立 pywebview 窗口            │    │
│  │  加载 TCYNBTeditor.html             │    │
│  │  events.loaded 回调注入数据          │    │
│  └─────────────────────────────────────┘   │
└─────────────────────────────────────────────┘

TCYNBTeditor.html (独立前端)
┌─ VSCode 风格三栏布局 ────────────────────────┐
│ ┌─ 左: 文件树 ───┐┌─ 中: 编辑器 ────────┐┌─ 右: 大纲 ─┐│
│ │ 收藏/最近(固高)││ 搜索栏 + 替换       ││ Outline    ││
│ │ renderFtNode() ││ 工具栏 (折叠/展开/  ││ Compound/  ││
│ │ toggleFtFolder ││   大纲/缩放重置)    ││ List 结构  ││
│ │ openFile()     ││ 编辑操作工具栏      ││ 点击跳转   ││
│ │ 拖拽文件打开   ││   (撤销/重做/剪切/  ││            ││
│ │                ││   复制/粘贴/添加/   ││            ││
│ │                ││   删除/重命名/排序/ ││            ││
│ │                ││   SNBT/另存/帮助)   ││            ││
│ │                ││ 多标签页 (可拖拽排序)││            ││
│ │                ││ 虚拟滚动渲染区      ││            ││
│ │                ││ rebuildFlatRows()   ││            ││
│ │                ││ renderVirtualRows() ││            ││
│ │                ││ 跨父级拖拽移动      ││            ││
│ │                ││   (缩进级别感知)     ││            ││
│ │                ││ 右键上下文菜单      ││            ││
│ │                ││ saveNbtTree()       ││            ││
│ │                ││ Hex 视图 (数组)     ││            ││
│ └────────────────┘└─────────────────────┘└────────────┘│
│ ┌─ 底部: 操作日志面板 ────────────────────────────────┐│
│ │ 实时记录所有编辑操作，按编辑会话分组                   ││
│ │ 取消操作自动标记删除线，日志同步写入磁盘               ││
│ └─────────────────────────────────────────────────────┘│
│ Ctrl+滚轮缩放 (50%-200%) 编辑区+大纲同步               │
│ 帮助弹窗 (快捷键列表 + 功能说明 + 开发者信息)           │
└──────────────────────────────────────────────────────────┘
```

**关键概念**：
- `Api` 类中所有 **公开方法**（不以 `_` 开头的方法）都可以被前端通过 `pywebview.api.方法名()` 直接调用。
- 以 `_` 开头的方法是内部方法，前端无法调用，仅后端内部使用。
- 后端方法的返回值会自动序列化为 JSON 传给前端。

### 前端 (`index.html`)

这是主前端壳文件，大约 9300 行，包含 HTML 结构 + CSS 样式 + 大部分 JavaScript 逻辑。JVM 调优和系统概览的渲染逻辑已拆到 `jvm_advisor.js` / `system_overview.js`，由 `index.html` 统一加载。

```
┌─ <head> ────────────────────────────────────┐
│  CSS 样式 (~1200 行)                         │
│  包含所有页面的样式定义                       │
└──────────────────────────────────────────────┘
┌─ <body> ────────────────────────────────────┐
│  ┌─ 侧边栏 ──────────────────────────────┐ │
│  │  nav-item 按钮 (更新、Mods、Config...) │ │
│  └────────────────────────────────────────┘ │
│  ┌─ 主内容区 ────────────────────────────┐  │
│  │  page-update: 更新页面                 │  │
│  │  page-mods: Mod 管理页面               │  │
│  │  page-config: Config 管理页面          │  │
│  │  page-moddownload: Mod 下载中心         │  │
│  │  page-crashlog: 崩溃日志分析            │  │
│  │  page-savemgr: 存档管理页面              │ │
│  │  page-serverstatus: 服务器状态/内置浏览器│ │
│  │  page-systemoverview: 系统概览页面       │ │
│  │  page-settings: 设置页面               │  │
│  │  page-log: 操作日志页面                │  │
│  │  page-web: 官网内嵌页面                │  │
│  └────────────────────────────────────────┘ │
│  ┌─ 弹窗/模态框 ─────────────────────────┐ │
│  │  restore-preview-modal (还原预览)      │  │
│  │  mod-detail-modal (Mod 详情弹窗)       │  │
│  │  fullscreen-overlay (全屏容器)          │ │
│  └────────────────────────────────────────┘ │
└──────────────────────────────────────────────┘
┌─ <script> ──────────────────────────────────┐
│  全局变量和状态                               │
│  initApp(): 程序初始化入口                    │
│  页面切换: showPage()                        │
│  ┌─ Mod 管理 JS ──────────────────────────┐ │
│  │  loadModsList(), renderModsList()       │ │
│  │  filterMods(), showModsView()           │ │
│  │  toggleBatchMode(), batchSetModEnabled()│ │
│  │  loadModDependencyGraph()               │ │
│  │  renderForceDirectedGraph()             │ │
│  │  renderGridGraph()                      │ │
│  │  openFullscreen(), closeFullscreen()    │ │
│  └─────────────────────────────────────────┘│
│  ┌─ Config 备份 JS ───────────────────────┐ │
│  │  refreshConfigBackupUI()                │ │
│  │  createConfigBackup()                   │ │
│  │  loadRestorePreview()                   │ │
│  │  confirmAndRestoreConfigBackup()        │ │
│  └─────────────────────────────────────────┘│
│  ┌─ 更新系统 JS ──────────────────────────┐ │
│  │  requestUpdatePreview()                 │ │
│  │  confirmUpdatePreview()                 │ │
│  │  cancelUpdatePreview()                  │ │
│  └─────────────────────────────────────────┘│
│  ┌─ 存档管理 JS ────────────────────────┐  │
│  │  loadSaves(), renderSavesList()         │ │
│  │  filterSaves(), openSaveNbt()           │ │
│  │  → pywebview.api.open_nbt_editor_for_  │ │
│  │    save() 打开独立 NBT 编辑器窗口      │  │
│  └─────────────────────────────────────────┘│
│  ┌─ 服务器状态 / 内置浏览器 JS ──────────┐  │
│  │  loadServerStatus()                     │ │
│  │  navigateBuiltinBrowser()               │ │
│  │  updateBrowserUrlBar()                  │ │
│  │  reloadServerStatus()                   │ │
│  │  stopServerStatusProxy()                │ │
│  └─────────────────────────────────────────┘│
│  ┌─ Crash Log 分析器 JS ────────────────┐   │
│  │  loadCrashLogs(), selectCrashFile()     │ │
│  │  renderLocalAnalysis()                  │ │
│  │  prepareAiAnalysis(), confirmSendToAi() │ │
│  └─────────────────────────────────────────┘│
│  ┌─ Modrinth Mod 下载中心 JS ──────────┐   │
│  │  doModrinthSearch()                     │ │
│  │  renderModSearchResults()               │ │
│  │  openModDetail(), showModDetailTab()    │ │
│  │  renderModVersions(), renderModDeps()   │ │
│  │  doModDownload(), onModDownloadProgress│  │
│  │  renderMarkdown(), inlineMarkdown()     │ │
│  └─────────────────────────────────────────┘│
│  ┌─ 设置 / 工具 JS ──────────────────────┐  │
│  │  loadSettings(), saveSettings()         │ │
│  │  粒子系统、主题、背景                    │ │
│  └─────────────────────────────────────────┘│
└──────────────────────────────────────────────┘
```

**关键概念**：
- 前端调用后端方法的格式：`pywebview.api.方法名(参数).then(result => { ... })`
- 所有页面都在同一个 HTML 文件中，通过 `display: none/block` 切换显示。
- 力向图使用 `lib/d3.min.js`（d3.js v7），通过 `<script>` 标签加载。

### 前后端通信示例

**前端调用后端**（最常见的模式）：
```javascript
// 前端 JS：调用后端的 get_mods_metadata() 方法
pywebview.api.get_mods_metadata().then(function(result) {
    if (result.success) {
        renderModsList(result.data);  // 拿到数据后渲染列表
    } else {
        alert('加载失败: ' + result.error);
    }
});
```

**后端定义对应方法**：
```python
# 后端 Python：在 Api 类中定义
def get_mods_metadata(self):
    try:
        mods_list = []  # ... 读取 mods 目录，解析元数据 ...
        return {"success": True, "data": mods_list}
    except Exception as e:
        return {"success": False, "error": str(e)}
```

**后端主动推送给前端**（较少使用）：
```python
# 后端：通过 evaluate_js 调用前端函数
global_window.evaluate_js(f'updateProgress({percent})')
```

---

## 各模块修改指南

### 如果你要修改 Mod 管理功能

**涉及文件**：
- `TCYServer_MCUpdater.py`：`get_mods_metadata()`、`set_mod_enabled()`、`batch_set_mod_enabled()`
- `index.html`：`renderModsList()`、`filterMods()`、`toggleBatchMode()`

**注意事项**：
- Mod 状态通过文件后缀判断：`.jar` = 已启用，`.jar.disabled` = 已禁用。
- 启用/禁用本质上是文件重命名操作。
- `get_mods_metadata()` 会解析 jar 包内部的 `fabric.mod.json`（Fabric）或 `META-INF/mods.toml`（Forge/NeoForge）来获取模组名称、版本、作者等信息。
- 批量操作使用 `batch_set_mod_enabled()`，一次调用处理多个 mod，避免多次 pywebview 桥接开销。

### 如果你要修改依赖管理/图谱可视化

**涉及文件**：
- `TCYServer_MCUpdater.py`：`get_mod_dependency_graph()`、`set_mod_dependency_ignore()`
- `index.html`：`renderForceDirectedGraph()`、`renderGridGraph()`、`renderModDependencyGraph()`
- `lib/d3.min.js`：d3.js 库（一般不需要修改）

**注意事项**：
- 力向图使用 d3-force 物理仿真：`forceSimulation` + `forceLink` + `forceManyBody` + `forceCenter` + `forceCollide`。
- 图数据格式为 `{nodes: [...], edges: [...]}`，节点有 `type`（mod / dependency）和 `state`（ok / missing / missing_ignored）。
- 全屏使用 pywebview 的 OS 级全屏（`pywebview.api.enter_fullscreen()`），不是浏览器的 `requestFullscreen`。
- 忽略数据保存在 `launcher_settings.json` 的 `mod_dep_ignores` 字段中。

### 如果你要修改 Config 备份还原

**涉及文件**：
- `TCYServer_MCUpdater.py`：`list_config_subfolders()`、`create_config_backup()`、`list_config_backups()`、`preview_config_restore()`、`restore_config_backup()`
- `index.html`：`refreshConfigBackupUI()`、`createConfigBackup()`、`loadRestorePreview()`、`confirmAndRestoreConfigBackup()`

**注意事项**：
- 备份存储在 `.config_backups/` 目录下，每个备份是一个独立文件夹，内含 `manifest.json` 元数据。
- 还原操作有双重安全机制：预览确认 + 自动创建 pre-restore 备份。
- 路径安全校验：防止 `..` 路径穿越攻击。

### 如果你要修改更新流程

**涉及文件**：
- `TCYServer_MCUpdater.py`：`preview_update_plan()`、`start_update_sequence_confirmed()`、`_probe_resume_feasibility()`、`_download_with_resume()`
- `index.html`：`requestUpdatePreview()`、`confirmUpdatePreview()`、`cancelUpdatePreview()`

**注意事项**：
- v1.0.5 引入了确认门禁：用户必须先看到摘要再确认，才会开始下载。
- 门禁使用 UUID token + 600 秒 TTL + payload SHA256 校验。
- 断点续传是可选优化，通过 HTTP Range 探测决定是否启用。
- **这是最敏感的模块**——任何改动都必须确保不破坏原子性更新和回滚机制。

### 如果你要修改冲突规则引擎

**涉及文件**：
- `TCYServer_MCUpdater.py`：`_load_conflict_rules()`、`get_conflict_rules()`
- `index.html`：`renderModsList()` 中的冲突规则展示部分
- `conflict_rules.json`：规则定义文件

**注意事项**：
- 规则文件格式见 README.md 中的 [conflict_rules.json 格式说明](README.md#conflict_rulesjson-冲突规则格式-v105-新增)。
- 匹配逻辑：多 mod 规则要求 **所有** 涉及的 mod 都已启用才触发。
- 规则加载必须容错：文件不存在或格式错误时返回空列表，不抛异常。

### 如果你要修改 JVM 调优向导

**涉及文件**：
- `jvm_advisor.py`：JVM 推荐模型、Java 版本建议、内存预算、GC 方案、风险提示、不建议场景
- `jvm_advisor.js`：JVM 页面渲染、子页面导航、参数 diff、改动摘要、复制按钮、人话替换建议
- `TCYServer_MCUpdater.py`：`get_jvm_recommendations()`、`detect_java_versions()`、`get_launcher_jvm_profiles()`、`copy_to_clipboard()`
- `index.html`：JVM 页面容器、全局 `copyText()`、设置项默认值
- `build.py`：`jvm_advisor.js` 打包项
- `HANDOFF.md` / `.planning/ROADMAP.md` / `readme.md`：功能状态与后续计划说明

**注意事项**：
- JVM 调优现在已经是**独立前后端模块**，优先改 `jvm_advisor.py` / `jvm_advisor.js`，不要再把逻辑塞回超长的 `index.html` 或 `TCYServer_MCUpdater.py`。
- 推荐模型已不再只是原版/中型/大型三档，而是要同时考虑 Minecraft 版本、Loader、整合包规模、CPU 档位、X3D、Java 偏好。
- Windows 下 Java 探测命令必须保持隐藏窗口（避免进入 JVM 页面时弹一堆黑框）。
- JVM 参数复制优先走后端系统剪贴板；前端按钮传参必须使用安全编码，避免长参数字符串把 `onclick` 属性冲坏。
- JVM 页面已经改为**子页面结构**（总览 / Java 检测 / 参数对比 / 备选方案 / 专业面板），后续新增内容时优先考虑放进合适的子页面，而不是继续整页往下堆。
- 如果你继续增强推荐能力，先同步更新 `HANDOFF.md`、`readme.md` 和 `.planning/ROADMAP.md`，避免上下文压缩后丢需求。

### 如果你要修改系统概览

**涉及文件**：
- `system_overview.py`：环境快照采集、当前启动器 Java 推断整合、规则建议生成
- `system_overview.js`：页面初始化、刷新流程、状态提示、机器概况 / 客户端概况 / 建议卡片渲染
- `TCYServer_MCUpdater.py`：`get_system_overview()`，以及被复用的 `detect_java_versions()`、`get_system_memory_info()`、`get_mods_metadata()`、`_get_screenshots_dir()`
- `index.html`：`nav-systemoverview`、`page-systemoverview`、`systemoverview-refresh-btn`、`switchTab('systemoverview')`
- `build.py`：`system_overview.js` 打包项
- `HANDOFF.md` / `.planning/phases/19-system-overview/*` / `readme.md`：范围边界和验收状态说明

**当前状态**：
- 已完成低维护版“系统概览”页面
- 首次进入页面会自动拉一次快照，用户可手动刷新
- 页面展示三块内容：机器概况、客户端概况、规则建议
- “客户端当前使用的 Java”只在能从常见启动器配置里可靠判断时显示；判断不稳时只显示说明，不伪造版本信息
- 当前规则建议只覆盖 Java / 内存 / 磁盘这些基础条件；不做网络诊断、实时监控、GPU 遥测、整合包规模适配判断和伪精确数字评分

**注意事项**：
- 保持**一次性快照接口**：前端应继续只调用 `pywebview.api.get_system_overview()`，不要拆成多个并发小接口。
- 保持**best-effort 降级**：某一项采集失败时，用 `"未知"` 或空字段降级，不要让整页报错。
- 继续**复用已有逻辑**：Java、Mod、存档、截图统计都应复用现有页面或 helper，不要再维护第二套扫描逻辑。
- 当前 Java 文案必须保持**保守**：只有在读到常见启动器配置中的 Java 路径，并且能和已检测到的本机 Java 版本稳定匹配时，才显示版本名。
- 建议输出必须保持**定性**（good / ok / tight / critical + 文案），并继续只谈 Java / 内存 / 磁盘这些基础条件；不要引入综合评分、实时曲线、复杂图表或“更适合某类整合包”这类推断。
- 前端逻辑优先改 `system_overview.js`，不要把整页逻辑重新塞回超长的 `index.html` 内联脚本。

### 如果你要修改启动自动更新提示流程

**涉及文件**：
- `TCYServer_MCUpdater.py`：`init_app()`、`check_online_update()`、`check_online_update_manual()`、`_check_update_thread()`
- `index.html`：顶部 `#update-island` DOM、`showUpdateIslandLoading()`、`showUpdateIslandReady()`、`showUpdateIslandIdle()`、`hideUpdateIslandSoon()`、`onUpdateIslandClick()`、`setPendingVersionModal()`、旧更新弹窗相关函数

**当前状态**：
- 启动时自动检测已切到静默模式，优先使用顶部悬浮提示
- 手动“检查更新”按钮也已接入同一提示流程
- 顶部 `#update-island` DOM 已接入，全局页面顶端可见
- 点击灵动岛后会进入现有综合版本信息弹窗流程
- 已清理重复的 `update-island` DOM
- 当前视觉已同步主题色与个性化风格，并已完成 CTA 高亮、宽度平滑伸缩、点击压缩反馈与更顺滑的过渡动画
- 仍需继续验证：更新器更新、客户端更新、两者同时存在、失败重试这几种链路是否完全符合预期

**注意事项**：
- 启动自动检测和手动检测要区分：
  - 启动自动检测：顶部悬浮提示，点击后才进入详情
  - 手动检测：可保留详细结果反馈，但不要破坏顶部提示状态机
- 顶部悬浮提示必须在全局页面顶端可见，不依赖具体 tab
- 更新详情页仍然复用现有的综合版本信息弹窗，不要重复造一套下载界面

### 如果你要修改存档管理

**涉及文件**：
- `TCYServer_MCUpdater.py`：`list_saves()`、`open_nbt_editor_for_save()`、`_parse_level_dat_metadata()`
- `index.html`：`loadSaves()`、`renderSavesList()`、`filterSaves()`、`openSaveNbt()`

**注意事项**：
- 存档列表通过扫描 `saves/` 目录获取（路径为 `versions/{TARGET_VERSION_NAME}/saves/`）。
- `_parse_level_dat_metadata()` 使用 `NbtIO.read()` 解析 `level.dat`，提取 `LevelName`、`GameType`、`RandomSeed`、`LastPlayed` 等字段。
- 点击"编辑 NBT"调用 `open_nbt_editor_for_save(world_folder_name)`，该方法内部调用 `open_nbt_editor(saves_dir, world_folder_name)` 打开独立窗口。
- 存档卡片使用 CSS 变量（`var(--card-bg)`、`var(--border-color)`）以适配主题。

### 如果你要修改存档管理 / NBT 编辑入口

**涉及文件**：
- `index.html`：`nav-savemgr`、`page-savemgr`、`openStandaloneNbtEditor()`、存档页顶部工具区和空状态提示
- `TCYServer_MCUpdater.py`：`open_nbt_editor_for_save()`、`open_nbt_editor_empty()`
- `TCYNBTeditor.py`：`open_nbt_editor()`、`open_nbt_editor_empty()`、`open_nbt_editor_standalone()`
- `TCYNBTeditor.html`：`initExplorer()` 空态初始化、拖放打开文件逻辑

**当前状态**：
- 侧边栏名称已改为“存档管理/NBT编辑”
- 导航顺序已调整：更新日志 / 操作日志 位于个性化上方，个性化位于官网页面上方
- 存档页顶部已提供“单独打开 NBT 编辑器”按钮
- 独立空白 NBT 编辑器入口已新增，打开后会提示“请拖入nbt文件或nbt文件夹，以读取目录或读取文件进行编辑”

**注意事项**：
- 不要破坏原有从存档卡片打开 NBT 编辑器的链路；`open_nbt_editor_for_save()` 仍是主入口之一。
- 空白工作台依赖 `TCYNBTeditor.html` 中 `initExplorer()` 对空参数的兼容处理；如果继续增强，请优先在前端空态逻辑上扩展，而不是把空态重新塞回主程序页面。
- 拖放打开逻辑目前支持 `.dat` / `.dat_old` / `.mca`；如果要支持文件夹拖放，需要继续增强 `TCYNBTeditor.html` 的 `drop` 处理和后端目录扫描入口。

### 如果你要修改 NBT 编辑器（独立模块）

**涉及文件**：
- `TCYNBTeditor.py`：`NbtIO` 类（解析/写入）、`NbtEditorApi` 类（JS API）、`open_nbt_editor()` 函数（窗口创建）
- `TCYNBTeditor.html`：文件树渲染、虚拟滚动 NBT 树、搜索(含上/下导航+替换)、大纲面板、缩放、撤销/重做、剪切/复制/粘贴、右键菜单、标签排序、重命名、SNBT 复制、多标签页、Hex 视图、.mca 区域文件、JSON 导出/导入、拖拽文件打开、跨父级拖拽移动（缩进级别感知）、编辑操作工具栏、帮助弹窗、未保存提示、操作日志面板、编辑会话追踪
- `build.py`：`ADDED_DATA` 和 `--hidden-import` 配置
- `NBTEditor-DevGuide.md`：**NBT 编辑器开发指南**（功能路线图、各功能实现方案、注意事项）
- `NBTEditor-log/`：**运行时生成的操作日志目录**，包含按日期分割的 `.log` 文件

**架构说明**：
- NBT 编辑器是**完全独立的模块**，不依赖主程序的 CSS/JS/Api 类。它有自己的后端（`NbtEditorApi`）和前端（`TCYNBTeditor.html`），在独立 pywebview 窗口中运行。
- 主程序仅通过 `from TCYNBTeditor import NbtIO, open_nbt_editor` 使用两个公开接口。

**开发路线图（对标 NBT Studio）**：

NBT 编辑器正在持续强化，目标是补齐 NBT Studio 的核心功能。完整路线图和实现方案详见 [NBTEditor-DevGuide.md](NBTEditor-DevGuide.md)。

| 批次 | 功能 | 状态 |
|------|------|------|
| 第一批 | 撤销/重做、重命名标签名、搜索上/下导航、剪切/复制/粘贴、右键菜单、标签排序 | 已完成 |
| 第二批 | SNBT 复制、查找替换（Ctrl+H）、另存为（Ctrl+Shift+S）、拖拽排序 | 已完成 |
| 第三批 | 多标签页、数组 hex 视图、.mca 区域文件、JSON 导出/导入、拖拽文件打开 | 已完成 |
| 后续增强 | 编辑操作工具栏、帮助弹窗、跨父级拖拽(缩进级别感知)、未保存提示、操作日志、编辑会话追踪 | 已完成 |

**编辑操作工具栏与帮助弹窗**：
- 编辑模式下，工具栏显示实体按钮：撤销、重做、剪切、复制、粘贴、添加、删除、重命名、排序、SNBT 复制、另存为。按钮使用 `flex-wrap:wrap` 自动换行，避免溢出到大纲面板后方。
- 帮助按钮（❓）弹出模态框，列出所有快捷键（Ctrl+Z/Y/X/C/V/S/Shift+S/H/F/Del）及功能说明，底部显示开发者信息（GitHub @KanameMadoka520）。

**跨父级拖拽与缩进级别感知**：
- 拖拽系统支持三种放置模式：目标行上方 25% 区域 = 放在目标前、中间 50% = 放入容器内、下方 25% = 放在目标后。
- **X 轴缩进级别逃逸**：鼠标相对于目标行缩进位置的水平偏移量决定逃逸层级。每向左偏移 20px（`ROW_INDENT=20`）逃逸一级父容器。例如，将一个节点从 3 层深的 Compound 往左拖 40px，会逃逸 2 级，目标变为祖父容器的同级位置。
- 核心函数 `_calcDropInfo(e, pathStr)` 返回 `{targetPath, mode, escapeLevels, isContainer}`，拖拽指示条实时显示当前放置位置和深度。
- 标签页顺序也支持拖拽排列（标签栏横向拖拽）。

**未保存修改提示**：
- 关闭标签页时，如果当前文件有未保存的修改（通过撤销栈 `undoStack.length > 0` 判断），弹出 `confirm()` 提示。
- 点"确定"关闭（放弃修改），同时结束编辑会话并标记为 `cancelled`；点"取消"则不关闭。

**操作日志系统**：
- 底部面板实时显示所有编辑操作：添加、删除、重命名、编辑值、移动、粘贴、排序等。
- 每条日志包含 `{time, type, msg, file, sid, cancelled}` 字段。
- 日志通过 `nbt_append_log(line)` 实时写入 `NBTEditor-log/nbt_session_YYYY-MM-DD.log` 文件。
- 面板可折叠/展开，日志条目自动滚动到最新。

**编辑会话追踪机制**：
- 每个文件的编辑有独立会话（session），用 `_editSessions[filePath]` 存储，包含唯一 `sid`、开始时间、操作计数。
- 会话有三种结束状态：
  - **SAVED**：用户保存文件 → 会话正常结束
  - **CANCELLED**：用户关闭标签页时选择不保存 → 该会话所有操作日志被标记 `cancelled=true`，显示删除线样式
  - **INTERRUPTED**：程序意外退出 / 用户关闭窗口 → `beforeunload` 事件中批量写入未结束会话的中断日志
- 取消操作时，所有属于该 `sid` 的日志条目会被追加 `CANCEL_BATCH` 标记到磁盘日志，前端以 `opacity:0.45 + line-through` 样式呈现。
- 多文件并发编辑时，每个文件独立追踪，互不干扰。

**NbtIO 二进制解析器技术细节**：
- NBT 是 Minecraft Java 版使用的二进制序列化格式，大端字节序（big-endian），通常 gzip 压缩。
- `NbtIO.read(path)`：先尝试 gzip 解压（失败则视为未压缩），然后按 NBT 规范递归解析。返回 JSON 可序列化的 Python 字典。
- `NbtIO.write(path, dict)`：将 Python 字典按 NBT 规范序列化为二进制，然后 gzip 压缩写入磁盘。
- **全部 13 种标签类型**：End(0), Byte(1), Short(2), Int(3), Long(4), Float(5), Double(6), ByteArray(7), String(8), List(9), Compound(10), IntArray(11), LongArray(12)。
- **Long 值精度安全**：NBT Long 是 64 位有符号整数（范围 ±9.2×10¹⁸），JavaScript Number 只有 53 位精度（`Number.MAX_SAFE_INTEGER` = 2⁵³-1 ≈ 9×10¹⁵）。为避免溢出，`NbtIO` 在读取时将 Long 值转为 Python 字符串（`str(val)`），前端展示/编辑时保持字符串格式，写入时再 `int(v)` 转回整数。Minecraft 的世界种子（RandomSeed）就是 Long 类型，如果不做此处理会导致种子被截断失真。
- 使用 `struct` 模块做二进制打包/解包，格式字符串用 `>` 前缀表示大端：`>b`=Byte, `>h`=Short, `>i`=Int, `>q`=Long, `>f`=Float, `>d`=Double。
- **Anvil .mca 区域文件**：`NbtIO.read_mca(path)` 解析 8KB 头部（4096 字节位置表 + 4096 字节时间戳表），返回非空 chunk 列表 `[{x, z, offset, size, timestamp}]`。`NbtIO.read_mca_chunk(path, x, z)` 读取指定 chunk 的 NBT 数据，支持 gzip/zlib/未压缩三种压缩类型。
- **JSON 双向转换**：`NbtIO.nbt_to_json(dict)` 将 NBT 字典转为标准 JSON（保留类型标注），`NbtIO.json_to_nbt(json)` 反向转换。用于 JSON 导出/导入功能。

**前端懒渲染架构技术细节**：
- 状态变量 `_expanded` 字典记录哪些路径被展开。路径用 `.` 分隔的索引字符串表示（如 `"0.3.1"` 表示根节点的第4个子节点的第2个子节点）。
- `renderNode(node, path, depth)` 是核心渲染函数：
  - 对容器节点（Compound/List），如果 `_expanded[path]` 为 falsy，只渲染一行摘要（如 `Compound [42 tags]`），**不递归子节点**。
  - 用户点击箭头 → `toggleExpand(pk)` → `_expanded[pk] = true` → `renderTree()` 重渲染 → 此时该节点的子节点才被递归渲染。
  - 一个包含 2000 个节点的 level.dat，初始只渲染根 Compound 的直接子节点（约 15 行），而非全部 2000 行。
- 搜索功能 `searchTree()` 递归遍历整棵树，匹配的节点标记到 `_searchMatches` 字典，并调用 `expandParents(path)` 自动展开其所有祖先节点。渲染时匹配节点添加 `.highlight` CSS 类（黄色左边框 + 浅黄背景）。

**文件树浏览器技术细节**：
- 后端 `nbt_scan_folder()` 递归扫描存档目录，构建 `{type, name, path, children}` 树结构，智能过滤：仅保留包含 `.dat`/`.dat_old`/`.mca` 文件的文件夹。
- **拖拽文件打开**：支持从系统文件管理器拖拽 `.dat`/`.dat_old`/`.mca` 文件到编辑器窗口直接打开。
- 前端 `renderFtNode()` 递归渲染目录树，文件夹可展开/折叠（状态存储在 `_ftExpanded` 字典），点击文件调用 `openFile()` 加载 NBT 数据。
- **路径转义**：Windows 路径包含反斜杠（如 `C:\Users\saves\world`），在 HTML onclick 属性中需要双重转义（`\\` → `\\\\`），否则 JS 解析时反斜杠会被吞掉导致路径错误。这是跨平台桌面应用常见的坑。

**pywebview 独立窗口通信机制**：
- `open_nbt_editor()` 创建新 pywebview 窗口时传入 `js_api=NbtEditorApi()` 实例。该实例的公开方法可被新窗口的 JS 通过 `pywebview.api.xxx()` 调用，与主窗口的 `Api` 类完全独立。
- 窗口加载完成后（`events.loaded` 事件），后端通过 `nbt_win.evaluate_js()` 注入初始化调用 `initExplorer(savesDir, worldFolder)`，触发前端加载文件树。
- 延迟 0.3 秒注入是因为 pywebview 的 `loaded` 事件在 DOM ready 时触发，但 JS 变量和函数定义可能尚未完成。

**修改时注意**：
- 如果修改 `NbtIO` 的读写逻辑，必须确保读写**往返一致**（read → write → read 结果相同），否则会损坏存档。
- 如果新增 JS API 方法到 `NbtEditorApi`，方法名不能以 `_` 开头（pywebview 只暴露公开方法）。
- 修改 `TCYNBTeditor.html` 后无需重新打包即可测试（源码模式直接运行），但发布前必须重新打包（`python build.py`）。
- **inline onclick 中传递数组的陷阱**：路径参数（如 `[0,3,1]`）在 HTML inline `onclick` 属性中通过字符串拼接时，JS 数组会丢失方括号（`'func('+[0,3]+')'` 变成 `'func(0,3)'`，即两个参数而非一个数组参数）。**必须**使用 `JSON.stringify(path)` 序列化后拼接，并在接收函数中兼容 `Array.isArray(x) ? x : JSON.parse(x)` 两种输入。
- **箭头点击事件冒泡**：展开/折叠箭头的 `onclick` 必须包含 `event.stopPropagation()`，否则事件会冒泡到父行的 `selectNode()`，导致编辑区内容消失。

### 如果你要修改服务器状态 / 内置浏览器

**涉及文件**：
- `TCYServer_MCUpdater.py`：`get_server_status_url()`、`set_proxy_target()`、`stop_server_status_proxy()`、`open_server_status_window()`
- `index.html`：`loadServerStatus()`、`navigateBuiltinBrowser()`、`updateBrowserUrlBar()`、`reloadServerStatus()`、`stopServerStatusProxy()`、`_startProxyPathPoll()`、`_stopProxyPathPoll()`

**注意事项**：
- 反向代理使用 `ThreadingTCPServer` + daemon 线程，监听 `127.0.0.1:0`（随机端口），代理类 `_ProxyHandler` 定义在 `get_server_status_url()` 方法内部。
- 代理会剥除 `content-security-policy`、`x-frame-options`、`content-security-policy-report-only` 三个响应头。
- **HTML 与非 HTML 请求区别处理**：代理通过检查请求的 `Accept` 头判断是否为 HTML 请求。HTML 请求不发送 `Accept-Encoding`（获取未压缩 HTML 以便注入脚本）；非 HTML 资源（CSS/JS/图片）透传 `Accept-Encoding` 保持 gzip 压缩加速。
- **链接拦截脚本注入**：代理在 HTML 响应的 `</head>` 前注入 `_NAV_SCRIPT`，该脚本拦截页面内指向外部域名的 `<a>` 链接点击，通过 `postMessage({type:'proxy-navigate', url})` 通知父窗口切换反代目标，避免 iframe 直接跳转到外部网站脱离代理。
- **反代目标动态切换**：`set_proxy_target(url)` 修改类变量 `Api._status_proxy_target`，`_ProxyHandler` 每次请求时读取该变量，实现运行时切换目标无需重启代理。
- **地址栏显示真实目标网址**：前端地址栏显示 `https://example.com/path`（反代正在转发的目标），而非 `http://127.0.0.1:port/path`。用户输入新网址时调用 `set_proxy_target()` 切换后端目标后重新加载 iframe。
- **路径轮询**：`_startProxyPathPoll()` 每 800ms 读取 iframe 的 `contentWindow.location.pathname`（同源可读），拼接反代目标 origin 得到真实 URL 同步到地址栏。轮询会跳过 `about:blank` 中间态防止 URL 污染。
- `open_server_status_window()` 是备用方案，使用 `pywebview.create_window()` 打开独立窗口，不依赖反向代理，不受地址栏/轮询影响。
- 修改代理逻辑时注意：不要移除 `daemon=True`，否则程序关闭后代理线程会残留。

### 如果你要修改 Crash Log 分析器

**涉及文件**：
- `TCYServer_MCUpdater.py`：`list_crash_logs()`、`load_crash_log()`、`analyze_crash_log()`、`build_ai_payload()`、`send_to_ai()`
- `index.html`：`loadCrashLogs()`、`renderCrashFileList()`、`selectCrashFile()`、`renderLocalAnalysis()`、`prepareAiAnalysis()`、`confirmSendToAi()`、`onAiAnalysisResult()`

**注意事项**：
- 本地分析使用正则提取堆栈帧中的 mod 包名，交叉对比已安装 mod 的 `id`（来自 `fabric.mod.json`/`mods.toml`）。
- AI 分析使用 OpenAI 兼容的 Chat Completions API 格式（`/v1/chat/completions`）。
- AI 设置保存在 `launcher_settings.json` 的 `ai_api_url`、`ai_api_key`、`ai_model` 字段中。
- `build_ai_payload()` 负责预处理日志（提取关键段落、已安装 mod 列表作为上下文），返回完整的 messages 数组。
- 预处理必须透明：前端展示"即将发送的内容"预览框，用户可审阅/编辑后才确认发送。

### 如果你要修改 Mod 下载中心 (Modrinth)

**涉及文件**：
- `TCYServer_MCUpdater.py`：`get_mods_dir_path()`、`modrinth_search()`、`modrinth_get_project()`、`modrinth_get_projects_batch()`、`modrinth_get_versions()`、`modrinth_download_mod()`、`_get_installed_mod_filenames()`
- `index.html`：`initModDownloadPage()`、`doModrinthSearch()`、`renderModSearchResults()`、`openModDetail()`、`showModDetailTab()`、`renderModVersions()`、`renderModDeps()`、`doModDownload()`、`onModDownloadProgress()`、`renderMarkdown()`、`inlineMarkdown()`

**注意事项**：
- Modrinth API v2 公开免费，无需 API Key，但必须设置 `User-Agent` 头（当前使用 `TCYClientUpdater/1.0.7 (tcymc.space)`）。
- 搜索使用 [facets 二维数组](https://docs.modrinth.com/api/operations/searchprojects/) 进行过滤，loader 通过 `categories:{loader}` facet（不是 `loaders:`）。
- `modrinth_search()` 支持 `sort_index` 参数（`relevance`/`downloads`/`follows`/`newest`/`updated`）。
- `modrinth_get_versions()` 返回每个版本的 `dependencies` 数组（含 `project_id`、`dependency_type`）和 `installed` 标志。
- `modrinth_get_projects_batch()` 调用 `GET /v2/projects?ids=[...]` 批量获取依赖项目信息。
- `modrinth_download_mod()` 在 daemon 线程中流式下载，通过 `global_window.evaluate_js()` 推送 `onModDownloadProgress` 进度事件。
- 前端内置轻量 Markdown 渲染器（`renderMarkdown()` + `inlineMarkdown()`），支持标题、粗体/斜体、图片（`![](url)`）、链接、列表、代码块、引用。用于渲染 Modrinth mod 的 `body` 描述。
- MC 版本下拉默认选中 `1.20.1`（当前客户端版本），分类下拉包含 Modrinth 官方 17 个 mod 分类。
- 详情弹窗有三个标签页（简介/版本列表/依赖），依赖标签页点击可递归打开其他 mod 的详情。

### 如果你要修改 UI 样式

**涉及文件**：
- `index.html`：`<style>` 标签内的 CSS（约前 1200 行）

**注意事项**：
- 所有样式都内联在 `index.html` 的 `<style>` 标签中。
- 主题色系统使用 CSS 变量和 JavaScript 动态修改。
- 粒子系统使用 `<canvas>` 元素，代码在 JS 部分。
- 毛玻璃效果使用 `backdrop-filter: blur()`。

---

## 提交规范

### Commit Message 格式

```
<type>: <简短描述>

<可选的详细说明>
```

**type 取值**：

| type | 说明 | 示例 |
|------|------|------|
| `feat` | 新功能 | `feat: 添加下载限速功能` |
| `fix` | 修复 bug | `fix: 修复 Mod 列表加载崩溃` |
| `refactor` | 重构（不改变功能） | `refactor: 提取镜像测速为独立方法` |
| `style` | UI/样式修改 | `style: 调整 Mod 卡片圆角大小` |
| `docs` | 文档修改 | `docs: 更新 README 部署指南` |
| `chore` | 构建/工具修改 | `chore: 更新 build.py 打包配置` |

### 提交建议

- **小步提交**：每个提交只做一件事。不要把"修复 bug + 新功能 + 改样式"混在一个提交里。
- **不混入无关重构**：如果你在修 bug 时发现了可以优化的代码，请分开提交。
- **测试再提交**：确保程序能正常启动，你改的功能能正常工作。

### PR 描述模板

提交 Pull Request 时，请在描述中包含以下内容：

```markdown
## 变更目标
简要说明你做了什么、为什么做。

## 影响模块
列出受影响的模块：更新系统 / Mod 管理 / Config 备份 / 依赖管理 / 设置 / UI / 日志 / 其他

## 手工验证步骤
1. 启动程序
2. 进入 xxx 页面
3. 点击 xxx 按钮
4. 预期看到 xxx
```

---

## 版本发布约定

发布新版本时，以下 **三处版本号必须同步更新**：

| 位置 | 文件 | 字段 / 关键词 |
|------|------|---------------|
| 启动器内部版本号 | `TCYServer_MCUpdater.py` | `LAUNCHER_INTERNAL_VERSION = "x.x.x"` |
| 打包产物名 | `build.py` | `EXE_NAME = "TCYClientUpdater-x.x.x"` |
| 文档版本 | `README.md` | 版本徽章 `version-x.x.x-blue` + Changelog 章节 |

补充说明：

- 主仓库里通常**不直接保存**线上使用的 `latest.json` / `Updater-latest.json` 成品。
- 这两个文件应通过 `VersionJsonEditor/` 或外部发布流程生成并上传，而不是手工在主仓库里随便塞一个本地副本。
- `build.py` 现在会在构建前后自动清理 `dist/` 中的旧 EXE 和运行时残留，避免把本地日志或设置文件一起发出去。

### 发布检查清单

- [ ] 三处版本号已同步
- [ ] `README.md` 的 Changelog 已添加本版本的更新说明
- [ ] `python -m py_compile TCYServer_MCUpdater.py` 通过
- [ ] `python -m py_compile TCYNBTeditor.py` 通过
- [ ] 程序能正常启动和使用
- [ ] `python build.py` 打包成功，`dist/` 下生成了 EXE
- [ ] `dist/` 中没有误带 `launcher_debug.log`、`launcher_settings.json`、`CRASH_IMPORT.txt` 这类运行时残留
- [ ] EXE 能独立运行（在没有 Python 环境的电脑上也能启动）

---

## 常见问题

### Q: 我只想改一个小 bug，需要了解整个项目吗？

不需要。只要你知道 bug 在哪个文件、哪个函数，直接定位修改即可。本文档的 [各模块修改指南](#各模块修改指南) 可以帮你快速找到相关代码。

### Q: 前端代码为什么全部写在一个 index.html 里？

这是项目的历史设计决策。因为 pywebview 加载单文件最简单，且打包时只需把一个文件打入 EXE。虽然文件很大，但通过搜索函数名可以快速定位。注意：从 v1.0.7 开始，NBT 编辑器的前端代码已分离到独立的 `TCYNBTeditor.html`，因为它运行在独立窗口中，与主程序前端没有 CSS/JS 依赖关系。

### Q: 为什么 NBT 编辑器要从主程序分离出来？

两个原因：(1) NBT 编辑器运行在独立 pywebview 窗口中，有自己的 `js_api` 实例（`NbtEditorApi`），与主窗口的 `Api` 类完全独立，代码分离更清晰。(2) NBT 文件可能非常大（数千节点），如果内嵌在主窗口中渲染会阻塞主程序 UI，独立窗口 + 懒渲染彻底解决了性能问题。

### Q: 我怎么知道前端某个按钮调用了后端哪个方法？

在 `index.html` 中搜索按钮的 `onclick` 属性，找到对应的 JS 函数，然后在函数体内搜索 `pywebview.api.` 就能看到调用了哪个后端方法。

### Q: d3.js 为什么不用 CDN 而是本地文件？

因为这是一个桌面应用，使用 `file:///` 协议加载页面，无法访问在线 CDN。d3.js 必须打包在本地 `lib/d3.min.js`。

### Q: 我改了后端代码，前端怎么没反应？

pywebview 有缓存。尝试关闭程序重新启动。如果还是不行，检查你的后端方法名是否正确，返回值格式是否和前端期望的一致。

### Q: 我想添加一个新的后端 API 方法，怎么做？

1. 在 `TCYServer_MCUpdater.py` 的 `Api` 类中添加一个新的公开方法（不以 `_` 开头）：
   ```python
   def my_new_method(self, param1, param2):
       try:
           # 你的逻辑
           return {"success": True, "data": result}
       except Exception as e:
           return {"success": False, "error": str(e)}
   ```
2. 在 `index.html` 中调用：
   ```javascript
   pywebview.api.my_new_method(arg1, arg2).then(function(result) {
       if (result.success) {
           // 处理成功
       }
   });
   ```
3. 重启程序即可生效。

### Q: 任何改动都必须附带手工验证结果吗？

影响 **启动链路**（`pywebviewready -> mark_ready -> initApp`）的改动必须附带手工验证结果。其他改动强烈建议验证，但不强制。

---

## v1.0.7 开发内容（已完成 — 客户端管家）

- **Phase 13**: 服务器状态 / 内置浏览器 — 本地反向代理嵌入 server.tcymc.space、地址栏导航、独立窗口备用方案、安全提示 ✓
- **Phase 14**: Crash Log 智能分析器 — 本地规则匹配（堆栈提取/mod 交叉对比/模式识别）+ AI 辅助（用户自配 API，预处理透明可审）✓
- **Phase 15**: Mod 下载中心 — Modrinth API v2 搜索/过滤/详情/Markdown 渲染/依赖展示/一键下载 ✓
- **Phase 16**: 存档管理与 NBT 编辑器 — 存档列表（level.dat 元数据解析）+ 独立窗口 NBT 编辑器（VSCode 三栏布局、虚拟滚动、搜索、大纲面板、缩放、全类型编辑）+ 代码分离（TCYNBTeditor.py/html）✓ → 持续强化中（对标 NBT Studio，详见 [NBTEditor-DevGuide.md](NBTEditor-DevGuide.md)）
- **Phase 17**: JVM 调优向导 ✓
  - 已完成：独立前后端模块（`jvm_advisor.py` / `jvm_advisor.js`）、多维推荐模型、主方案/备选方案、参数解释、风险提示、不建议场景、当前启动器参数 diff、改动摘要、一键复制修正版参数、JVM 子页面导航、场景模板、当前 Java 匹配提示、启动器应用指南、建议等级、客户端/服务端区分说明、子页面切换自动滚动到顶部
  - 当前边界：不直接改写 HMCL / PCL 配置，而是输出修正版参数并引导用户手动粘贴
  - 可继续优化：启动器具体粘贴路径说明、建议等级与备选方案联动细化、替换建议增强、客户端/服务端误用警告、可选的只看变化项筛选
- **Phase 18**: 截图画廊 ✓
  - 已完成：主程序侧边栏入口、截图页工具栏、截图目录扫描、元数据读取、稳定顺序 `grid` 布局、缩略图懒加载、底部哨兵 + 滚动兜底续载、灯箱预览、排序/搜索、多选导出、收藏夹 / 漫游模式、灯箱“用系统默认应用打开 / 打开图片所在目录 / 导出（复制）此图”、收藏夹“导出整个收藏夹”、缩略图磁盘缓存（`thumbnail_cache/screenshots/thumbs`）、预览缓存（`thumbnail_cache/screenshots/previews`）、后台预热、有限并行生成、运行状态区与手工验收模式
  - 近期修复：旧图视觉插队、滚动到底不续载、“进入多选”按钮失效；“打开图片所在目录”现为直接打开截图真实父目录
  - 默认路径：缩略图使用 WebView2 前端生成并缓存，不再要求玩家额外安装 Pillow
  - 可继续优化：大量截图性能验收、灯箱交互细节与状态文案微调、必要时增加缓存容量上限 / 更细粒度预热策略
- **Phase 19**: 系统概览 ✓（2026-03-14 后续实现，2026-03-15 已完成手工验收）
  - 已完成：独立后端模块 `system_overview.py`、独立前端模块 `system_overview.js`、`Api.get_system_overview()`、侧边栏入口、页面容器、刷新按钮、打包接入
  - 当前行为：客户端当前使用的 Java 仅在能从常见启动器配置里可靠判断时显示；判断不稳时只显示说明
  - 当前边界：只做只读环境快照 + 规则建议，且建议只覆盖 Java / 内存 / 磁盘这些基础条件；不做网络诊断、实时监控、GPU 遥测、整合包规模适配判断或数字评分
  - 可继续优化：Windows 实机验收、文案微调、字段缺失时的降级展示细节

## v1.0.5 开发内容

- **Phase 7**: Config 备份/还原 — 可选范围备份、还原前预览、还原前自动安全备份、搜索过滤
- **Phase 8**: 更新前摘要预览与确认门禁 — token 校验、600s TTL、取消无副作用
- **Phase 9**: 断点续传可行性评估与条件启用 — HTTP Range 探测、条件回退、活动日志
- **Phase 10**: Mod 依赖管理与可视化 — 四视图（列表/图谱/力向图/网格图）、d3.js 力向图、OS 级全屏、搜索过滤、忽略工作流
- **Phase 11**: Mod 批量启用/禁用 — 多选模式、全选/反选、批量操作、结果汇总、状态回读
- **Phase 12**: Mod 冲突规则提示引擎 — 本地 JSON 规则、mod ID 匹配、严重级别颜色标签

---

感谢你的贡献！如有任何疑问，欢迎在 GitHub Issues 中提问。
