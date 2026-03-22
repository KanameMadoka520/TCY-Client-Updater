# NBT Editor 开发指南

本文档持续指导 NBT 编辑器（`TCYNBTeditor.py` + `TCYNBTeditor.html`）的功能迭代开发。

---

## 当前架构

```
TCYNBTeditor.py (后端 ~709 行)
  NbtIO            纯 Python NBT 二进制解析/写入 (13 种标签类型)
                   + read_mca / read_mca_chunk (Anvil .mca 区域文件)
                   + nbt_to_json / json_to_nbt (JSON 双向转换)
  NbtEditorApi     pywebview js_api (打开/保存/另存/扫描/MCA/JSON导出导入/日志/最近/收藏/主题)
  open_nbt_editor  创建独立 pywebview 窗口

TCYNBTeditor.html (前端 ~2336 行)
  布局: 左侧文件树 | 中央编辑器(含标签页栏) | 右侧大纲面板 | 底部操作日志面板
  渲染: 虚拟滚动 (ROW_HEIGHT * flatRows)
  编辑: 撤销/重做栈, 剪切/复制/粘贴, 右键菜单, 排序, 跨父级拖拽(缩进级别感知)
  多标签: _tabs 数组, 每 tab 独立状态, 标签栏拖拽排序
  日志: _logEntries 数组, _editSessions 会话追踪, 实时写入磁盘
  状态: _tree, _expanded, _editMode, _flatRows, _searchMatches, _zoomLevel,
        _undoStack, _redoStack, _clipboard, _searchResultPks, _searchIdx, _ctxPath,
        _tabs, _activeTabId, _tabIdCounter, _hexView, _mcaMode, _mcaPath,
        _mcaChunks, _mcaActiveChunk, _logEntries, _logPanelOpen,
        _editSessions, _sessionCounter

NBTEditor-log/ (运行时生成)
  nbt_session_YYYY-MM-DD.log  按日期分割的操作日志文件
```

### 前后端通信

| 方向 | 方式 | 示例 |
|------|------|------|
| 前端 -> 后端 | `pywebview.api.method()` | `pywebview.api.nbt_open_file(path)` |
| 后端 -> 前端 | `nbt_win.evaluate_js()` | `nbt_win.evaluate_js("initExplorer(...)")` |

### NBT 数据结构约定

所有节点统一为 `{type: int, name: string, value: any}` 格式：
- **Compound (10)**: `value` = `[{type, name, value}, ...]`
- **List (9)**: `value` = `{list_type: int, items: [{type, name, value}, ...]}`
- **Scalar (1-6, 8)**: `value` = number | string
- **Array (7, 11, 12)**: `value` = `{array_type: string, values: [...]}`
- **Long (4)**: `value` 序列化为字符串，防止 JS 精度丢失

---

## 功能开发路线图

### 第一批: 核心编辑体验

| # | 功能 | 优先级 | 复杂度 | 状态 |
|---|------|--------|--------|------|
| 1 | **撤销/重做 (Undo/Redo)** | P0 | 中 | 已完成 |
| 2 | **重命名标签名** | P0 | 低 | 已完成 |
| 3 | **搜索结果上/下导航** | P0 | 低 | 已完成 |
| 4 | **剪切/复制/粘贴标签** | P0 | 中 | 已完成 |
| 5 | **右键上下文菜单** | P0 | 中 | 已完成 |

### 第二批: 高级功能

| # | 功能 | 优先级 | 复杂度 | 状态 |
|---|------|--------|--------|------|
| 6 | **SNBT 文本显示/复制/粘贴** | P1 | 中 | 已完成 |
| 7 | **查找并替换** | P1 | 中 | 已完成 |
| 8 | **标签排序 (按名称/类型)** | P1 | 低 | 已完成 |
| 9 | **另存为** | P1 | 低 | 已完成 |
| 10 | **拖拽排序** | P1 | 高 | 已完成 |

### 第三批: 进阶格式支持

