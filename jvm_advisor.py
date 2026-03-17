# -*- coding: utf-8 -*-
import math

DEFAULT_JVM_ADVISOR_SETTINGS = {
    "mc_version": "1.20.1",
    "loader": "forge",
    "modpack_scale": "medium",
    "cpu_tier": "mainstream",
    "is_x3d": False,
    "preferred_java_version": "auto",
    "template": "custom",
}

JVM_SCENE_TEMPLATES = {
    "custom": {
        "name": "自定义",
        "desc": "按你当前手动选择的条件生成推荐。",
        "settings": {}
    },
    "vanilla_fps": {
        "name": "原版高帧率",
        "desc": "适合原版 / 轻量客户端，重点放在稳定响应和不过度分配内存。",
        "settings": {"mc_version": "1.20.1", "loader": "vanilla", "modpack_scale": "light", "cpu_tier": "high_end", "is_x3d": False, "preferred_java_version": "auto"}
    },
    "fabric_optimized": {
        "name": "Fabric 优化包",
        "desc": "适合 Sodium / Lithium / FerriteCore 一类优化包或轻中型 Fabric 模组组合。",
        "settings": {"mc_version": "1.20.1", "loader": "fabric", "modpack_scale": "medium", "cpu_tier": "mainstream", "is_x3d": False, "preferred_java_version": "auto"}
    },
    "forge_medium": {
        "name": "Forge 中型整合包",
        "desc": "适合 50-100 左右模组的 Forge 客户端，优先兼容和稳妥。",
        "settings": {"mc_version": "1.20.1", "loader": "forge", "modpack_scale": "medium", "cpu_tier": "mainstream", "is_x3d": False, "preferred_java_version": "auto"}
    },
    "forge_large": {
        "name": "Forge 大型整合包",
        "desc": "适合大量内容模组、脚本联动、实体较多的大型 Forge 包。",
        "settings": {"mc_version": "1.20.1", "loader": "forge", "modpack_scale": "large", "cpu_tier": "high_end", "is_x3d": False, "preferred_java_version": "auto"}
    },
    "neoforge_modern": {
        "name": "NeoForge 新版本大包",
        "desc": "适合 1.20.5+ / 1.21+ 的新版本 NeoForge 大型整合包。",
        "settings": {"mc_version": "1.21.1", "loader": "neoforge", "modpack_scale": "large", "cpu_tier": "high_end", "is_x3d": False, "preferred_java_version": "21"}
    },
    "legacy_compat": {
        "name": "老版本兼容档",
        "desc": "适合 1.16.5 及更早代版本，优先兼容性，不追求新 GC。",
        "settings": {"mc_version": "1.16.5", "loader": "forge", "modpack_scale": "medium", "cpu_tier": "mainstream", "is_x3d": False, "preferred_java_version": "auto"}
    },
}

JAVA_VERSION_NOTES = {
    "8": {"status": "legacy", "note": "仅适合 1.16.5 及更早版本；新版本与大型整合包不建议继续停留在 Java 8。"},
    "17": {"status": "recommended", "note": "1.18 - 1.20.4 的主流首选，兼容性与稳定性最好。"},
    "21": {"status": "latest", "note": "1.20.5+ 更推荐 Java 21；可使用分代 ZGC，停顿更低。"},
    "graalvm": {"status": "advanced", "note": "进阶尝试项。可能带来更积极的 JIT 优化，但兼容性要自行验证。"},
}

CPU_TIER_LABELS = {
    "mainstream": "一般 CPU",
    "high_end": "高级 CPU",
    "flagship": "顶级 CPU",
}

LOADER_LABELS = {
    "vanilla": "原版",
    "fabric": "Fabric 优化/轻模组",
    "forge": "Forge",
    "neoforge": "NeoForge",
}

MODPACK_LABELS = {
    "light": "原版 / 轻量",
    "medium": "中型整合包",
    "large": "大型整合包",
}


