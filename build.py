import os
import base64
import sys
import shutil
import glob

# === 配置区 ===
ICON_FILE = "icon.ico"            
MAIN_SCRIPT = "TCYServer_MCUpdater.py" 
ASSET_FILE = "tcy_assets.py"
EXE_NAME = "TCYClientUpdater-1.0.6"
DIST_DIR = "dist"
# 新增：指定要包含的额外文件
# 格式：("源文件", "目标路径")，目标路径 "." 表示根目录
ADDED_DATA = [("index.html", "."), ("lib/d3.min.js", "lib"), ("TCYNBTeditor.html", "."), ("jvm_advisor.js", "."), ("system_overview.js", ".")]

RUNTIME_RESIDUE_FILES = [
    "launcher_debug.log",
    "launcher_settings.json",
    "CRASH_IMPORT.txt",
]


def clean_dist_release_residue():
    os.makedirs(DIST_DIR, exist_ok=True)
    removed = []

    for path in glob.glob(os.path.join(DIST_DIR, "TCYClientUpdater-*.exe")):
        if os.path.basename(path) == f"{EXE_NAME}.exe":
            continue
        try:
            os.remove(path)
            removed.append(path)
        except Exception as e:
            print(f"⚠️ 清理旧 EXE 失败：{path} -> {e}")

    for filename in RUNTIME_RESIDUE_FILES:
        path = os.path.join(DIST_DIR, filename)
        if not os.path.exists(path):
            continue
        try:
            os.remove(path)
            removed.append(path)
        except Exception as e:
            print(f"⚠️ 清理运行时残留失败：{path} -> {e}")

    return removed

def main():
    print("🚀 TCY 更新器自动构建工具启动...")
    removed_before = clean_dist_release_residue()
    if removed_before:
        print(f"🧽 已清理 dist 目录中的旧发布残留：{len(removed_before)} 项")
    
    # 1. 检测并处理背景图片 (逻辑不变)
    bg_b64_str = ""
    if os.path.exists("background.png"):
        print(f"📸 检测到背景图片，正在转换为 Base64...")
        with open("background.png", "rb") as f:
            base64_data = base64.b64encode(f.read()).decode('utf-8')
            bg_b64_str = f"data:image/png;base64,{base64_data}"
        print(f"✅ 转换完成，长度: {len(bg_b64_str)} 字符")
    else:
        print("⚠️ 警告：当前目录下没有 background.png，打包后的程序将是纯白背景！")

    # 2. 生成资源文件 (逻辑不变)
    print(f"📄 正在生成资源模块 {ASSET_FILE}...")
    with open(ASSET_FILE, "w", encoding="utf-8") as f:
        f.write(f'# 这是自动生成的文件，请勿手动修改\n')
        f.write(f'BACKGROUND_IMAGE_B64 = "{bg_b64_str}"\n')

    # 3. 组装 PyInstaller 命令 (修改：加入 --add-data)
    # Windows 下分隔符是 ;  Linux/Mac 下是 :
    path_sep = ";" if os.name == 'nt' else ":"
    
    add_data_str = ""
    for src, dst in ADDED_DATA:
        add_data_str += f'--add-data="{src}{path_sep}{dst}" '

    cmd = [
        "pyinstaller",
        "--noconsole",
        "--onefile",
        f'--name="{EXE_NAME}"',
        f'--hidden-import={ASSET_FILE.replace(".py", "")}',
        '--hidden-import=TCYNBTeditor',
        add_data_str.strip(), # 添加数据文件参数
        MAIN_SCRIPT
    ]

    if os.path.exists(ICON_FILE):
        cmd.insert(4, f"--icon={ICON_FILE}")
    
    cmd_str = " ".join(cmd)
    print(f"🔨 开始打包...\n执行命令: {cmd_str}")
    
    # 4. 执行打包
    exit_code = os.system(cmd_str)

    # 5. 清理 (逻辑不变)
    print("🧹 正在清理临时文件...")
    if os.path.exists(ASSET_FILE):
        os.remove(ASSET_FILE)
    if os.path.exists(f"{EXE_NAME}.spec"):
        os.remove(f"{EXE_NAME}.spec")
    if os.path.exists("build"):
        shutil.rmtree("build")

    removed_after = clean_dist_release_residue()
    if removed_after:
        print(f"🧽 已清理本次构建产生的运行时残留：{len(removed_after)} 项")

    if exit_code == 0:
        print("\n🎉🎉🎉 构建成功！")
        print(f"👉 请在 dist 文件夹中查看: {EXE_NAME}.exe")
    else:
        print("\n❌ 构建失败，请检查上方错误信息。")

if __name__ == "__main__":
    main()