| # | 功能 | 优先级 | 复杂度 | 状态 |
|---|------|--------|--------|------|
| 11 | **多标签页** | P2 | 高 | 已完成 |
| 12 | **数组 hex 视图** | P2 | 中 | 已完成 |
| 13 | **.mca 区域文件支持** | P2 | 高 | 已完成 |
| 14 | **JSON 导出/导入** | P2 | 低 | 已完成 |
| 15 | **拖拽文件打开** | P2 | 低 | 已完成 |

### 后续增强: 体验完善与健壮性

| # | 功能 | 优先级 | 复杂度 | 状态 |
|---|------|--------|--------|------|
| 16 | **编辑操作工具栏** | P0 | 低 | 已完成 |
| 17 | **帮助弹窗** | P1 | 低 | 已完成 |
| 18 | **跨父级拖拽 (缩进级别感知)** | P0 | 高 | 已完成 |
| 19 | **未保存修改提示** | P0 | 低 | 已完成 |
| 20 | **操作日志面板** | P1 | 中 | 已完成 |
| 21 | **编辑会话追踪** | P1 | 高 | 已完成 |
| 22 | **标签页拖拽排序** | P1 | 低 | 已完成 |

---

## 各功能实现指南

### 1. 撤销/重做 (Undo/Redo) — 已实现

**实现**: 操作栈模式，最多 200 步。`pushUndo(action)` 记录操作并清空 redoStack。

```
状态: _undoStack, _redoStack
快捷键: Ctrl+Z / Ctrl+Y
工具栏: ↶ / ↷ 按钮 (disabled 时半透明)

操作类型 (applyUndoAction 处理 6 种):
  editVal  — {path, before, after}
  editArr  — {path, arrIdx, before, after}
  rename   — {path, before, after}
  delete   — {parentPath, index, node}
  add      — {parentPath, index, node}
  sort     — {path, before, after} (before/after 是完整 value 数组的 deepClone)

关键函数: pushUndo(), nbtUndo(), nbtRedo(), applyUndoAction(action, isRedo), updateUndoButtons()
打开新文件时清空两个栈。
```

### 2. 重命名标签名 — 已实现

**实现**: 编辑模式下 Compound 子节点的名称变为 `<input>` 输入框，`onchange` 调用 `nbtRename()`。
非编辑模式下可通过右键菜单"重命名"弹出 `prompt()` 对话框。
`nbtRename()` 记录 undo（类型 `rename`）。

### 3. 搜索结果上/下导航 — 已实现

**实现**: 搜索栏右侧 `#search-nav` 包含 ▲▼ 两个按钮。

```
状态: _searchResultPks (匹配 pk 数组), _searchIdx (当前索引)
显示: updateSearchInfo() 渲染 "n/m" 格式
导航: searchNext() / searchPrev() 循环跳转，scrollToMatch(idx)
快捷键: F3 / Shift+F3 / Enter (搜索框内), 全局 F3 监听
```

### 4. 剪切/复制/粘贴标签 — 已实现

**实现**: 内存剪贴板 `_clipboard = {node, isCut, sourcePath}`。

```
nbtCopy(path)  — deepClone 节点存入 _clipboard
nbtCut(path)   — 同 copy 但标记 isCut=true，粘贴时删除源节点
nbtPaste(path) — 仅粘贴到 Compound/List 容器
  Compound: 检查重名 -> 自动加 _1, _2 后缀
  List: 强制 nn.type = list_type, nn.name = ''
  剪切粘贴后清除 isCut 标志 (一次性)
  所有操作记录 undo

快捷键: Ctrl+C / Ctrl+X / Ctrl+V (非 input 焦点时生效, 依赖 _ctxPath)
```

### 5. 右键上下文菜单 — 已实现

**实现**: `<div id="ctx-menu" class="ctx-menu">` 固定定位，`showCtx(event, pathStr)` 动态生成菜单项。