def normalize_jvm_advisor_settings(raw):
    data = dict(DEFAULT_JVM_ADVISOR_SETTINGS)
    if isinstance(raw, dict):
        data.update(raw)

    template_key = data.get("template") if isinstance(data.get("template"), str) else "custom"
    if template_key not in JVM_SCENE_TEMPLATES:
        template_key = "custom"
    template_settings = JVM_SCENE_TEMPLATES.get(template_key, {}).get("settings", {})
    if template_key != "custom":
        merged = dict(DEFAULT_JVM_ADVISOR_SETTINGS)
        merged.update(template_settings)
        merged.update(data)
        data = merged
    data["template"] = template_key

    legacy_profile = data.get("profile")
    if legacy_profile == "vanilla":
        data["modpack_scale"] = "light"
        data.setdefault("loader", "vanilla")
    elif legacy_profile == "medium":
        data["modpack_scale"] = "medium"
    elif legacy_profile == "large":
        data["modpack_scale"] = "large"
        data.setdefault("loader", "forge")

    if str(data.get("mc_version") or "").strip() == "":
        data["mc_version"] = DEFAULT_JVM_ADVISOR_SETTINGS["mc_version"]

    if data.get("loader") not in LOADER_LABELS:
        data["loader"] = DEFAULT_JVM_ADVISOR_SETTINGS["loader"]
    if data.get("modpack_scale") not in MODPACK_LABELS:
        data["modpack_scale"] = DEFAULT_JVM_ADVISOR_SETTINGS["modpack_scale"]
    if data.get("cpu_tier") not in CPU_TIER_LABELS:
        data["cpu_tier"] = DEFAULT_JVM_ADVISOR_SETTINGS["cpu_tier"]

    preferred = str(data.get("preferred_java_version") or "auto")
    if preferred not in ("auto", "17", "21"):
        preferred = "auto"
    data["preferred_java_version"] = preferred
    data["is_x3d"] = bool(data.get("is_x3d"))
    return data


def _parse_version_tuple(version_text):
    parts = []
    for piece in str(version_text or "").split('.'):
        if piece.isdigit():
            parts.append(int(piece))
        else:
            break
    return tuple(parts or [0])


def _recommended_java_version(mc_version, preferred_java_version):
    version_tuple = _parse_version_tuple(mc_version)
    if version_tuple >= (1, 20, 5):
        auto_java = "21"
    elif version_tuple >= (1, 18):
        auto_java = "17"
    else:
        auto_java = "8"

    if preferred_java_version in ("17", "21"):
        if auto_java == "8":
            return "8", "该 Minecraft 版本仍以 Java 8 兼容性为主，手动偏好不会覆盖基础兼容性。"
        return preferred_java_version, "已按你的 Java 偏好优先生成方案。"
    return auto_java, "已根据 Minecraft 版本自动选择最合适的 Java 大版本。"


