# TCY Client Updater — 技术开发交接文档

> 本文档面向接手开发的新人，目标是让你即使没有参与过之前的开发，也能快速理解项目、找到代码、继续做未完成的功能。

## 先看这里（3 分钟接手版）

如果你刚接手这个项目，建议按下面顺序读：

1. 先看本文第 4 节到第 8 节，建立代码结构、已完成功能和当前边界的整体认识。
2. 再看 [CONTRIBUTING.md](CONTRIBUTING.md) 里的“各模块修改指南”和“版本发布约定”，明确怎么改、怎么验、怎么发。
3. 如果你要接着做某个具体 Phase，就去 `.planning/phases/对应目录/` 看 `*-STATUS.md` 和 `*-PLAN.md`，不要只凭 `readme.md` 继续开发。

**当前稳定基线（2026-03-15）**：

- `v1.0.6` 主体功能（Phase 13–18）已完成。
- Phase 19“系统概览”已完成并通过一轮手工验收。
- 当前没有已知的高优先级阻塞问题；如果后续继续开发，优先沿着现有模块边界扩展，不要把新逻辑重新堆回超长内联脚本。
- 发布相关的 `latest.json` / `Updater-latest.json` 不在这个主仓库里维护；它们走外部发布流程或 `VersionJsonEditor/` 工具链。

---

## 目录