```
菜单项 (根据节点类型/编辑模式动态调整):
  复制 (Ctrl+C)        — 非根节点
  剪切 (Ctrl+X)        — 非根节点, 需编辑模式
  粘贴 (Ctrl+V)        — 容器节点, 需编辑模式+剪贴板非空
  ---
  重命名                — 有名称的非根节点, 需编辑模式
  删除 (Del)            — 非根节点, 需编辑模式
  ---
  按名称排序 / 按类型排序  — Compound 节点, 需编辑模式
  ---
  添加子节点            — 容器节点, 自动进入编辑模式

溢出修正: requestAnimationFrame 检测菜单是否超出窗口边界并调整位置。
点击任意位置 / 其他右键 自动关闭菜单。
```

### 6. SNBT 文本显示/复制 — 已实现

**实现**: `toSnbt(node, indent)` 递归序列化为 SNBT 字符串，`copySnbt(path)` 写入剪贴板。

```
toSnbt(node, indent):
  递归序列化，支持全部 13 种标签类型:
  Byte→1b, Short→42s, Int→100, Long→9999L, Float→3.14f, Double→3.14d
  String→"hello", Compound→{key:val}, List→[items], ByteArray→[B;1b,2b]
  IntArray→[I;1,2], LongArray→[L;1L,2L]
  indent>0 时带缩进和换行

esc_snbt_key(name):
  含特殊字符的键名用双引号包裹

copySnbt(path):
  navTo(path) -> toSnbt(node,1) -> navigator.clipboard.writeText()
  回退: document.execCommand('copy')

入口: 右键上下文菜单 → "复制为 SNBT"
```

### 7. 查找并替换 — 已实现

**实现**: 搜索栏下方增加可折叠的替换行。

```
UI:
  搜索栏左侧 ▼ 按钮调用 toggleReplace() 切换 #replace-bar 显示
  替换行: [替换文本输入框] [替换当前] [全部替换]
  限定: 仅替换标量值 (Scalar types 1-6, 8)
  快捷键: Ctrl+H 切换替换栏

replaceOne():
  当前匹配 -> navTo -> 检查是否标量 -> 修改 value -> pushUndo(editVal) -> searchNext()
  Long 值保持字符串，数字类型尝试 parseFloat

replaceAll():
  遍历 _searchResultPks -> 逐个替换标量 -> 逐个 pushUndo(editVal)
  完成后重建搜索和渲染，状态栏显示替换计数
```

### 8. 标签排序 — 已实现

**实现**: `nbtSortChildren(path, sortBy)` 对 Compound 的 `value` 数组排序。

```
sortBy='name': localeCompare 按名称字母序
sortBy='type': 先按 type 数值序，同 type 再按名称字母序
记录 undo {type:'sort', path, before: deepClone(oldValue), after: deepClone(newValue)}
入口: 右键上下文菜单 → "按名称排序" / "按类型排序"
```

### 9. 另存为 — 已实现

**实现**: 后端 `nbt_save_as()` 调用 pywebview `SAVE_DIALOG`，前端 `saveNbtAs()` 更新路径和标题。

```
后端 (TCYNBTeditor.py):
  NbtEditorApi.nbt_save_as(nbt_json):
    遍历 webview.windows 找到 NBT 窗口 -> create_file_dialog(SAVE_DIALOG)
    保存后自动添加到最近文件列表

前端 (TCYNBTeditor.html):
  saveNbtAs(): 调用后端 -> 成功后更新 _path, 文件标签, topbar 标题
  快捷键: Ctrl+Shift+S
  工具栏: "另存为" 按钮 (编辑模式时显示)
```

### 10. 拖拽排序 — 已实现

**实现**: HTML5 Drag & Drop API，编辑模式下非根节点可拖拽。

```
renderNodeRow() 为编辑模式下的非根节点添加:
  draggable="true" ondragstart/ondragover/ondrop/ondragend

onDragStart(e, pathStr): 记录 _dragSrcPath, 添加 .dragging 样式
onDragOver(e, pathStr): 根据鼠标 Y 位置显示 .drag-over-above/.drag-over-below 指示线
onDragEnd(): 清除所有拖拽样式和状态
onDrop(e, pathStr):
  验证: 不能拖到自身/子节点，必须同级节点 (同父)
  计算插入位置 (考虑上/下方 + 源索引偏移)
  splice 移动节点，记录 undo (type:'sort', before/after 完整数组)
  Compound 和 List 容器均支持
```