def _memory_budget(total_gb, settings):
    total_gb = max(float(total_gb or 0), 0)
    scale = settings["modpack_scale"]
    loader = settings["loader"]
    cpu_tier = settings["cpu_tier"]
    is_x3d = settings["is_x3d"]

    if loader == "vanilla":
        base_map = {"light": 3.0, "medium": 4.5, "large": 5.5}
    elif loader == "fabric":
        base_map = {"light": 3.5, "medium": 5.0, "large": 6.5}
    else:
        base_map = {"light": 4.0, "medium": 6.5, "large": 8.5}

    base = base_map[scale]

    if loader in ("forge", "neoforge") and scale == "large":
        base += 0.5
    if loader == "fabric" and scale == "light":
        base -= 0.5
    if loader == "vanilla" and cpu_tier == "mainstream":
        base -= 0.3
    if is_x3d and scale == "large":
        base -= 0.5

    if total_gb <= 8:
        cap = max(3.0, total_gb * 0.42)
    elif total_gb <= 16:
        cap = total_gb * 0.4
    elif total_gb <= 32:
        cap = total_gb * 0.36
    else:
        cap = min(12.0, total_gb * 0.32)

    if loader == "vanilla":
        cap = min(cap, 6.0)
    elif loader == "fabric":
        cap = min(cap, 8.0 if scale != "large" else 9.0)

    recommended = min(base, cap)
    recommended = max(2.5, recommended)
    xmx = round(recommended * 2) / 2

    if loader == "vanilla":
        xms = min(xmx, 2.0 if xmx <= 4 else 3.0)
    elif loader == "fabric":
        xms = min(xmx, 2.5 if xmx <= 5 else 3.5)
    else:
        xms = min(xmx, 3.0 if xmx <= 6 else max(4.0, xmx / 2))
    xms = round(xms * 2) / 2

    reserve = max(total_gb - xmx, 0)
    if loader == "vanilla":
        profile_note = "原版更偏 CPU / 渲染瓶颈，内存只要够用即可，给太多通常收益很小。"
    elif loader == "fabric":
        profile_note = "Fabric 优化包通常比 Forge 更省堆，但更依赖 CPU、渲染链路和模组自身实现质量。"
    else:
        profile_note = "Forge / NeoForge 更容易在大地图、切维度、批量实体和脚本联动时制造堆压力。"

    if scale == "large":
        scale_note = "大型整合包优先保证稳定堆空间，但通常超过 10-12G 后收益会明显下降。"
    elif scale == "medium":
        scale_note = "中型整合包更适合稳一点的分配策略，避免为了追求极限而把系统挤压得太狠。"
    else:
        scale_note = "轻量场景内存过大反而可能让 GC 单次处理的堆更大。"

    x3d_note = " X3D 大缓存能缓解大型整合包的 CPU/内存访问压力，所以这里略偏保守地控制堆大小，优先换更平滑的帧时间。" if is_x3d else ""

    return {
        "xms_gb": xms,
        "xmx_gb": xmx,
        "suggested_range": f"{max(2, int(math.floor(max(2.0, xmx - 1))))}-{int(math.ceil(xmx + (1 if scale == 'large' else 0)))}G",
        "note": f"总内存 {total_gb:.1f} GB，建议给游戏 {xmx:g} GB，并至少给系统与后台预留 {reserve:.1f} GB。{profile_note} {scale_note}{x3d_note}",
    }


def _build_g1_flags(memory, settings):
    xms = memory["xms_gb"]
    xmx = memory["xmx_gb"]
    loader = settings["loader"]
    scale = settings["modpack_scale"]
    flags = [
        f"-Xms{xms:g}G",
        f"-Xmx{xmx:g}G",
        "-XX:+UseG1GC",
        "-XX:+ParallelRefProcEnabled",
        "-XX:MaxGCPauseMillis=140" if loader == "vanilla" else "-XX:MaxGCPauseMillis=120" if loader == "fabric" else "-XX:MaxGCPauseMillis=100",
        "-XX:+UnlockExperimentalVMOptions",
        "-XX:+DisableExplicitGC",
        "-XX:+AlwaysPreTouch",
        "-XX:G1NewSizePercent=20" if loader == "vanilla" else "-XX:G1NewSizePercent=25" if loader == "fabric" else "-XX:G1NewSizePercent=30",
        "-XX:G1MaxNewSizePercent=35" if loader == "vanilla" else "-XX:G1MaxNewSizePercent=40",
        "-XX:G1ReservePercent=15" if loader in ("vanilla", "fabric") else "-XX:G1ReservePercent=20",
        "-XX:InitiatingHeapOccupancyPercent=20" if loader == "vanilla" else "-XX:InitiatingHeapOccupancyPercent=15",
        "-XX:G1MixedGCCountTarget=3" if loader == "vanilla" else "-XX:G1MixedGCCountTarget=4",
        "-XX:G1HeapWastePercent=5",
        "-XX:G1MixedGCLiveThresholdPercent=90",
        "-XX:G1RSetUpdatingPauseTimePercent=5",
        "-XX:SurvivorRatio=32",
        "-XX:+PerfDisableSharedMem",
        "-Dfile.encoding=UTF-8",
    ]
    if settings["cpu_tier"] in ("high_end", "flagship"):
        flags.append("-XX:ConcGCThreads=4")
    if scale == "large":
        flags.append("-XX:G1HeapRegionSize=8M")
    if loader == "vanilla":
        name = "G1GC（原版/轻量稳妥）"
        desc = "适合原版和轻量客户端，重点是兼容性和避免过度调参。"
        why = "原版通常不需要激进低停顿 GC；控制堆大小和维持稳定响应往往更重要。"
    elif loader == "fabric":
        name = "G1GC（Fabric 平衡方案）"
        desc = "适合 Fabric 优化包与轻中型模组组合，兼顾流畅和兼容。"
        why = "Fabric 场景通常比 Forge 更省堆，G1 足够稳，而且不容易因为参数过激带来副作用。"
    else:
        name = "G1GC（Forge / NeoForge 稳妥主推）"
        desc = "兼容性最好，适合绝大多数 Forge / NeoForge 中大型整合包。"
        why = "你的场景更偏向稳定兼容与成熟经验值，G1 更不容易踩启动器 / Mod 兼容坑。"
    return {
        "key": "g1",
        "name": name,
        "min_java": 17,
        "args": " ".join(flags),
        "desc": desc,
        "why": why,
    }