1. [项目是什么](#1-项目是什么)
2. [技术栈一句话总结](#2-技术栈一句话总结)
3. [怎么跑起来](#3-怎么跑起来)
4. [文件在哪里，每个文件干什么](#4-文件在哪里每个文件干什么)
5. [代码是怎么工作的（架构原理）](#5-代码是怎么工作的架构原理)
6. [前端和后端怎么通信](#6-前端和后端怎么通信)
7. [已经做完了什么](#7-已经做完了什么)
8. [v1.0.6 收尾、验收与后续优化](#8-v106-收尾验收与后续优化如果你要继续)
9. [怎么加一个新功能（手把手教程）](#9-怎么加一个新功能手把手教程)
10. [NBT 编辑器模块详解](#10-nbt-编辑器模块详解)
11. [踩过的坑和注意事项](#11-踩过的坑和注意事项)
12. [相关文档索引](#12-相关文档索引)

---

## 1. 项目是什么

这是一个 **Minecraft Java 版客户端管理工具**，给糖醋鱼神人服务器的玩家用的。

最初只是一个"一键更新客户端"的小工具，后来不断扩展，现在已经变成一个功能丰富的"客户端管家"，包括：

- 一键更新客户端（支持增量更新、断点续传、回滚）
- Mod 管理（启用/禁用/搜索/下载/依赖检测/冲突提示）
- Config 配置备份还原
- 存档管理 + NBT 编辑器（可以像 NBT Studio 那样编辑 Minecraft 的 NBT 数据文件）
- Crash Log 崩溃日志分析（本地规则 + AI 辅助）
- 服务器状态查看（内嵌网页）
- JVM 调优向导（已完成，当前定位为推荐/复制参数，不直接改写 HMCL / PCL）
- 截图画廊（已完成，已补充灯箱快捷操作、收藏夹整夹导出，并修复顺序稳定性 / 自动续载 / 多选入口问题）

**开发者**：GitHub [@KanameMadoka520](https://github.com/KanameMadoka520)

---

## 2. 技术栈一句话总结

| 层 | 技术 | 说明 |
|---|---|---|
| 后端 | Python 3.8+ | 单文件脚本，处理文件操作、系统调用、网络请求 |
| 前端 | HTML + CSS + JS | 单文件页面，写界面和交互逻辑 |
| 桥接 | pywebview | Python 库，创建一个桌面窗口，里面跑网页，前后端可以互相调用 |
| 打包 | PyInstaller | 把 Python 脚本打包成单个 .exe，用户不需要装 Python |

**关键理解**：这不是一个网站，也不是一个传统的桌面程序。它是一个 **Python 程序打开一个窗口，窗口里跑 HTML 页面**。前端用 `pywebview.api.xxx()` 调用后端 Python 方法，后端用 `window.evaluate_js('xxx()')` 调用前端 JS 函数。

---

## 3. 怎么跑起来

### 安装依赖

```bash
# 确保你有 Python 3.8+
python --version

# 安装两个包
pip install pywebview pyinstaller
```

### 运行程序

```bash
# 主程序
python TCYServer_MCUpdater.py

# 如果不在正确的游戏目录下，会弹出目录校验警告，点"强制跳过"就行
```

### 单独运行 NBT 编辑器（开发调试时常用）

```bash
python TCYNBTeditor.py
```

### 打包成 exe

```bash
python build.py
# 产物在 dist/ 目录
```

---

## 4. 文件在哪里，每个文件干什么

```
TCY-Client-Updater/
│
├── TCYServer_MCUpdater.py    # 【核心】主程序后端桥接 (~5500 行)
│                              #   大部分 API 与主流程都在这里
│                              #   通过 Api 类把前端和独立模块串起来
│
├── index.html                # 【核心】主程序前端壳 (~9300 行)
│                              #   绝大多数页面容器、样式和全局 JS 都在这里
│                              #   部分新功能已改为外置 JS 模块接入
│
├── jvm_advisor.py            # JVM 调优向导后端模块
├── jvm_advisor.js            # JVM 调优向导前端模块
├── system_overview.py        # 系统概览后端模块（环境快照 + 规则建议）
├── system_overview.js        # 系统概览前端模块（采样 / 刷新 / 渲染）
│
├── TCYNBTeditor.py           # NBT 编辑器后端 (~746 行)
│                              #   独立于主程序，有自己的 API 类
│                              #   包含 NbtIO（NBT 二进制解析器）和 NbtEditorApi
│
├── TCYNBTeditor.html         # NBT 编辑器前端 (~2346 行)
│                              #   独立页面，VSCode 风格的三栏布局
│
├── build.py                  # 打包脚本，把所有文件打包成一个 exe
├── lib/d3.min.js             # d3.js 图表库（Mod 依赖图谱用的）
├── conflict_rules.json       # Mod 冲突规则配置
├── icon.ico                  # 程序图标
├── background.png            # 默认背景图
│
├── NBTEditor-log/            # 运行时自动生成的 NBT 编辑器操作日志
│   └── nbt_session_2026-03-05.log
│
├── readme.md                 # 项目说明文档（给用户看的）
├── CONTRIBUTING.md           # 贡献指南（给开发者看的，超详细）
├── NBTEditor-DevGuide.md     # NBT 编辑器开发指南（功能路线图 + 实现方案）
├── HANDOFF.md                # 本文件
├── LICENSE                   # CC BY-NC-SA 4.0 开源协议
│
└── VersionJsonEditor/        # TCY Publish Manager（更新发布管理器，独立工具）
```

### 文件关系图

```
用户双击 exe
    ↓
TCYServer_MCUpdater.py 启动
    ↓
创建 pywebview 窗口，加载 index.html
    ↓
index.html 渲染界面，用户操作
    ↓                           ↓
pywebview.api.xxx()         用户点"编辑 NBT"
调用后端方法                     ↓
                         TCYNBTeditor.py 启动
                         新窗口加载 TCYNBTeditor.html
```

---

## 5. 代码是怎么工作的（架构原理）

### 主程序后端 (`TCYServer_MCUpdater.py`)

整个后端就是一个巨大的 `Api` 类。这个类里的每一个**不以下划线开头**的方法，都可以被前端 JS 直接调用。

不过从 v1.0.6 后期开始，一些新功能已经逐步拆成独立模块，例如 `jvm_advisor.py` 和 `system_overview.py`。前端仍然统一通过 `Api` 调用它们，主程序负责桥接、目录路径和共享状态。

```python
class Api:
    def get_mods_metadata(self):      # 前端可以调用：pywebview.api.get_mods_metadata()
        ...

    def set_mod_enabled(self, ...):   # 前端可以调用：pywebview.api.set_mod_enabled(...)
        ...

    def _internal_helper(self):       # 以 _ 开头 → 内部方法，前端不能调用
        ...
```

方法的返回值格式统一为 `{"success": True/False, "data": ..., "error": ...}`。

### 主程序前端 (`index.html`)

- 所有页面都在同一个 HTML 文件里，通过 `display: none/block` 切换显示哪个页面
- CSS 样式在 `<style>` 标签里（约前 1200 行）
- JS 逻辑在 `<script>` 标签里（约后 4000 行）
- 用 `showPage('page-mods')` 切换到 Mod 管理页面，`showPage('page-config')` 切换到 Config 页面，以此类推
- 新功能也开始拆成外置前端模块，例如 `jvm_advisor.js` 与 `system_overview.js`，由 `index.html` 通过 `<script src="...">` 加载

### NBT 编辑器（独立模块）

NBT 编辑器是完全独立的——它有自己的后端（`TCYNBTeditor.py`）和前端（`TCYNBTeditor.html`），跑在单独的窗口里。

主程序只通过两行代码使用它：

```python
from TCYNBTeditor import NbtIO, open_nbt_editor

# NbtIO: 解析 level.dat 等 NBT 文件
# open_nbt_editor: 打开 NBT 编辑器窗口
```

---

## 6. 前端和后端怎么通信

这是最重要的概念，理解了这个，整个项目就通了。

### 前端调用后端（最常用）

```javascript
// 前端 JS 写法：
pywebview.api.get_mods_metadata().then(function(result) {
    // result 是后端 Python 方法的返回值，自动变成 JS 对象
    if (result.success) {
        renderModsList(result.data);  // 拿到数据，渲染页面
    } else {
        alert('出错了: ' + result.error);
    }
});
```

```python
# 后端 Python 写法（Api 类里）：
def get_mods_metadata(self):
    try:
        mods = [...]  # 读文件、处理数据
        return {"success": True, "data": mods}
    except Exception as e:
        return {"success": False, "error": str(e)}
```

### 后端调用前端（较少用）

```python
# 后端 Python 写法：
global_window.evaluate_js('updateProgress(50)')  # 直接执行前端 JS 代码
```

### 关键要点

1. 前端调用后端是 **异步的**（`.then()` 回调），不能当同步用
2. 后端方法名 **不能以 `_` 开头**，否则前端调不了
3. 参数和返回值会自动做 JSON 序列化，所以不能传 Python 的 set、bytes 等非 JSON 类型

---

## 7. 已经做完了什么

### v1.0.5 已完成

| Phase | 功能 | 说明 |
|-------|------|------|
| 7 | Config 备份还原 | 可选范围备份、还原预览、自动安全备份 |
| 8 | 更新确认门禁 | Token 校验、600s 有效期、取消无副作用 |
| 9 | 断点续传 | HTTP Range 探测、条件启用 |
| 10 | Mod 依赖可视化 | 列表/图谱/力向图/网格图，d3.js 渲染 |
| 11 | Mod 批量操作 | 多选/全选/批量启禁用 |
| 12 | Mod 冲突规则 | JSON 规则文件，多 mod 条件匹配 |

### v1.0.6 已完成

| Phase | 功能 | 说明 |
|-------|------|------|
| 13 | 服务器状态/内置浏览器 | 反向代理嵌入网页、地址栏、独立窗口备用 |
| 14 | Crash Log 分析器 | 本地规则匹配 + AI 辅助分析（用户自配 API） |
| 15 | Mod 下载中心 | Modrinth API v2，搜索/过滤/详情/依赖/下载 |
| 16 | 存档管理 + NBT 编辑器 | 完整 NBT 编辑器，对标 NBT Studio 全部核心功能；主程序中现已整合为“存档管理/NBT编辑”，支持从存档卡片打开对应世界的 NBT 编辑器，也支持从存档页顶部直接打开空白 NBT 工作台并拖入 nbt 文件 / 文件夹 |
| 17 | JVM 调优向导 | Java 检测、多维推荐、主方案/备选方案、参数 diff、修正版参数复制、应用指南；当前明确不直接写入 HMCL / PCL |
| 18 | 截图画廊 | 稳定顺序网格布局、懒加载缩略图、灯箱/全屏、漫游模式、收藏夹、批量导出、灯箱快捷操作、收藏夹整夹导出；已修复旧图“插队”、底部不续载与多选入口失效 |

NBT 编辑器做了 3 批 + 后续增强，功能非常丰富，详见 [第 10 节](#10-nbt-编辑器模块详解)。

### 2026-03-14 后续补充（已实现，2026-03-15 已完成手工验收）

| Phase | 功能 | 说明 |
|-------|------|------|
| 19 | 系统概览 | 只读环境快照页面，展示机器概况 + 客户端概况 + 规则建议；已接入刷新按钮、独立前后端模块与打包流程，2026-03-15 已完成手工验收 |

---

## 8. v1.0.6 收尾、验收与后续优化（如果你要继续）

### Phase 17：JVM 调优向导

**当前定位**：功能已完成，作为“检测 + 推荐 + 参数对比 + 一键复制”工具使用，不直接写入第三方启动器配置。

**已完成**：
1. **独立模块拆分**
   - 后端：`jvm_advisor.py`
   - 前端：`jvm_advisor.js`
   - 已编译接入主程序，运行方式与其他页面一致

2. **多维推荐模型**
   - Minecraft 版本
   - Loader（Vanilla / Fabric / Forge / NeoForge）
   - 整合包规模
   - CPU 档位
   - 是否 AMD X3D
   - Java 偏好
   - 场景模板（原版高帧率 / Fabric 优化包 / Forge 中型整合包 / Forge 大型整合包 / NeoForge 新版本大包 / 老版本兼容档）

3. **推荐结果展示**
   - 主方案
   - 备选方案
   - 参数逐项解释
   - 风险提示
   - 不建议场景
   - 建议等级（稳妥 / 进阶 / 实验性）
   - 当前 Java 匹配提示
   - 一键复制主方案 / 修正版参数

4. **当前参数对比**
   - 检测当前启动器参数
   - 与主方案逐项 diff
   - 改动摘要
   - 人话替换建议

5. **页面结构与使用引导**
   - JVM 页面已拆成子页面（总览 / Java 检测 / 参数对比 / 备选方案 / 专业面板）
   - 顶部子页面导航固定显示
   - 切换子页面时自动滚动到 JVM 内容顶部
   - 已增加“启动器应用指南”
   - 已增加“客户端 / 服务端区分说明”

6. **启动自动更新提示改造（并行收尾项）**
   - 启动时自动版本检测已改为静默模式，不再准备直接弹老的版本结果窗口
   - 已接入顶部“灵动岛风格”悬浮提示（全局页面顶端）
   - 已支持状态：正在检查 / 检测到更新点我查看详情 / 检测失败点我重试 / 无更新自动消失
   - 手动“检查更新”按钮也已接入同一顶部提示流程
   - 当前视觉已进一步完成：
     - 与个性化主题（accent color / card bg / blur）同步
     - “点我查看详情 / 点我重试” CTA 高亮
     - 内容宽度平滑伸缩
     - 点击压缩反馈
     - 更顺滑的过渡动画
   - 旧的 `showFetchResultDialog(...)` 连接检查结果弹窗分支已移除，启动与手动检查更新统一走顶部提示 + 版本详情链路
   - 当前剩余工作主要是常规回归验收，而非功能缺口

**后续优化清单（建议按顺序继续）**：
1. **保持当前边界**
   - 由于 HMCL / PCL 没有稳定公开源码接口或官方写回协议，当前不要尝试“自动应用参数到启动器”
   - 保持“生成推荐 + 复制修正版参数 + 明确粘贴路径”是更稳妥的做法

2. **启动器应用指南再细化**
   - HMCL / PCL / 其他启动器中 JVM 参数的具体粘贴位置说明
   - 可考虑补充截图或分栏示例

3. **GC 选择理由强化**
   - 用一句话明确解释为什么当前场景推荐 G1 / ZGC / Shenandoah
   - 区分原版、Fabric、Forge/NeoForge 大型整合包

4. **内存分配警告**
   - 系统总内存不足提示
   - 原版 / Fabric 盲目给过高 Xmx 的提示
   - 大型整合包超过合理区间后的收益下降提示

5. **建议等级与备选方案联动强化**
   - 明确哪些备选方案更适合“保守切换”
   - 明确哪些方案需要先观察兼容性再长期使用

6. **客户端 / 服务端区分说明继续增强**
   - 增加更明确的误用警告
   - 进一步提示服务端参数与客户端目标完全不同

7. **JVM 页面体验继续打磨**
   - 导航区继续优化
   - 信息密度与文案层级再压缩

### Phase 18：截图画廊

**当前定位**：功能已完成，现阶段主要是体验优化与更大样本量验收。

**已完成**：
1. **页面接入**
   - 主程序侧边栏已新增“截图画廊”入口
   - 主页面已新增独立截图页容器
   - 首次进入时会自动扫描截图目录

2. **后端 API**
   - 新增截图目录解析 helper
   - 新增截图元数据扫描 API
   - 新增缩略图批量生成 API
   - 新增灯箱预览 API
   - 新增批量导出到用户指定目录 API
   - 新增 `open_screenshot_with_default_app()` 与 `reveal_screenshot_in_folder()`，分别用于系统默认应用打开图片和打开图片真实父目录

3. **画廊 UI**
   - 稳定顺序 `grid` 布局（避免缩略图异步回填导致视觉插队）
   - 工具栏：刷新、打开截图文件夹、排序、搜索、进入多选、导出所选
   - 缩略图按视口懒加载
   - 点击截图可打开灯箱
   - 灯箱支持上一张 / 下一张 / Esc 关闭 / 左右方向键切换
   - 灯箱已补充“用系统默认应用打开”“打开图片所在目录”“导出（复制）此图”按钮
   - 展示元数据：文件名、修改时间、分辨率、文件大小

4. **批量操作**
   - 多选模式
   - “进入多选”按钮失效问题已修复
   - 全选当前筛选结果
   - 清空选择
   - 导出所选到指定目录
   - 收藏夹页面支持“导出整个收藏夹”

5. **缩略图缓存与性能优化**
   - 缩略图不再只在内存 / base64 中临时生成
   - 现已统一缓存到更新器同级目录下：`thumbnail_cache/screenshots/thumbs`
   - 预览图缓存目录：`thumbnail_cache/screenshots/previews`
   - 缓存 key 基于源文件路径 + 文件大小 + `mtime_ns`
   - 缩略图列表前端改为直接消费缓存文件 URL，降低 JSON 与 WebView 传输压力
   - 打开截图页时会做轻量缓存清理，删除已失效的旧缩略图
   - 首次进入截图页后会对最新一批截图做后台预热
   - 缩略图请求内部已引入有限并行生成
   - 灯箱打开后会顺手预热相邻截图的 preview

**后续优化清单（建议按顺序继续）**：
1. **性能验收**
   - 用 100+ / 500+ 截图进行滚动与懒加载验收
   - 观察是否需要进一步扩大预热窗口

2. **依赖与打包说明**
   - 默认缩略图生成已经迁移到 WebView2 前端，不再要求玩家额外安装 Pillow
   - 若开发环境要保留 Pillow 兜底，需要在文档和打包流程里明确区分“默认路径”和“开发兜底路径”

3. **2026-03-13 稳定性修复（已完成，作为近期修复记录保留）**
   - 截图布局已从多列流式排版调整为稳定顺序 `grid`，修复旧日期截图在异步缩略图加载后视觉上插入到上方的问题
   - 自动继续加载已改为“底部哨兵 + 滚动兜底”双触发，修复滑到底部后不再继续加载下一批截图的问题
   - 新增“运行状态区”和“验收模式”，便于手工区分扫描、缓存命中、前端生成与失败状态

4. **视觉强化**
   - 灯箱操作细节和动画可继续打磨

### Phase 19：系统概览

**当前定位**：功能已实现，当前作为低维护的“环境概览页”使用，不是网络诊断，也不是硬件监控仪表盘。2026-03-15 已完成一轮 Windows + pywebview 实机手工验收。

**已完成**：
1. **页面接入**
   - 侧边栏已新增“系统概览”入口
   - 主页面已新增独立容器 `page-systemoverview`
   - 已接入刷新按钮 `systemoverview-refresh-btn`
   - 切换到该 tab 时会自动初始化并拉取一次快照

2. **后端快照与规则建议**
   - 新增独立模块：`system_overview.py`
   - 新增桥接接口：`Api.get_system_overview()`
   - 系统数据包含：操作系统、CPU、线程数、总内存、可用内存、磁盘空间
   - 客户端数据包含：游戏目录、本地版本、客户端当前使用的 Java（仅在能从常见启动器配置中可靠判断时显示）、Mod 启用/禁用数量、存档数量、截图数量
   - Java 判断会优先读取常见启动器配置里的 Java 路径并与本机检测结果匹配；如果判断不稳，就只显示说明，不伪造版本信息
   - 建议输出为定性等级和少量说明文案，只覆盖 Java / 内存 / 磁盘这些基础条件，不做伪精确数字评分

3. **前端渲染**
   - 新增独立模块：`system_overview.js`
   - 页面拆为“机器概况 / 客户端概况 / 规则建议”三块
   - 已区分加载中、刷新中、失败、最近采样时间等状态
   - 单项字段缺失时允许局部降级，不阻断整个页面渲染

4. **维护边界**
   - 明确不做网络诊断
   - 明确不做实时刷新 / 后台监控
   - 明确不做 GPU 温度 / 占用 / 风扇 / 功耗
   - 明确不做复杂图表与伪精确综合评分
   - 明确不做整合包规模适配判断或“更适合某类整合包”这类结论
   - `build.py` 已把 `system_overview.js` 打包进 EXE

**手工验收建议**：
1. 在正常游戏目录下打开“系统概览”，确认机器概况、客户端概况、建议卡片都能出值。
2. 点击“刷新概览”，确认状态行会切到刷新中并在完成后更新采样时间。
3. 分别在能 / 不能从常见启动器配置里可靠判断 Java 的环境下，看“客户端当前使用的 Java”是否按预期显示版本名或说明文案。
4. 重点观察字段缺失时是否局部显示“未知”而不是整页报错。

**规划文档**：
- `.planning/phases/19-system-overview/19-STATUS.md`
- `.planning/phases/19-system-overview/19-RESEARCH.md`
- `.planning/phases/19-system-overview/19-01-PLAN.md`
- `.planning/phases/19-system-overview/19-02-PLAN.md`

### 更远期想法

这些是更远期的想法，不急：
- 多语言支持（i18n）
- 系统托盘最小化
- 下载限速
- 更新包签名验证
- 自动错误上报

---

## 9. 怎么加一个新功能（手把手教程）

以 Phase 17 "JVM 调优向导"为例，完整走一遍添加新功能的流程。

### 第一步：后端加方法

打开 `TCYServer_MCUpdater.py`，在 `Api` 类里添加方法：

```python
class Api:
    # ... 已有的方法 ...

    def detect_java_versions(self):
        """检测系统中安装的 Java 版本"""
        try:
            versions = []
            # 你的检测逻辑...
            return {"success": True, "data": versions}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_jvm_recommendations(self, system_ram_gb, mod_count):
        """根据系统配置返回 JVM 参数推荐"""
        try:
            recommendations = {}
            # 你的推荐逻辑...
            return {"success": True, "data": recommendations}
        except Exception as e:
            return {"success": False, "error": str(e)}
```

### 第二步：前端加页面

打开 `index.html`，在 HTML 部分添加新页面容器：

```html
<!-- 在其他 page-xxx 旁边加 -->
<div id="page-jvm" class="page" style="display:none;">
    <h2>JVM 调优向导</h2>
    <div id="jvm-content">
        <!-- 页面内容 -->
    </div>
</div>
```

### 第三步：侧边栏加按钮

在 `index.html` 的侧边栏部分加导航按钮：

```html
<div class="nav-item" onclick="showPage('page-jvm')">
    <!-- 图标 SVG -->
    <span>JVM 调优</span>
</div>
```

### 第四步：前端加 JS 逻辑

在 `index.html` 的 `<script>` 部分加函数：

```javascript
function loadJvmPage() {
    pywebview.api.detect_java_versions().then(function(result) {
        if (result.success) {
            renderJavaVersions(result.data);
        }
    });
}

function renderJavaVersions(versions) {
    var html = '';
    versions.forEach(function(v) {
        html += '<div class="jvm-card">' + v.version + '</div>';
    });
    document.getElementById('jvm-content').innerHTML = html;
}
```

### 第五步：在 showPage 里加初始化

```javascript
function showPage(pageId) {
    // ... 已有的切换逻辑 ...

    if (pageId === 'page-jvm') {
        loadJvmPage();
    }
}
```

### 第六步：测试

```bash
python TCYServer_MCUpdater.py
# 点侧边栏的"JVM 调优"按钮，看页面是否正常加载
```

就这么简单。所有功能都是"后端加方法 + 前端加页面 + 通过 pywebview.api 连起来"。

---

## 10. NBT 编辑器模块详解

NBT 编辑器是项目中最复杂的模块，这里单独详细说明。

### 什么是 NBT

NBT（Named Binary Tag）是 Minecraft 用来存储游戏数据的二进制格式。你在 Minecraft 里的所有东西——物品栏、世界种子、实体属性——都是 NBT 格式存储的。

NBT 有 13 种数据类型：

| 类型 ID | 名称 | 对应 | 例子 |
|---------|------|------|------|
| 0 | End | 标记结束 | — |
| 1 | Byte | 8位整数 | 难度值 |
| 2 | Short | 16位整数 | 物品耐久 |
| 3 | Int | 32位整数 | 经验值 |
| 4 | Long | 64位整数 | 世界种子 |
| 5 | Float | 单精度浮点 | 玩家血量 |
| 6 | Double | 双精度浮点 | 坐标 |
| 7 | ByteArray | 字节数组 | — |
| 8 | String | 字符串 | 世界名称 |
| 9 | List | 列表（同类型） | 物品栏 |
| 10 | Compound | 字典（键值对） | 最常见的容器 |
| 11 | IntArray | 整数数组 | — |
| 12 | LongArray | 长整数数组 | — |

### 后端 (`TCYNBTeditor.py`) 结构

```
NbtIO 类 — 纯 Python 实现的 NBT 解析器/写入器
├── read(path)          读取 .dat 文件 → Python 字典
├── write(path, dict)   Python 字典 → 写入 .dat 文件（gzip 压缩）
├── read_mca(path)      读取 .mca 区域文件头部 → 区块列表
├── read_mca_chunk()    读取单个区块的 NBT 数据
├── nbt_to_json()       NBT 字典 → 可读 JSON（用于导出）
└── json_to_nbt()       JSON → NBT 字典（用于导入）

NbtEditorApi 类 — 暴露给前端的 API
├── nbt_open_file()     打开 NBT 文件
├── nbt_save_file()     保存 NBT 文件
├── nbt_save_as()       另存为（弹出文件对话框）
├── nbt_scan_folder()   扫描目录树（过滤出 .dat/.mca 文件）
├── nbt_open_mca_file() 打开 .mca 区域文件
├── nbt_read_mca_chunk() 读取单个区块
├── nbt_export_json()   导出为 JSON
├── nbt_import_json()   从 JSON 导入
├── nbt_append_log()    追加操作日志到磁盘
└── nbt_write_log()     写入日志
```

### 前端 (`TCYNBTeditor.html`) 结构

```
┌─ 左侧：文件树 ──────┐┌─ 中央：编辑器 ──────────────┐┌─ 右侧：大纲 ──┐
│ 收藏夹               ││ 搜索栏 + 替换栏             ││ Outline 面板   │
│ 最近打开              ││ 工具栏按钮                  ││ 只显示容器节点 │
│ 目录树浏览            ││ 编辑操作按钮（编辑模式时）   ││ 点击可跳转     │
│                      ││ 标签页栏（多文件切换）        ││                │
│                      ││ NBT 树渲染区（虚拟滚动）      ││                │
│                      ││                              ││                │
│                      ││                              ││                │
└──────────────────────┘└──────────────────────────────┘└────────────────┘
┌─ 底部：操作日志面板 ─────────────────────────────────────────────────────┐
│ 实时记录所有编辑操作（添加、删除、移动、改名、编辑值...）                 │
│ 取消的操作显示删除线，日志同步写入磁盘                                    │
└──────────────────────────────────────────────────────────────────────────┘
```

### 核心状态变量

```javascript
var _tree = null;           // 当前 NBT 树数据（嵌套的 JS 对象）
var _expanded = {};         // 哪些路径被展开了，key 是 "0.3.1" 格式
var _editMode = false;      // 是否在编辑模式
var _flatRows = [];         // 扁平化的行数组（虚拟滚动用）
var _undoStack = [];        // 撤销栈
var _redoStack = [];        // 重做栈
var _clipboard = null;      // 剪贴板 {node, isCut, sourcePath}
var _tabs = [];             // 多标签页数组
var _activeTabId = null;    // 当前激活的标签页 ID
var _logEntries = [];       // 操作日志
var _editSessions = {};     // 编辑会话追踪 {filePath: session}
```

### 路径系统

NBT 是一棵树，要定位一个节点，用它在树中的**索引路径**：

```
根 Compound
├── [0] Data (Compound)
│   ├── [0] LevelName (String)
│   ├── [1] GameType (Int)
│   └── [2] Player (Compound)
│       └── [0] Health (Float)
```

- `Health` 节点的路径数组：`[0, 2, 0]`（第 0 个子节点的第 2 个子节点的第 0 个子节点）
- 路径字符串（pk）：`"0.2.0"`（用点连接，作为字典的 key）

### 虚拟滚动

NBT 文件可能有几万个节点，不能全部渲染成 DOM 元素（会卡死）。解决方案是**虚拟滚动**：

1. `rebuildFlatRows()` 把树扁平化成一个数组（只包含"当前应该显示的行"，折叠的节点跳过）
2. 根据滚动位置，只渲染**可视区域内**的几十行
3. 用一个占位 `div` 撑开总高度，让滚动条长度正确

### 已实现的功能清单

- 基础：打开/保存/另存为、搜索（含上下导航 + 替换）、编辑值/添加/删除/改类型
- 编辑增强：撤销/重做（200 步）、剪切/复制/粘贴、右键上下文菜单、标签排序
- 高级功能：SNBT 复制、多标签页、数组 Hex 视图、.mca 区域文件、JSON 导出/导入
- 交互优化：拖拽文件打开、跨父级拖拽移动（缩进级别感知）、编辑操作工具栏、帮助弹窗
- 安全保障：未保存修改提示、操作日志面板、编辑会话追踪（保存/取消/中断三状态）

详细的实现方案和代码位置参见 [NBTEditor-DevGuide.md](NBTEditor-DevGuide.md)。

---

## 11. 踩过的坑和注意事项

### 坑 1：inline onclick 里传数组会丢括号

这是最容易中招的 bug。在 HTML 的 onclick 属性里用字符串拼接传 JS 数组：

```javascript
// 错误写法：
var path = [0, 3];
html += '<div onclick="myFunc(' + path + ')">';
// 实际生成：<div onclick="myFunc(0, 3)">  → 变成两个参数了！

// 正确写法：
html += '<div onclick="myFunc(' + JSON.stringify(path) + ')">';
// 实际生成：<div onclick="myFunc([0,3])">  → 正确，一个数组参数
```

而且接收函数要同时兼容数组和字符串输入：

```javascript
function myFunc(pathStr) {
    var path = Array.isArray(pathStr) ? pathStr : JSON.parse(pathStr);
    // ...
}
```

### 坑 2：展开/折叠箭头的事件冒泡

箭头的 `onclick` 如果不加 `event.stopPropagation()`，点击会冒泡到父行的 `selectNode()`，导致内容消失。

```javascript
// 必须加 event.stopPropagation()
var arrow = '<span onclick="event.stopPropagation();toggleExpand(\'' + pk + '\')">▶</span>';
```

### 坑 3：Long 值的 JS 精度问题

NBT 的 Long 是 64 位整数，但 JS 的 Number 只有 53 位精度。世界种子（RandomSeed）就是 Long 类型，如果直接转成 JS Number 会被截断。

解决方案：Long 值在整个管道中始终保持为字符串。

```python
# Python 后端读取时
long_val = struct.unpack('>q', data)[0]
return str(long_val)  # 转成字符串！不是数字

# Python 后端写入时
int(str_val)  # 再转回整数
```

### 坑 4：pywebview 的 loaded 事件时机

`events.loaded` 在 DOM ready 时触发，但 JS 变量和函数可能还没定义完。所以注入初始化调用时要加延迟：

```python
def on_loaded():
    time.sleep(0.3)  # 等 JS 加载完
    nbt_win.evaluate_js("initExplorer(...)")
```

### 坑 5：Windows 路径的反斜杠

Windows 路径如 `C:\Users\saves\world` 在 HTML onclick 属性中需要双重转义：

```python
path = path.replace('\\', '\\\\')  # \ → \\
```

### 坑 6：NbtIO 的读写一致性

如果修改了 `NbtIO` 的解析/写入逻辑，**必须**确保 `read → write → read` 结果完全相同，否则会损坏玩家存档。这是最严重的问题。

### 坑 7：新增后端 API 方法

方法名**不能以下划线 `_` 开头**，否则 pywebview 不会暴露给前端。

### 坑 8：编辑操作必须关联日志会话

新增任何编辑操作时，必须：
1. 调用 `_ensureSession(filePath)` 确保会话存在
2. 调用 `addLog()` 记录日志并关联 `sid`

否则取消操作时日志不会被正确标记。

---

## 12. 相关文档索引

| 文档 | 内容 | 适合谁看 |
|------|------|---------|
| [readme.md](readme.md) | 项目功能介绍、部署指南、changelog | 用户、新开发者了解项目全貌 |
| [CONTRIBUTING.md](CONTRIBUTING.md) | 代码架构详解、各模块修改指南、提交规范 | 开发者修改代码时参考 |
| [NBTEditor-DevGuide.md](NBTEditor-DevGuide.md) | NBT 编辑器功能路线图、每个功能的实现方案 | 继续开发 NBT 编辑器时参考 |
| [HANDOFF.md](HANDOFF.md) | 本文件，技术交接总览 | 新接手的开发者 |
| [1.0.6版本规划方向.txt](1.0.6版本规划方向.txt) | v1.0.6 各 Phase 的原始讨论和设计思路 | 了解为什么要做这些功能 |
| [.planning/phases/19-system-overview/19-STATUS.md](.planning/phases/19-system-overview/19-STATUS.md) | Phase 19 系统概览的正式范围定义 + 当前实现状态 | 手工验收或继续小修前先看 |
| [.planning/phases/19-system-overview/19-RESEARCH.md](.planning/phases/19-system-overview/19-RESEARCH.md) | Phase 19 的技术取舍与低维护实现建议 | 理解为什么范围被刻意收窄时参考 |
| [.planning/phases/19-system-overview/19-01-PLAN.md](.planning/phases/19-system-overview/19-01-PLAN.md) | Phase 19 后端执行计划 | 回看 `system_overview.py` / `Api.get_system_overview()` 的设计意图 |
| [.planning/phases/19-system-overview/19-02-PLAN.md](.planning/phases/19-system-overview/19-02-PLAN.md) | Phase 19 前端执行计划 | 回看 `system_overview.js` / 页面接线方式时参考 |

---

> 最后更新：2026-03-15 | 如有疑问，欢迎在 [GitHub Issues](https://github.com/KanameMadoka520/TCY-Client-Updater/issues) 中提问。