### 11. 多标签页 — 已实现

**实现**: 编辑区顶部 tab bar，每个打开的文件/区块一个标签。

```
状态: _tabs (数组), _activeTabId, _tabIdCounter
每个 tab 保存: id, path, name, tree, expanded, editMode, undoStack, redoStack,
  clipboard, searchQuery, ctxPath, hexView, mcaMode, mcaPath, mcaChunks, mcaActiveChunk

saveTabState(): 将当前全局状态写入当前 tab 对象
restoreTabState(tab): 从 tab 对象恢复全局状态并刷新 UI
createTab(path, name): 创建新 tab 或切换到已有同路径 tab
switchTab(tabId): 保存当前 -> 切换 -> 恢复
closeTab(tabId): 关闭并自动切换到相邻 tab
renderTabBar(): 仅在 _tabs.length > 1 时显示

openFile() 和 openMcaFile() 自动调用 createTab()。
标签页显示修改标记 (●) 表示有未保存的 undo 操作。
```

### 12. 数组 hex 视图 — 已实现

**实现**: ByteArray/IntArray/LongArray 展开行显示 HEX 切换按钮。

```
状态: _hexView (对象, pk -> true)

renderNodeRow(): isArr 行右侧添加 .hex-toggle 按钮
toggleHexView(pk): 切换 _hexView[pk] 并刷新渲染
formatArrVal(v, isHex, arrType): 格式化数组值
  byte: 0x00-0xFF (无符号, 2位hex)
  int: 0x00000000 (无符号, 8位hex)
  long: 0x... (直接转换)

renderArrItemRow(): 检查 _hexView[parentPk]，使用 formatArrVal() 显示
hex 模式下使用等宽字体和 accent 颜色以区分
```

### 13. .mca 区域文件支持 — 已实现

**实现**: Anvil 格式区域文件解析 + 32×32 区块网格 UI。

```
后端 (TCYNBTeditor.py):
  NbtIO.read_mca(path): 解析头部 8KB (4096 位置表 + 4096 时间戳表)
    返回 [{x, z, offset, sectors, timestamp}, ...] 非空区块列表
  NbtIO.read_mca_chunk(path, offset): 读取单个区块
    支持压缩类型 1 (gzip), 2 (zlib), 3 (未压缩)
    返回 NBT 树 (通常为 Compound, 名称为空)

  NbtEditorApi.nbt_open_mca_file(path): 返回区块元数据
  NbtEditorApi.nbt_read_mca_chunk(path, offset): 返回单区块 NBT 树
  nbt_open_file() 自动路由 .mca 文件到 nbt_open_mca_file()
  _scan_dir() 扫描时也包含 .mca 文件

前端 (TCYNBTeditor.html):
  openMcaFile(path): 创建 tab + 加载区块元数据
  renderMcaGrid(): 渲染 32x32 CSS Grid
    空区块: 灰色, 有数据: 绿色, 已选中: accent 蓝色
    悬停显示坐标和时间戳
  loadMcaChunk(x, z, offset): 读取区块 -> 切换到 NBT 树视图
```

### 14. JSON 导出/导入 — 已实现

**实现**: 后端双向转换 + 文件对话框。

```
后端 (TCYNBTeditor.py):
  NbtIO.nbt_to_json(nbt_dict): NBT 树 -> 可读 JSON
    每个节点转为 {_type, _name, _value} 格式
    Compound: _value 为 {key: child, ...} 字典
    List: _value 为数组 + _listType
    Array: _value 为数值数组
    Scalar: _value 为原始值

  NbtIO.json_to_nbt(json_dict): JSON -> NBT 树 (逆操作)

  NbtEditorApi.nbt_export_json(nbt_json): SAVE_DIALOG -> json.dump
  NbtEditorApi.nbt_import_json(): OPEN_DIALOG -> json.load -> json_to_nbt

前端 (TCYNBTeditor.html):
  exportJson(): 调用后端导出，状态栏显示结果
  importJson(): 调用后端导入 -> createTab -> 进入编辑模式
  工具栏: "导出JSON" 按钮 (有文件时显示), "导入JSON" 按钮 (始终显示)
```