def _build_zgc_flags(memory, settings):
    xmx = max(memory["xmx_gb"], 6.0)
    xms = min(xmx, max(memory["xms_gb"], xmx / 2))
    loader = settings["loader"]
    flags = [
        f"-Xms{xms:g}G",
        f"-Xmx{xmx:g}G",
        "-XX:+UseZGC",
        "-XX:+ZGenerational",
        "-XX:+AlwaysPreTouch",
        "-XX:+DisableExplicitGC",
        "-XX:+UnlockExperimentalVMOptions",
        "-Dfile.encoding=UTF-8",
    ]
    if settings["cpu_tier"] == "flagship" or settings["is_x3d"]:
        flags.append("-XX:ConcGCThreads=4")
    if loader in ("forge", "neoforge"):
        name = "Generational ZGC（Forge 大包低停顿）"
        desc = "更适合新版本 Forge / NeoForge 大型整合包、高刷新率和复杂脚本环境。"
        why = "当整合包本身就容易制造长时间 GC 停顿时，Java 21 的分代 ZGC 更容易把卡顿压平。"
    elif loader == "fabric":
        name = "Generational ZGC（Fabric 高刷方案）"
        desc = "适合新版本 Fabric、追求高帧率稳定性的高配机器。"
        why = "Fabric 本身堆压力常低于 Forge，只有在你明确追求更平滑帧时间时才值得切到 ZGC。"
    else:
        name = "Generational ZGC（原版进阶尝试）"
        desc = "原版一般不必上 ZGC，但在 Java 21 + 顶级 CPU 场景下可以作为低停顿进阶项。"
        why = "原版本来就不太吃大堆；只有高端机器追求极低停顿时，ZGC 才比较有意义。"
    return {
        "key": "zgc",
        "name": name,
        "min_java": 21,
        "args": " ".join(flags),
        "desc": desc,
        "why": why,
    }


def _build_shenandoah_flags(memory, settings):
    xmx = max(memory["xmx_gb"], 6.0)
    xms = min(xmx, max(memory["xms_gb"], xmx / 2))
    loader = settings["loader"]
    flags = [
        f"-Xms{xms:g}G",
        f"-Xmx{xmx:g}G",
        "-XX:+UseShenandoahGC",
        "-XX:+AlwaysPreTouch",
        "-XX:+DisableExplicitGC",
        "-Dfile.encoding=UTF-8",
    ]
    return {
        "key": "shenandoah",
        "name": "Shenandoah（低停顿备选）" if loader in ("forge", "neoforge") else "Shenandoah（进阶备选）",
        "min_java": 17,
        "args": " ".join(flags),
        "desc": "适合愿意尝试低停顿 GC 的进阶玩家，但整体生态经验少于 G1。",
        "why": "如果你不满意 G1 的停顿表现，但又不想直接切到 Java 21，可以试试它。",
    }