### 15. 拖拽文件打开 — 已实现

**实现**: 全局拖放监听，支持 .dat/.dat_old/.mca 文件。

```
前端 (TCYNBTeditor.html):
  #drop-overlay: 固定全屏覆盖层 (虚线边框 + 图标 + 提示文字)
  dragenter: _dragCounter++ 并显示覆盖层
  dragleave: _dragCounter-- 当归零时隐藏覆盖层
  dragover: 设置 dropEffect='copy'
  drop: 获取 files[0]，检查后缀，使用 file.path 调用 openFile/openMcaFile

注意: file.path 是 Electron/pywebview 特有属性，标准浏览器不支持。
pywebview 环境下 File 对象通常有 path 属性。
```

### 16. 编辑操作工具栏 — 已实现

**实现**: 编辑模式下显示实体按钮行，快捷键不再是唯一入口。

```
按钮列表: 撤销(Ctrl+Z), 重做(Ctrl+Y), 剪切(Ctrl+X), 复制(Ctrl+C),
  粘贴(Ctrl+V), 添加子节点, 删除(Del), 重命名, 排序▼(下拉),
  SNBT复制, 另存为(Ctrl+Shift+S)
CSS: flex-wrap:wrap 自动换行，display:contents 防止溢出到大纲面板后方
依赖: _ctxPath 用于确定操作目标节点
```

### 17. 帮助弹窗 — 已实现

**实现**: 顶栏"帮助"按钮弹出模态框。

```
内容:
  快捷键列表 (Ctrl+Z/Y/X/C/V/S/Shift+S/H/F/Del/F3)
  功能说明 (搜索、替换、拖拽、编辑模式等)
  开发者信息: GitHub @KanameMadoka520
CSS: 模态框居中, 半透明背景, 点击外部关闭
```

### 18. 跨父级拖拽 (缩进级别感知) — 已实现

**实现**: 重写整个拖拽系统，不再限制同父节点。

```
核心函数 _calcDropInfo(e, pathStr):
  Y 轴判定:
    上方 25%: mode='above' (放在目标行前面)
    中间 50%: mode='into' (放入容器内部，仅容器节点)
    下方 25%: mode='below' (放在目标行后面)

  X 轴缩进级别逃逸 (仅 above/below 模式):
    rowIndentPx = targetDepth * 20 + 12  (节点当前的视觉缩进像素)
    mouseOffsetFromLeft = e.clientX - rect.left
    escapeLevels = floor((rowIndentPx - mouseOffsetFromLeft) / 20)
    escapeLevels = min(escapeLevels, targetPath.length - 1)
    每逃逸一级: 目标路径上移到祖先容器的下一个位置

  返回: {targetPath, mode, escapeLevels, isContainer}

拖拽指示条:
  .drag-indicator 绝对定位横线，宽度和缩进随 escapeLevels 实时变化
  容器模式: 目标行添加 .drag-over-into 蓝色边框

验证规则:
  不能拖到自身
  不能拖到自己的子孙节点 (防止循环引用)
  目标容器为 List 时，强制 node.type = list_type, node.name = ''
  目标容器为 Compound 时，检查重名并自动加 _1, _2 后缀

undo: type='sort', before/after 为受影响父容器的完整 value deepClone
  (跨父级移动时记录两个父容器的 before/after)
```

### 19. 未保存修改提示 — 已实现

**实现**: 关闭标签页或窗口时检查未保存状态。

```
closeTab(tabId):
  hasChanges = tab.undoStack && tab.undoStack.length > 0
  if (hasChanges):
    confirm('文件 "xxx" 有未保存的修改，确定关闭？')
    取消 -> return (不关闭)
    确定 -> endSession(tab.path, 'cancelled') -> 关闭标签

window.onbeforeunload:
  遍历所有 tab，任何有 undoStack 的触发 beforeunload 提示
  同时结束所有未保存会话为 'interrupted'
```

### 20. 操作日志面板 — 已实现

**实现**: 底部可折叠面板，实时显示所有编辑操作。

```
状态: _logEntries = [{time, type, msg, file, sid, cancelled}]
       _logPanelOpen = true

addLog(type, msg, sid):
  创建日志条目 -> push 到 _logEntries
  调用 nbt_append_log(line) 写入磁盘
  自动滚动到最新条目

渲染: renderAllLogEntries()
  每条: <div class="log-entry {type} {cancelled?'cancelled':''}">
  type 颜色: edit=蓝, delete=红, add=绿, session=紫, move=橙
  cancelled 样式: opacity:0.45 + line-through

磁盘日志: NBTEditor-log/nbt_session_YYYY-MM-DD.log
  格式: [HH:MM:SS] [TYPE] message | file: xxx | sid: N
  取消时追加: [HH:MM:SS] [CANCEL_BATCH] sid=N, ops=M
```

### 21. 编辑会话追踪 — 已实现

**实现**: 每个文件的编辑生命周期独立追踪。

```
状态: _editSessions = { filePath: {sid, filePath, file, startTime, opCount, ended, saved} }
       _sessionCounter (全局递增)

_ensureSession(filePath):
  已有未结束的会话 -> 返回
  新建: sid = ++_sessionCounter, 记录 startTime, opCount=0
  addLog('session', '开始编辑会话 #N: filename', sid)

endSession(filePath, status):
  status = 'saved' | 'cancelled' | 'interrupted'
  saved: 会话正常结束，日志不标记
  cancelled: 遍历 _logEntries，所有 sid 匹配的条目标记 cancelled=true
    写入磁盘 CANCEL_BATCH 标记 -> renderAllLogEntries() 刷新为删除线样式
  interrupted: 写入 INTERRUPTED 标记 (程序异常退出)
  delete _editSessions[filePath]

每次编辑操作 (editVal/rename/delete/add/move/paste/sort):
  调用 _ensureSession(filePath)
  sess.opCount++
  addLog() 关联 sid

saveNbtTree() 成功后:
  endSession(filePath, 'saved')

多文件并发: 每个 filePath 独立会话，切换标签不影响其他文件的会话状态
```

### 22. 标签页拖拽排序 — 已实现

**实现**: 标签栏内拖拽改变标签顺序。

```
renderTabBar() 为每个 tab 元素添加 draggable="true"
ondragstart: 记录 _dragTabId
ondragover: 计算鼠标位置在标签的左半/右半，显示插入指示
ondrop: 从 _tabs 数组移动元素，重新渲染标签栏
```

---

## 已完成功能清单