def _split_flag_details(args):
    return [item for item in str(args or "").split() if item.strip()]



def _flag_explanation_map(primary_gc_key):
    base = {
        "-XX:+AlwaysPreTouch": "启动时预热堆内存页，减少游戏过程中首次触碰内存时的卡顿。",
        "-XX:+DisableExplicitGC": "屏蔽显式 Full GC 请求，避免某些模组或库突然触发整堆回收。",
        "-Dfile.encoding=UTF-8": "固定字符编码，避免个别环境下日志、路径或文本处理出现乱码。",
        "-XX:ConcGCThreads=4": "提高并发 GC 线程数，更适合高端 CPU；低端机器不一定有收益。",
    }
    if primary_gc_key == "g1":
        base.update({
            "-XX:+UseG1GC": "启用 G1 GC，这是 Minecraft 最成熟、兼容性最好的路线。",
            "-XX:+ParallelRefProcEnabled": "并行处理引用队列，减少 GC 附带开销。",
            "-XX:MaxGCPauseMillis=140": "对原版更宽松的停顿目标，换取更稳的整体吞吐。",
            "-XX:MaxGCPauseMillis=120": "比较平衡的停顿目标，适合 Fabric 或中型场景。",
            "-XX:MaxGCPauseMillis=100": "对大型 Forge 场景更积极地压低单次停顿，但会增加回收频率。",
            "-XX:G1NewSizePercent=20": "年轻代占比更保守，适合原版轻量场景。",
            "-XX:G1NewSizePercent=25": "比较均衡的年轻代起始比例。",
            "-XX:G1NewSizePercent=30": "给大型整合包更多年轻代空间，减少对象洪峰时的抖动。",
            "-XX:G1MaxNewSizePercent=35": "限制年轻代上限，避免原版场景年轻代膨胀过多。",
            "-XX:G1MaxNewSizePercent=40": "允许年轻代在高负载下扩大，适合中大型整合包。",
            "-XX:G1ReservePercent=15": "保留一定空闲堆空间，轻量场景不用留太大。",
            "-XX:G1ReservePercent=20": "给大型整合包更多安全余量，降低晋升失败概率。",
            "-XX:InitiatingHeapOccupancyPercent=20": "原版场景稍晚开始混合回收，减少过早打断。",
            "-XX:InitiatingHeapOccupancyPercent=15": "更早开始回收老年代，适合中大型模组环境。",
            "-XX:G1MixedGCCountTarget=3": "原版场景降低混合回收轮次，减少额外 GC 负担。",
            "-XX:G1MixedGCCountTarget=4": "中大型整合包用更多轮次平滑回收老年代。",
            "-XX:G1HeapWastePercent=5": "允许少量堆浪费来换取更平滑的回收节奏。",
            "-XX:G1MixedGCLiveThresholdPercent=90": "存活率过高的 Region 不急着混合回收，减少低收益回收。",
            "-XX:G1RSetUpdatingPauseTimePercent=5": "限制 Remembered Set 更新对停顿时间的侵占。",
            "-XX:SurvivorRatio=32": "控制 Eden / Survivor 比例，帮助短命对象更快回收。",
            "-XX:+PerfDisableSharedMem": "关闭某些共享性能计数器，减少不必要的系统层开销。",
            "-XX:G1HeapRegionSize=8M": "增大 Region 尺寸，更适合 8G+ 大堆的大型整合包。",
        })
    elif primary_gc_key == "zgc":
        base.update({
            "-XX:+UseZGC": "启用 ZGC，核心目标是极低停顿。",
            "-XX:+ZGenerational": "启用分代 ZGC，让短命对象和长寿对象分开处理，更适合游戏。",
        })
    elif primary_gc_key == "shenandoah":
        base.update({
            "-XX:+UseShenandoahGC": "启用 Shenandoah，目标同样是低停顿，但实战经验少于 G1。",
        })
    return base