| 功能 | 完成时间 | 备注 |
|------|---------|------|
| NbtIO 二进制解析/写入 (13 种标签) | 2026-03-05 | |
| 文件树浏览器 (递归扫描/过滤) | 2026-03-05 | |
| NBT 树虚拟滚动渲染 | 2026-03-05 | |
| 搜索 (键名+标量值匹配/高亮) | 2026-03-05 | |
| 编辑模式 (编辑值/添加/删除/改类型) | 2026-03-05 | |
| 保存 (gzip 压缩写回) | 2026-03-05 | |
| 展开/折叠全部 | 2026-03-05 | |
| 最近文件 / 收藏夹 | 2026-03-05 | |
| 主题同步 (跟随主程序亮/暗色) | 2026-03-05 | |
| List items 统一包装为 {type,name,value} | 2026-03-05 | 修复 undefined bug |
| 历史记录区域固定高度 | 2026-03-05 | max-height 180px |
| 大纲导航面板 | 2026-03-05 | 右侧 Outline |
| Ctrl+滚轮缩放 (50%-200%) | 2026-03-05 | 编辑区+大纲同步 |
| 撤销/重做 (Undo/Redo) | 2026-03-05 | 操作栈 200 步，Ctrl+Z/Y |
| 重命名标签名 | 2026-03-05 | 编辑模式下名称变输入框 + 右键重命名 |
| 搜索结果上/下导航 | 2026-03-05 | F3/Shift+F3/Enter，显示 n/m 计数 |
| 剪切/复制/粘贴 | 2026-03-05 | Ctrl+C/X/V，跨节点粘贴 |
| 右键上下文菜单 | 2026-03-05 | 复制/剪切/粘贴/重命名/删除/排序/添加 |
| 标签排序 (按名称/类型) | 2026-03-05 | 右键菜单触发，仅 Compound |
| SNBT 文本复制 | 2026-03-05 | toSnbt() 序列化，右键"复制为 SNBT" |
| 查找并替换 | 2026-03-05 | Ctrl+H 切换替换栏，替换当前/全部替换 |
| 另存为 | 2026-03-05 | Ctrl+Shift+S，后端 nbt_save_as() 文件对话框 |
| 拖拽排序 | 2026-03-05 | HTML5 DnD，同级节点间拖拽移动，记录 undo |
| 多标签页 | 2026-03-05 | 每 tab 独立状态，自动切换，修改标记 |
| 数组 hex 视图 | 2026-03-05 | HEX 按钮切换，ByteArr/IntArr/LongArr |
| .mca 区域文件支持 | 2026-03-05 | Anvil 格式解析，32×32 区块网格，点击加载 |
| JSON 导出/导入 | 2026-03-05 | nbt_to_json/json_to_nbt 双向转换 |
| 拖拽文件打开 | 2026-03-05 | 全局 DnD 监听，覆盖层提示 |
| 编辑操作工具栏 | 2026-03-05 | 实体按钮，flex-wrap 自动换行 |
| 帮助弹窗 | 2026-03-05 | 快捷键列表 + 功能说明 + 开发者信息 |
| 跨父级拖拽 (缩进级别感知) | 2026-03-05 | _calcDropInfo, X 轴逃逸, 三区域放置 |
| 未保存修改提示 | 2026-03-05 | closeTab confirm, beforeunload |
| 操作日志面板 | 2026-03-05 | 底部面板, 实时写入 NBTEditor-log/ |
| 编辑会话追踪 | 2026-03-05 | per-file session, 3 种结束状态 |
| 标签页拖拽排序 | 2026-03-05 | 标签栏横向拖拽 |

---

## 开发注意事项

1. **读写往返一致**: 修改 NbtIO 后必须确保 `read -> write -> read` 结果相同
2. **虚拟滚动**: 新增行类型时需在 `flattenNode()` 和 `renderFlatRow()` 中同时处理
3. **路径系统**: 节点路径是索引数组 `[0, 3, 1]`，pk 是 `"0.3.1"` 字符串
4. **Long 精度**: Long 值始终为字符串，编辑/保存时不能转为 JS Number
5. **性能**: 大文件可能有 10000+ 节点，避免全量 DOM 操作，利用虚拟滚动
6. **pywebview API**: 方法名不以 `_` 开头才能被前端调用
7. **打包**: 修改 HTML 后需确保 `build.py` 的 `ADDED_DATA` 包含 `TCYNBTeditor.html`
8. **inline onclick 数组陷阱**: HTML 属性字符串拼接中 JS 数组 `[0,3]` 会丢失方括号，必须 `JSON.stringify(path)` 后拼接，接收端用 `Array.isArray(x)?x:JSON.parse(x)` 兼容
9. **事件冒泡**: 箭头 `onclick` 必须 `event.stopPropagation()`，否则冒泡到父行的 `selectNode()` 导致内容消失
10. **编辑会话**: 新增编辑操作时必须调用 `_ensureSession(filePath)` 并 `addLog()` 关联 `sid`，否则日志不会被会话管理