def _describe_flag(flag, explanation_map):
    if flag.startswith("-Xms"):
        return "初始堆内存。设得更高可以减少运行中扩容，但不宜大到挤压系统。"
    if flag.startswith("-Xmx"):
        return "最大堆内存。并不是越大越好，过大可能让单次回收更重。"
    return explanation_map.get(flag, "该参数属于当前方案的组成部分，会与其他参数共同影响停顿、吞吐与兼容性。")



def _parameter_explanations(primary_gc_key, args):
    explanation_map = _flag_explanation_map(primary_gc_key)
    return [
        {
            "flag": flag,
            "meaning": _describe_flag(flag, explanation_map),
            "category": "memory" if flag.startswith("-Xm") else "gc" if flag.startswith("-XX:") or flag.startswith("-XX+") else "runtime",
        }
        for flag in _split_flag_details(args)
    ]


def _risk_notes(primary_key, settings, java_version, memory):
    loader = settings["loader"]
    scale = settings["modpack_scale"]
    notes = []

    if primary_key == "zgc":
        notes.append("ZGC 更适合 Java 21+、高配 CPU 与追求低停顿的场景；如果你更看重兼容性，优先保留 G1 备选。")
        if loader == "vanilla":
            notes.append("原版通常不会从 ZGC 中获得特别夸张的提升，收益往往不如控制帧率、优化资源包与渲染设置明显。")
    elif primary_key == "g1":
        notes.append("G1 是最稳妥的默认选项，但极端大型整合包在切维度、批量实体或长时间游玩后仍可能出现可感知停顿。")
    elif primary_key == "shenandoah":
        notes.append("Shenandoah 属于进阶备选，生态经验少于 G1；如果出现兼容问题，建议回退到 G1。")

    if memory["xmx_gb"] >= 10:
        notes.append("当前堆分配已经不小，如果机器还有浏览器、语音、录屏等后台程序，注意观察系统剩余内存是否被挤压。")
    if loader == "fabric" and scale == "light":
        notes.append("Fabric 轻量场景盲目增加 Xmx 往往收益很低，很多时候 CPU、显卡驱动和模组组合才是真正瓶颈。")
    if loader in ("forge", "neoforge") and scale == "large":
        notes.append("Forge / NeoForge 大型整合包不要一味继续加内存；超过合理区间后，GC 负担和堆扫描成本也会一起上升。")
    if java_version == "8":
        notes.append("Java 8 仅建议用于老版本兼容场景，不建议把新一代 GC 调优思路生搬硬套到它上面。")
    return notes



def _avoid_scenarios(primary_key, settings):
    loader = settings["loader"]
    scale = settings["modpack_scale"]
    avoid = []
    if primary_key == "zgc":
        avoid.append("不建议在低端 CPU、老机器或只是普通原版游玩时为了‘看起来高级’而强上 ZGC。")
        avoid.append("不建议在你还没确认 Java 21 与当前整合包兼容之前，直接把 ZGC 当唯一方案。")
    if primary_key == "g1":
        avoid.append("不建议在超大 Forge 包 + 高刷显示器 + 极度敏感于帧时间抖动的场景里，把 G1 视为唯一答案。")
    if primary_key == "shenandoah":
        avoid.append("不建议把 Shenandoah 当成零成本替代品；若你只是想稳定，不如先用 G1。")
    if loader == "vanilla":
        avoid.append("不建议给原版或轻量客户端分配过高内存；多数情况下 3-5G 就够了。")
    if loader == "fabric" and scale != "large":
        avoid.append("不建议把 Fabric 优化包按 Forge 大整合的思路去给 8G、10G 甚至更高堆内存。")
    if loader in ("forge", "neoforge") and scale == "large":
        avoid.append("不建议在大型整合包里一边无限加内存，一边忽略模组冲突、实体数量、视距和脚本负载。")
    return avoid



def _build_java_match_status(recommended_java, detected_versions):
    versions = detected_versions if isinstance(detected_versions, list) else []
    majors = sorted({str(v.get("major")) for v in versions if v.get("major")}, reverse=True)
    has_recommended = any(str(v.get("major")) == str(recommended_java) for v in versions)
    best = majors[0] if majors else None

    if has_recommended:
        return {
            "level": "ok",
            "title": f"本机已检测到 Java {recommended_java}",
            "detail": "当前主方案所需的 Java 版本已经在本机找到，可以直接按推荐参数落地。"
        }
    if best:
        return {
            "level": "warn",
            "title": f"当前主方案推荐 Java {recommended_java}，但本机最高检测到 Java {best}",
            "detail": "你仍可先参考参数，但更建议切换到推荐 Java 版本后再使用当前主方案。"
        }
    return {
        "level": "danger",
        "title": f"本机未检测到主方案推荐的 Java {recommended_java}",
        "detail": "请先安装或切换到对应 Java 版本，否则当前主方案可能无法正确运行。"
    }


def _recommendation_level(primary_key, settings, java_version):
    loader = settings["loader"]
    scale = settings["modpack_scale"]
    cpu_tier = settings["cpu_tier"]
    if primary_key == "g1":
        return {
            "key": "stable",
            "label": "稳妥",
            "desc": "优先兼容性、容错率和通用性，适合大多数客户端直接落地。"
        }
    if primary_key == "shenandoah":
        return {
            "key": "advanced",
            "label": "进阶",
            "desc": "更偏向低停顿与特定场景优化，适合愿意自己验证效果的玩家。"
        }
    if primary_key == "zgc":
        if java_version == "21" and ((loader in ("forge", "neoforge") and scale == "large") or cpu_tier in ("high_end", "flagship") or settings["is_x3d"]):
            return {
                "key": "advanced",
                "label": "进阶",
                "desc": "建立在 Java 21 和较强硬件之上的低停顿方案，适合追求更平滑帧时间。"
            }
        return {
            "key": "experimental",
            "label": "实验性",
            "desc": "当前场景能尝试，但收益与兼容性更依赖你的环境，建议先备份启动器配置。"
        }
    return {
        "key": "advanced",
        "label": "进阶",
        "desc": "适合愿意继续微调与观察的场景。"
    }


def _launcher_application_guide(settings, java_version, memory):
    return [
        f"先在启动器里把游戏 Java 切到推荐的 Java {java_version}，再处理 JVM 参数；不要先改参数、却仍然用旧 Java。",
        f"把启动器现有 JVM 参数整体备份后，再整串替换为本页主方案；尤其是当前推荐堆范围为 {memory['suggested_range']}。",
        "若启动器同时存在“最大内存”“最小内存”和“自定义 JVM 参数”三处设置，优先避免双重配置互相覆盖。",
        "首次应用后先进入同一张常玩地图或同一整合包场景观察 10-20 分钟，再决定是否改用备选方案。",
    ]


def _client_server_scope_notes(settings):
    loader_label = LOADER_LABELS[settings["loader"]]
    return [
        f"本页推荐默认面向 Minecraft 客户端启动参数，尤其适合 {loader_label} 的本地游玩、单人存档和日常进服。",
        "如果你在调优的是服务端（尤其是独立开服 Java 进程），不要直接照搬客户端方案；服务端更关注 tick、插件/模组负载和长期在线稳定性。",
        "客户端更看重帧时间、切维度和进世界时的卡顿体感；服务端则更看重 TPS、区块加载和多人并发，因此优先级并不相同。",
    ]



def build_jvm_recommendation(settings, total_gb, detected_versions=None):
    settings = normalize_jvm_advisor_settings(settings)
    memory = _memory_budget(total_gb, settings)
    java_version, java_reason = _recommended_java_version(settings["mc_version"], settings["preferred_java_version"])

    loader = settings["loader"]
    scale = settings["modpack_scale"]
    cpu_tier = settings["cpu_tier"]
    is_x3d = settings["is_x3d"]

    if loader == "vanilla":
        use_zgc = java_version == "21" and cpu_tier == "flagship" and not scale == "light"
    elif loader == "fabric":
        use_zgc = java_version == "21" and (cpu_tier in ("high_end", "flagship") or is_x3d) and scale in ("medium", "large")
    else:
        use_zgc = java_version == "21" and (scale == "large" or cpu_tier in ("high_end", "flagship") or is_x3d)

    primary = _build_zgc_flags(memory, settings) if use_zgc else _build_g1_flags(memory, settings)
    alternatives = []
    if primary["key"] != "g1":
        alternatives.append(_build_g1_flags(memory, settings))
    if java_version in ("17", "21") and primary["key"] != "shenandoah":
        alternatives.append(_build_shenandoah_flags(memory, settings))
    if java_version == "21" and primary["key"] != "zgc":
        alternatives.insert(0, _build_zgc_flags(memory, settings))

    summary = [
        f"Minecraft {settings['mc_version']} · {LOADER_LABELS[settings['loader']]} · {MODPACK_LABELS[settings['modpack_scale']]}",
        f"CPU 档位：{CPU_TIER_LABELS[settings['cpu_tier']]}" + (" · AMD X3D" if settings["is_x3d"] else ""),
        f"主推 Java {java_version}，推荐堆内存 {memory['xmx_gb']:g}G。",
    ]

    level = _recommendation_level(primary["key"], settings, java_version)
    launcher_guide = _launcher_application_guide(settings, java_version, memory)
    scope_notes = _client_server_scope_notes(settings)

    compat = []
    if settings["loader"] == "vanilla":
        compat.append("原版 / 轻量客户端通常首先受 CPU 单核、渲染管线和资源包影响，JVM 参数不是决定性因素。")
    if settings["loader"] == "fabric":
        compat.append("Fabric 优化包普遍比 Forge 更省堆，除非你装了很多内容型模组，否则不建议盲目拉高内存。")
    if settings["loader"] in ("forge", "neoforge") and settings["modpack_scale"] == "large":
        compat.append("Forge / NeoForge 大整合包在进世界、切维度、批量加载实体时更容易暴露 GC 抖动。")
    if settings["is_x3d"]:
        compat.append("X3D 大缓存 CPU 对大型整合包经常比单纯高主频更有帮助，因此更适合优先追求低停顿方案。")

    return {
        "system_ram_gb": round(float(total_gb or 0), 1),
        "input": settings,
        "template": {
            "key": settings.get("template", "custom"),
            "name": JVM_SCENE_TEMPLATES.get(settings.get("template", "custom"), JVM_SCENE_TEMPLATES["custom"])["name"],
            "desc": JVM_SCENE_TEMPLATES.get(settings.get("template", "custom"), JVM_SCENE_TEMPLATES["custom"])["desc"],
            "options": [
                {"key": key, "name": item["name"], "desc": item["desc"]}
                for key, item in JVM_SCENE_TEMPLATES.items()
            ]
        },
        "java_choice": {
            "recommended": java_version,
            "reason": java_reason,
            "notes": JAVA_VERSION_NOTES,
        },
        "java_match": _build_java_match_status(java_version, detected_versions),
        "recommendation_level": level,
        "memory": memory,
        "launcher_guide": launcher_guide,
        "scope_notes": scope_notes,
        "primary": {
            **primary,
            "full_args": primary["args"],
            "flag_details": _parameter_explanations(primary["key"], primary["args"]),
        },
        "alternatives": [
            {
                **item,
                "full_args": item["args"],
                "flag_details": _parameter_explanations(item["key"], item["args"]),
            } for item in alternatives[:3]
        ],
        "parameter_explanations": _parameter_explanations(primary["key"], primary["args"]),
        "risk_notes": _risk_notes(primary["key"], settings, java_version, memory),
        "avoid_scenarios": _avoid_scenarios(primary["key"], settings),
        "summary": summary,
        "compatibility_notes": compat,
        "copy_ready": primary["args"],
    }
