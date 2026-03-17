(function () {
    const DEFAULTS = {
        mc_version: '1.20.1',
        loader: 'forge',
        modpack_scale: 'medium',
        cpu_tier: 'mainstream',
        is_x3d: false,
        preferred_java_version: 'auto'
    };

    let jvmAdvisorLoadedOnce = false;
    let jvmAdvisorLoading = false;
    let jvmAdvisorCache = null;

    function esc(value) {
        return typeof escapeHtml === 'function' ? escapeHtml(String(value ?? '')) : String(value ?? '');
    }

    function getJvmAdvisorSettings() {
        const data = {
            template: document.getElementById('jvm-scene-template')?.value || currentSettings.jvm_template || 'custom',
            mc_version: document.getElementById('jvm-mc-version')?.value || currentSettings.mc_version || DEFAULTS.mc_version,
            loader: document.getElementById('jvm-loader')?.value || currentSettings.loader || DEFAULTS.loader,
            modpack_scale: document.getElementById('jvm-modpack-scale')?.value || currentSettings.modpack_scale || currentSettings.jvm_profile || DEFAULTS.modpack_scale,
            cpu_tier: document.getElementById('jvm-cpu-tier')?.value || currentSettings.cpu_tier || DEFAULTS.cpu_tier,
            is_x3d: !!document.getElementById('jvm-is-x3d')?.checked,
            preferred_java_version: document.getElementById('jvm-preferred-java')?.value || currentSettings.preferred_java_version || DEFAULTS.preferred_java_version,
        };
        currentSettings.jvm_template = data.template;
        currentSettings.mc_version = data.mc_version;
        currentSettings.loader = data.loader;
        currentSettings.modpack_scale = data.modpack_scale;
        currentSettings.cpu_tier = data.cpu_tier;
        currentSettings.is_x3d = data.is_x3d;
        currentSettings.preferred_java_version = data.preferred_java_version;
        currentSettings.jvm_profile = data.modpack_scale;
        return data;
    }

    function fillJvmAdvisorFormFromSettings() {
        const merged = { ...DEFAULTS, ...currentSettings };
        const profileToScale = { vanilla: 'light', medium: 'medium', large: 'large' };
        const scale = merged.modpack_scale || profileToScale[merged.jvm_profile] || DEFAULTS.modpack_scale;
        if (document.getElementById('jvm-scene-template')) document.getElementById('jvm-scene-template').value = merged.jvm_template || 'custom';
        if (document.getElementById('jvm-mc-version')) document.getElementById('jvm-mc-version').value = merged.mc_version || DEFAULTS.mc_version;
        if (document.getElementById('jvm-loader')) document.getElementById('jvm-loader').value = merged.loader || DEFAULTS.loader;
        if (document.getElementById('jvm-modpack-scale')) document.getElementById('jvm-modpack-scale').value = scale;
        if (document.getElementById('jvm-cpu-tier')) document.getElementById('jvm-cpu-tier').value = merged.cpu_tier || DEFAULTS.cpu_tier;
        if (document.getElementById('jvm-is-x3d')) document.getElementById('jvm-is-x3d').checked = !!merged.is_x3d;
        if (document.getElementById('jvm-preferred-java')) document.getElementById('jvm-preferred-java').value = merged.preferred_java_version || DEFAULTS.preferred_java_version;
    }

    function uiTone(kind) {
        const map = {
            primary: { color: 'var(--accent-color)', bg: 'color-mix(in srgb, var(--accent-color) 10%, var(--card-bg))', border: 'color-mix(in srgb, var(--accent-color) 24%, rgba(255,255,255,0.35))' },
            success: { color: 'color-mix(in srgb, var(--accent-color) 72%, #10b981)', bg: 'color-mix(in srgb, var(--accent-color) 8%, var(--card-bg))', border: 'color-mix(in srgb, var(--accent-color) 18%, rgba(16,185,129,0.22))' },
            info: { color: 'color-mix(in srgb, var(--accent-color) 62%, #3b82f6)', bg: 'color-mix(in srgb, var(--accent-color) 6%, var(--card-bg))', border: 'color-mix(in srgb, var(--accent-color) 16%, rgba(59,130,246,0.20))' },
            warning: { color: 'color-mix(in srgb, var(--accent-color) 46%, #b45309)', bg: 'color-mix(in srgb, var(--accent-color) 5%, rgba(245,158,11,0.06))', border: 'color-mix(in srgb, var(--accent-color) 12%, rgba(245,158,11,0.24))' },
            danger: { color: 'color-mix(in srgb, var(--accent-color) 38%, #ef4444)', bg: 'color-mix(in srgb, var(--accent-color) 4%, rgba(239,68,68,0.06))', border: 'color-mix(in srgb, var(--accent-color) 10%, rgba(239,68,68,0.24))' },
            neutral: { color: 'var(--text-color)', bg: 'var(--card-bg)', border: 'rgba(255,255,255,0.35)' }
        };
        return map[kind] || map.neutral;
    }

    function formatJvmStatus(status) {
        const map = {
            legacy: { text: '旧版', tone: uiTone('danger') },
            recommended: { text: '推荐', tone: uiTone('success') },
            latest: { text: '较新', tone: uiTone('info') },
            advanced: { text: '进阶', tone: uiTone('primary') }
        };
        const item = map[status] || { text: status || '未知', tone: uiTone('neutral') };
        return { text: item.text, color: item.tone.color, bg: item.tone.bg, border: item.tone.border };
    }

    function renderFlagDetails(flagDetails, limit = 0) {
        const items = Array.isArray(flagDetails) ? flagDetails : [];
        const shown = limit > 0 ? items.slice(0, limit) : items;
        if (!shown.length) return '<div class="card" style="padding:12px; opacity:0.72;">当前没有可展示的参数说明。</div>';
        return shown.map(item => {
            const categoryMap = {
                memory: { text: '内存', tone: uiTone('info') },
                gc: { text: 'GC', tone: uiTone('success') },
                runtime: { text: '运行时', tone: uiTone('primary') }
            };
            const meta = categoryMap[item.category] || { text: '参数', tone: uiTone('neutral') };
            return `
                <div class="card" style="padding:12px; border:1px solid ${meta.tone.border}; background:${meta.tone.bg}; box-shadow:none;">
                    <div style="display:flex; justify-content:space-between; gap:8px; align-items:flex-start; margin-bottom:6px; flex-wrap:wrap;">
                        <div style="font-family:Consolas,monospace; font-size:12px; color:var(--accent-color); word-break:break-all;">${esc(item.flag || '')}</div>
                        <span style="font-size:11px; padding:2px 8px; border-radius:999px; color:${meta.tone.color}; background:color-mix(in srgb, ${meta.tone.color} 10%, transparent); border:1px solid ${meta.tone.border};">${meta.text}</span>
                    </div>
                    <div style="font-size:12px; opacity:0.82; line-height:1.75;">${esc(item.meaning || '')}</div>
                </div>
            `;
        }).join('');
    }

    function toggleJvmPanel(button) {
        const panelId = button?.getAttribute('data-panel-id');
        if (!panelId) return;
        const body = document.getElementById(panelId);
        if (!body) return;
        const expanded = body.style.display !== 'none';
        body.style.display = expanded ? 'none' : 'block';
        button.textContent = expanded ? '展开' : '收起';
    }

    function renderCollapsiblePanel(title, bodyHtml, panelId, expanded = false, tone = 'default') {
        const toneMap = {
            default: uiTone('neutral'),
            primary: uiTone('primary'),
            warning: uiTone('warning'),
            danger: uiTone('danger')
        };
        const toneStyle = toneMap[tone] || toneMap.default;
        return `
            <div class="card" style="padding:14px; border:1px solid ${toneStyle.border}; background:${toneStyle.bg}; box-shadow:none;">
                <div style="display:flex; justify-content:space-between; align-items:center; gap:8px; margin-bottom:${expanded ? '10px' : '0'};">
                    <strong style="font-size:14px; color:${toneStyle.color};">${esc(title)}</strong>
                    <button class="btn outline small" data-panel-id="${esc(panelId)}" onclick="toggleJvmPanel(this)">${expanded ? '收起' : '展开'}</button>
                </div>
                <div id="${esc(panelId)}" style="display:${expanded ? 'block' : 'none'};">${bodyHtml}</div>
            </div>
        `;
    }

    function parseJvmArgs(argsText) {
        const tokens = String(argsText || '').trim().split(/\s+/).filter(Boolean);
        const result = new Map();
        tokens.forEach(token => {
            let key = token;
            let value = '';
            if (token.startsWith('-Xms')) {
                key = '-Xms'; value = token.slice(4);
            } else if (token.startsWith('-Xmx')) {
                key = '-Xmx'; value = token.slice(4);
            } else if (token.startsWith('-XX:')) {
                const eqIndex = token.indexOf('=');
                key = eqIndex >= 0 ? token.slice(0, eqIndex) : token;
                value = eqIndex >= 0 ? token.slice(eqIndex + 1) : 'on';
            } else if (token.startsWith('-D')) {
                const eqIndex = token.indexOf('=');
                key = eqIndex >= 0 ? token.slice(0, eqIndex) : token;
                value = eqIndex >= 0 ? token.slice(eqIndex + 1) : 'set';
            }
            result.set(key, { token, key, value });
        });
        return result;
    }

    function copyEncodedText(encoded) {
        try {
            return copyText(decodeURIComponent(encoded || ''));
        } catch (e) {
            alert('复制失败，请手动复制');
        }
    }

    function renderJvmDiffPanel(launcherProfiles, rec) {
        const launchers = Array.isArray(launcherProfiles) ? launcherProfiles : [];
        if (!launchers.length) {
            return '<div class="card" style="padding:14px; opacity:0.75;">未检测到可对比的启动器参数文件，因此无法生成逐项 diff。你仍可直接复制主方案参数。</div>';
        }
        const recommendedArgs = rec?.copy_ready || '';
        const recommended = parseJvmArgs(recommendedArgs);
        return launchers.map((profile, index) => {
            const current = parseJvmArgs(profile.args || '');
            const keys = Array.from(new Set([...current.keys(), ...recommended.keys()]));
            const changedKeys = [];
            const addedKeys = [];
            const currentOnlyKeys = [];
            const diffAddTone = uiTone('info');
            const diffChangeTone = uiTone('danger');
            const diffCurrentOnlyTone = uiTone('warning');
            const diffSameTone = uiTone('success');
            const rows = keys.map(key => {
                const cur = current.get(key);
                const next = recommended.get(key);
                let status = { text: '一致', color: diffSameTone.color, bg: diffSameTone.bg };
                if (!cur && next) {
                    status = { text: '建议新增', color: diffAddTone.color, bg: diffAddTone.bg };
                    addedKeys.push(key);
                } else if (cur && !next) {
                    status = { text: '当前独有', color: diffCurrentOnlyTone.color, bg: diffCurrentOnlyTone.bg };
                    currentOnlyKeys.push(key);
                } else if ((cur?.token || '') !== (next?.token || '')) {
                    status = { text: '建议调整', color: diffChangeTone.color, bg: diffChangeTone.bg };
                    changedKeys.push(key);
                }
                return `
                    <tr style="border-bottom:1px solid rgba(0,0,0,0.06); vertical-align:top;">
                        <td style="padding:8px 10px; font-family:Consolas,monospace; font-size:12px; white-space:nowrap;">${esc(key)}</td>
                        <td style="padding:8px 10px; font-family:Consolas,monospace; font-size:12px; color:#b45309;">${esc(cur?.token || '—')}</td>
                        <td style="padding:8px 10px; font-family:Consolas,monospace; font-size:12px; color:#047857;">${esc(next?.token || '—')}</td>
                        <td style="padding:8px 10px;"><span style="font-size:11px; padding:2px 8px; border-radius:999px; color:${status.color}; background:${status.bg};">${status.text}</span></td>
                    </tr>
                `;
            }).join('');
            const summary = {
                added: addedKeys.length,
                changed: changedKeys.length,
                currentOnly: currentOnlyKeys.length,
            };
            const focusKeys = [...changedKeys, ...addedKeys].slice(0, 4);
            const summaryText = focusKeys.length
                ? `最关键的差异集中在 ${focusKeys.map(k => `<code>${esc(k)}</code>`).join('、')}。`
                : '当前参数与主方案已经非常接近。';

            const advice = [];
            if (changedKeys.includes('-Xmx') || changedKeys.includes('-Xms')) {
                advice.push('优先先把 <code>-Xms</code> / <code>-Xmx</code> 调到推荐值，因为堆大小是最基础的前提。');
            }
            if (changedKeys.some(k => k.includes('UseG1GC') || k.includes('UseZGC') || k.includes('UseShenandoahGC')) || addedKeys.some(k => k.includes('UseG1GC') || k.includes('UseZGC') || k.includes('UseShenandoahGC'))) {
                advice.push('其次确认 GC 类型和主方案一致，不要同时混用多套 GC 开关。');
            }
            if (changedKeys.some(k => k.includes('MaxGCPauseMillis')) || addedKeys.some(k => k.includes('MaxGCPauseMillis'))) {
                advice.push('然后再调整 <code>MaxGCPauseMillis</code> 这类停顿目标参数，它会直接影响回收节奏。');
            }
            if (currentOnlyKeys.length) {
                advice.push(`对于当前独有的 ${currentOnlyKeys.length} 项参数，除非你明确知道用途，否则建议先按整串修正版替换，而不是手动保留混搭。`);
            }
            if (!advice.length) {
                advice.push('你当前参数已经和主方案很接近；如果游戏运行稳定，可以只核对个别差异项后再决定是否整串替换。');
            }
            const adviceHtml = `<ul style="margin:0; padding-left:18px; line-height:1.9; font-size:13px; opacity:0.86;">${advice.map(item => `<li>${item}</li>`).join('')}</ul>`;

            const body = `
                <div style="font-size:12px; opacity:0.78; margin-bottom:10px; line-height:1.8;">
                    启动器：<strong>${esc(profile.launcher || '启动器')}</strong><br>
                    路径：<code>${esc(profile.path || '')}</code>
                </div>
                <div class="card" style="padding:12px; margin-bottom:10px; border:1px solid rgba(16,185,129,0.22); background:rgba(16,185,129,0.05); box-shadow:none;">
                    <div style="font-size:12px; color:#10b981; font-weight:700; letter-spacing:0.04em; margin-bottom:6px;">改动摘要</div>
                    <div style="font-size:13px; line-height:1.8; opacity:0.86; margin-bottom:8px;">
                        当前启动器参数相对主方案：<strong>建议新增 ${summary.added}</strong> 项、<strong>建议调整 ${summary.changed}</strong> 项、<strong>当前独有 ${summary.currentOnly}</strong> 项。${summaryText}
                    </div>
                    <div style="display:flex; justify-content:space-between; align-items:center; gap:10px; flex-wrap:wrap;">
                        <div style="font-size:12px; opacity:0.72;">下方按钮会直接复制“修正版整串参数”，你可以整串替换启动器里的 JVM 参数。</div>
                        <button class="btn small" onclick="copyEncodedText('${encodeURIComponent('' + recommendedArgs)}')">复制修正版参数</button>
                    </div>
                </div>
                <div class="card" style="padding:12px; margin-bottom:10px; border:1px solid rgba(59,130,246,0.20); background:rgba(59,130,246,0.05); box-shadow:none;">
                    <div style="font-size:12px; color:#3b82f6; font-weight:700; letter-spacing:0.04em; margin-bottom:6px;">人话替换建议</div>
                    ${adviceHtml}
                </div>
                <div style="display:flex; gap:8px; flex-wrap:wrap; margin-bottom:10px;">
                    <span style="font-size:11px; padding:3px 8px; border-radius:999px; background:rgba(59,130,246,0.10); color:#3b82f6;">建议新增 ${summary.added}</span>
                    <span style="font-size:11px; padding:3px 8px; border-radius:999px; background:rgba(239,68,68,0.10); color:#ef4444;">建议调整 ${summary.changed}</span>
                    <span style="font-size:11px; padding:3px 8px; border-radius:999px; background:rgba(245,158,11,0.10); color:#b45309;">当前独有 ${summary.currentOnly}</span>
                </div>
                <div style="overflow:auto; border:1px solid rgba(0,0,0,0.06); border-radius:10px; background:rgba(255,255,255,0.55);">
                    <table style="width:100%; border-collapse:collapse; min-width:760px;">
                        <thead>
                            <tr style="background:rgba(0,0,0,0.03); text-align:left;">
                                <th style="padding:8px 10px; font-size:12px; opacity:0.7;">参数键</th>
                                <th style="padding:8px 10px; font-size:12px; opacity:0.7;">当前启动器</th>
                                <th style="padding:8px 10px; font-size:12px; opacity:0.7;">主方案</th>
                                <th style="padding:8px 10px; font-size:12px; opacity:0.7;">结论</th>
                            </tr>
                        </thead>
                        <tbody>${rows}</tbody>
                    </table>
                </div>
            `;
            return renderCollapsiblePanel(`逐项 diff：${profile.launcher || '启动器'} #${index + 1}`, body, `jvm-diff-panel-${index}`, index === 0, 'default');
        }).join('');
    }

    function switchJvmSubpage(subpage, persist = true) {
        const page = subpage || currentSettings.jvm_subpage || 'overview';
        document.querySelectorAll('[data-jvm-subpage]').forEach(el => {
            el.style.display = el.getAttribute('data-jvm-subpage') === page ? '' : 'none';
        });
        const activeTone = uiTone('primary');
        document.querySelectorAll('[data-jvm-subpage-btn]').forEach(btn => {
            const active = btn.getAttribute('data-jvm-subpage-btn') === page;
            btn.style.background = active ? activeTone.bg : 'var(--card-bg)';
            btn.style.color = active ? activeTone.color : 'var(--text-color)';
            btn.style.borderColor = active ? activeTone.border : 'rgba(255,255,255,0.35)';
            btn.style.boxShadow = active ? `0 6px 18px color-mix(in srgb, ${activeTone.color} 20%, transparent)` : 'none';
            btn.style.opacity = active ? '1' : '0.88';
            btn.style.fontWeight = active ? '700' : '600';
        });
        const titleEl = document.getElementById('jvm-subpage-title');
        if (titleEl) {
            const titleMap = {
                overview: '总览',
                java: 'Java 检测',
                diff: '参数对比',
                alternatives: '备选方案',
                advanced: '专业面板'
            };
            titleEl.textContent = titleMap[page] || '总览';
        }
        const topAnchor = document.getElementById('jvm-subpage-anchor');
        if (topAnchor && typeof topAnchor.scrollIntoView === 'function') {
            topAnchor.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
        currentSettings.jvm_subpage = page;
        if (persist && typeof saveSettingsDebounced === 'function') saveSettingsDebounced();
    }

    function renderJvmSubpageNav() {
        const tabs = [
            { key: 'overview', label: '总览' },
            { key: 'java', label: 'Java 检测' },
            { key: 'diff', label: '参数对比' },
            { key: 'alternatives', label: '备选方案' },
            { key: 'advanced', label: '专业面板' }
        ];
        return `
            <div style="position:sticky; top:0; z-index:20; margin-bottom:12px;">
                <div class="card" style="padding:10px 12px; border:1px solid rgba(255,255,255,0.35); backdrop-filter:blur(var(--card-blur)); background:var(--card-bg); box-shadow:0 8px 24px rgba(15,23,42,0.08);">
                    <div style="display:flex; justify-content:space-between; align-items:center; gap:10px; flex-wrap:wrap; margin-bottom:8px;">
                        <div>
                            <div style="font-size:11px; opacity:0.58; letter-spacing:0.08em; font-weight:700;">JVM SUBPAGE</div>
                            <div id="jvm-subpage-title" style="font-size:18px; font-weight:800; color:var(--accent-color);">总览</div>
                        </div>
                        <div style="font-size:12px; opacity:0.68;">点击子页面可直接跳转查看，不必整页滚动</div>
                    </div>
                    <div style="display:flex; gap:8px; flex-wrap:wrap; align-items:center;">
                        ${tabs.map(tab => `
                            <button class="btn outline small" style="transition:none; transform:none; border-radius:999px; padding:8px 14px; background:var(--card-bg); border:1px solid rgba(255,255,255,0.35); color:var(--text-color);" data-jvm-subpage-btn="${tab.key}" onclick="switchJvmSubpage('${tab.key}')">${tab.label}</button>
                        `).join('')}
                    </div>
                </div>
            </div>
        `;
    }

    function applyJvmTemplateFromResult(template) {
        if (!template || !template.key) return;
        currentSettings.jvm_template = template.key;
        if (document.getElementById('jvm-scene-template')) document.getElementById('jvm-scene-template').value = template.key;
    }

    function renderJvmAdvisor(javaVersions, rec, launcherProfiles) {
        const container = document.getElementById('jvm-content');
        if (!container) return;
        const versions = Array.isArray(javaVersions) ? javaVersions : [];
        const launchers = Array.isArray(launcherProfiles) ? launcherProfiles : [];
        const javaNotes = rec?.java_choice?.notes || {};
        const javaCards = versions.length ? versions.map(v => {
            const statusKey = v.is_graalvm ? 'advanced' : (String(v.major || '') === '21' ? 'latest' : String(v.major || '') === '17' ? 'recommended' : String(v.major || '') === '8' ? 'legacy' : 'recommended');
            const status = formatJvmStatus(statusKey);
            return `
                <div class="card" style="padding:14px; border:1px solid ${status.border}; background:${status.bg}; box-shadow:none;">
                    <div style="display:flex; justify-content:space-between; gap:10px; align-items:flex-start; margin-bottom:8px;">
                        <div>
                            <div style="font-weight:700; font-size:15px;">Java ${esc(v.version || '未知')}</div>
                            <div style="font-size:12px; opacity:0.7; margin-top:4px;">${esc(v.runtime || '')}</div>
                        </div>
                        <span style="font-size:11px; color:${status.color}; background:color-mix(in srgb, ${status.color} 12%, transparent); border:1px solid ${status.border}; border-radius:999px; padding:3px 8px;">${status.text}</span>
                    </div>
                    <div style="font-size:12px; line-height:1.8; opacity:0.82;">
                        <div>路径：<code>${esc(v.path || '')}</code></div>
                        <div>来源：${esc(v.source || '未知')} · 架构：${esc(v.arch || '未知')}</div>
                    </div>
                </div>
            `;
        }).join('') : '<div class="card" style="padding:16px; opacity:0.75;">未检测到可用 Java。你仍然可以先按下方方案手动选择 Java 版本与参数。</div>';

        const javaVersionNotes = Object.entries(javaNotes).map(([key, item]) => {
            const status = formatJvmStatus(item.status);
            return `<div class="card" style="padding:12px;"><div style="display:flex; justify-content:space-between; align-items:center; gap:8px;"><strong>${esc(key === 'graalvm' ? 'GraalVM' : 'Java ' + key)}</strong><span style="font-size:11px; color:${status.color};">${status.text}</span></div><div style="font-size:12px; opacity:0.78; margin-top:6px; line-height:1.7;">${esc(item.note || '')}</div></div>`;
        }).join('');

        const templateTone = uiTone('info');
        const primaryTone = uiTone('success');
        const adviceTone = uiTone('info');
        const summaryTone = uiTone('success');

        const launcherCards = launchers.length ? launchers.map(item => `
            <div class="card" style="padding:14px;">
                <div style="display:flex; justify-content:space-between; gap:8px; align-items:center; flex-wrap:wrap; margin-bottom:8px;">
                    <strong>${esc(item.launcher || '启动器')}</strong>
                    <span style="font-size:11px; opacity:0.7;">已检测到当前 JVM 参数</span>
                </div>
                <div style="font-size:12px; opacity:0.72; line-height:1.7; margin-bottom:8px;">路径：<code>${esc(item.path || '')}</code></div>
                <div style="display:grid; grid-template-columns:1fr 1fr; gap:10px;">
                    <div>
                        <div style="font-size:12px; opacity:0.7; margin-bottom:6px;">当前值</div>
                        <textarea readonly style="width:100%; min-height:110px; resize:vertical; padding:10px; border-radius:8px; border:1px solid var(--border-color); background:rgba(0,0,0,0.04); color:var(--text-color); font-family:Consolas,monospace; font-size:12px; box-sizing:border-box;">${item.args || ''}</textarea>
                    </div>
                    <div>
                        <div style="font-size:12px; opacity:0.7; margin-bottom:6px;">推荐值（${esc(rec?.primary?.name || '主方案')}）</div>
                        <textarea readonly style="width:100%; min-height:110px; resize:vertical; padding:10px; border-radius:8px; border:1px solid ${primaryTone.border}; background:color-mix(in srgb, ${primaryTone.bg} 65%, var(--card-bg)); color:var(--text-color); font-family:Consolas,monospace; font-size:12px; box-sizing:border-box;">${rec?.copy_ready || ''}</textarea>
                    </div>
                </div>
                <div style="display:flex; justify-content:flex-end; gap:8px; margin-top:8px; flex-wrap:wrap;">
                    <button class="btn outline small" onclick="copyEncodedText('${encodeURIComponent('' + (item.args || ''))}')">复制当前值</button>
                    <button class="btn small" onclick="copyEncodedText('${encodeURIComponent('' + (rec?.copy_ready || ''))}')">复制推荐值</button>
                </div>
            </div>
        `).join('') : '<div class="card" style="padding:16px; opacity:0.72;">未检测到 HMCL / PCL 的 JVM 参数配置文件。若你使用其他启动器，可直接复制下方一键参数。</div>';

        const alternatives = (rec?.alternatives || []).map(item => `
            <div class="card" style="padding:16px;">
                <div style="display:flex; justify-content:space-between; gap:8px; align-items:center; margin-bottom:8px; flex-wrap:wrap;">
                    <strong>${esc(item.name || item.key || '备选方案')}</strong>
                    <span style="font-size:11px; opacity:0.7;">最低 Java ${esc(item.min_java || '-')}</span>
                </div>
                <div style="font-size:12px; opacity:0.8; line-height:1.7; margin-bottom:6px;">${esc(item.desc || '')}</div>
                <div style="font-size:12px; opacity:0.75; line-height:1.7; margin-bottom:8px;">${esc(item.why || '')}</div>
                <textarea readonly style="width:100%; min-height:92px; resize:vertical; padding:10px; border-radius:8px; border:1px solid var(--border-color); background:rgba(0,0,0,0.04); color:var(--text-color); font-family:Consolas,monospace; font-size:12px; box-sizing:border-box;">${item.full_args || ''}</textarea>
                <div style="display:flex; justify-content:flex-end; margin-top:8px; margin-bottom:10px;">
                    <button class="btn outline small" onclick="copyEncodedText('${encodeURIComponent('' + (item.full_args || ''))}')">复制备选参数</button>
                </div>
                <div style="font-size:12px; font-weight:700; margin-bottom:8px; opacity:0.8;">关键参数拆解</div>
                <div style="display:grid; grid-template-columns:1fr; gap:8px;">${renderFlagDetails(item.flag_details || [], 6)}</div>
            </div>
        `).join('');

        const javaMatch = rec?.java_match || { level: 'warn', title: 'Java 匹配状态未知', detail: '当前无法判断本机 Java 与主方案的匹配情况。' };
        const recommendationLevel = rec?.recommendation_level || { key: 'advanced', label: '进阶', desc: '当前方案适合愿意继续观察和调优的场景。' };
        const launcherGuide = (rec?.launcher_guide || []).map(item => `<li>${esc(item)}</li>`).join('') || '<li>当前没有额外的启动器应用说明。</li>';
        const scopeNotes = (rec?.scope_notes || []).map(item => `<li>${esc(item)}</li>`).join('') || '<li>当前没有额外的客户端 / 服务端说明。</li>';
        const levelTone = recommendationLevel.key === 'stable'
            ? uiTone('success')
            : recommendationLevel.key === 'experimental'
            ? uiTone('warning')
            : uiTone('primary');
        const matchTone = javaMatch.level === 'ok'
            ? { ...uiTone('success'), label: '匹配正常' }
            : javaMatch.level === 'danger'
            ? { ...uiTone('danger'), label: '需要处理' }
            : { ...uiTone('warning'), label: '建议切换' };
        const templateInfo = rec?.template || { name: '自定义', desc: '' };
        const explainCards = renderFlagDetails(rec?.parameter_explanations || []);
        const summaryList = (rec?.summary || []).map(item => `<li>${esc(item)}</li>`).join('');
        const riskList = (rec?.risk_notes || []).map(item => `<li>${esc(item)}</li>`).join('') || '<li>当前没有额外风险提示。</li>';
        const avoidList = (rec?.avoid_scenarios || []).map(item => `<li>${esc(item)}</li>`).join('') || '<li>当前没有额外的不建议场景。</li>';

        const parameterPanel = renderCollapsiblePanel(
            '参数说明面板',
            `<div style="font-size:13px; line-height:1.8; opacity:0.82; margin-bottom:10px;">下方按 <strong>内存</strong>、<strong>GC</strong>、<strong>运行时</strong> 三类拆解当前主方案中的关键参数。你复制整串即可直接使用；只有在明确知道自己要改什么时，才建议单独改某一项。</div><div style="display:grid; grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); gap:12px;">${explainCards}</div>`,
            'jvm-parameter-panel',
            false,
            'primary'
        );
        const diffPanel = renderCollapsiblePanel(
            '当前启动器参数 vs 主方案 diff',
            `<div style="font-size:13px; line-height:1.8; opacity:0.82; margin-bottom:10px;">下面会把检测到的启动器 JVM 参数与当前主方案逐项对比：<strong>一致</strong>、<strong>建议新增</strong>、<strong>建议调整</strong>、<strong>当前独有</strong>。这样你不用自己肉眼比整串参数。</div>${renderJvmDiffPanel(launcherProfiles, rec)}`,
            'jvm-diff-panel-root',
            true,
            'primary'
        );
        const riskPanel = renderCollapsiblePanel(
            '风险提示',
            `<ul style="margin:0; padding-left:18px; line-height:1.9; font-size:13px; opacity:0.86;">${riskList}</ul>`,
            'jvm-risk-panel',
            true,
            'warning'
        );
        const avoidPanel = renderCollapsiblePanel(
            '不建议场景',
            `<ul style="margin:0; padding-left:18px; line-height:1.9; font-size:13px; opacity:0.86;">${avoidList}</ul>`,
            'jvm-avoid-panel',
            false,
            'danger'
        );
        const compatList = (rec?.compatibility_notes || []).map(item => `<li>${esc(item)}</li>`).join('') || '<li>当前场景下没有额外兼容性警告，优先按主方案落地即可。</li>';
        const launcherGuidePanel = renderCollapsiblePanel(
            '启动器应用指南',
            `<ul style="margin:0; padding-left:18px; line-height:1.9; font-size:13px; opacity:0.86;">${launcherGuide}</ul>`,
            'jvm-launcher-guide-panel',
            true,
            'primary'
        );
        const scopePanel = renderCollapsiblePanel(
            '客户端 / 服务端区分说明',
            `<ul style="margin:0; padding-left:18px; line-height:1.9; font-size:13px; opacity:0.86;">${scopeNotes}</ul>`,
            'jvm-scope-panel',
            true,
            'warning'
        );

        container.innerHTML = `
            <div id="jvm-subpage-anchor"></div>
            ${renderJvmSubpageNav()}

            <div data-jvm-subpage="overview">
                <div class="card" style="padding:16px; margin-bottom:12px; border:1px solid ${templateTone.border}; background:${templateTone.bg}; box-shadow:none;">
                    <div style="display:flex; justify-content:space-between; align-items:center; gap:10px; flex-wrap:wrap; margin-bottom:8px;">
                        <div>
                            <div style="font-size:11px; opacity:0.6; letter-spacing:0.08em; font-weight:700;">SCENE TEMPLATE</div>
                            <div style="font-size:18px; font-weight:800; color:${templateTone.color};">${esc(templateInfo.name || '自定义')}</div>
                        </div>
                        <span style="font-size:11px; padding:3px 8px; border-radius:999px; background:color-mix(in srgb, ${templateTone.color} 12%, transparent); color:${templateTone.color}; border:1px solid ${templateTone.border};">模板</span>
                    </div>
                    <div style="font-size:13px; line-height:1.8; opacity:0.84;">${esc(templateInfo.desc || '按当前手动选择的条件生成推荐。')}</div>
                </div>

                <div style="display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); gap:12px; margin-bottom:12px;">
                    <div class="card" style="padding:16px;">
                        <div style="font-size:13px; opacity:0.7; margin-bottom:6px;">系统总内存</div>
                        <div style="font-size:28px; font-weight:800; color:var(--accent-color);">${esc(String(rec?.system_ram_gb || 0))} GB</div>
                        <div style="font-size:12px; opacity:0.78; margin-top:8px; line-height:1.8;">推荐分配：<strong>${esc(rec?.memory?.suggested_range || '-')}</strong><br>${esc(rec?.memory?.note || '')}</div>
                    </div>
                    <div class="card" style="padding:16px;">
                        <div style="font-size:13px; opacity:0.7; margin-bottom:6px;">Java 主推</div>
                        <div style="font-size:26px; font-weight:800; color:var(--accent-color);">Java ${esc(rec?.java_choice?.recommended || '-')}</div>
                        <div style="font-size:12px; opacity:0.8; margin-top:8px; line-height:1.8;">${esc(rec?.java_choice?.reason || '')}</div>
                    </div>
                </div>

                <div class="card" style="padding:16px; margin-bottom:14px; border:1px solid ${primaryTone.border}; background:linear-gradient(180deg, ${primaryTone.bg}, color-mix(in srgb, ${primaryTone.bg} 55%, transparent)); box-shadow:none;">
                    <div style="display:flex; justify-content:space-between; gap:10px; align-items:center; flex-wrap:wrap; margin-bottom:8px;">
                        <div>
                            <div style="font-size:12px; color:${primaryTone.color}; font-weight:700; letter-spacing:0.04em; margin-bottom:4px;">PRIMARY</div>
                            <h3 style="margin:0;">主方案：${esc(rec?.primary?.name || '未生成')}</h3>
                        </div>
                        <button class="btn small" onclick="copyEncodedText('${encodeURIComponent('' + (rec?.copy_ready || ''))}')">复制主方案</button>
                    </div>
                    <div style="font-size:13px; line-height:1.8; opacity:0.85; margin-bottom:8px;">${esc(rec?.primary?.desc || '')}<br>${esc(rec?.primary?.why || '')}</div>
                    <textarea readonly style="width:100%; min-height:118px; resize:vertical; padding:10px; border-radius:8px; border:1px solid ${primaryTone.border}; background:color-mix(in srgb, ${primaryTone.bg} 70%, var(--card-bg)); color:var(--text-color); font-family:Consolas,monospace; font-size:12px; box-sizing:border-box;">${rec?.copy_ready || ''}</textarea>
                    <div style="display:grid; grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); gap:10px; margin-top:12px;">
                        <div class="card" style="padding:12px; box-shadow:none; border:1px solid rgba(0,0,0,0.06);">
                            <div style="font-size:12px; opacity:0.7; margin-bottom:6px;">推荐 Java</div>
                            <div style="font-size:20px; font-weight:800; color:var(--accent-color);">Java ${esc(rec?.java_choice?.recommended || '-')}</div>
                        </div>
                        <div class="card" style="padding:12px; box-shadow:none; border:1px solid rgba(0,0,0,0.06);">
                            <div style="font-size:12px; opacity:0.7; margin-bottom:6px;">推荐堆范围</div>
                            <div style="font-size:20px; font-weight:800; color:var(--accent-color);">${esc(rec?.memory?.suggested_range || '-')}</div>
                        </div>
                    </div>
                    <div style="margin-top:12px;">
                        <div style="font-size:12px; font-weight:700; margin-bottom:8px; opacity:0.8;">主方案关键参数拆解</div>
                        <div style="display:grid; grid-template-columns:1fr; gap:8px;">${renderFlagDetails(rec?.primary?.flag_details || [], 10)}</div>
                    </div>
                </div>

                <div class="card" style="padding:16px; margin-bottom:14px; border:1px solid ${matchTone.border}; background:${matchTone.bg};">
                    <div style="display:flex; justify-content:space-between; gap:10px; align-items:center; flex-wrap:wrap; margin-bottom:8px;">
                        <div>
                            <div style="font-size:11px; font-weight:700; letter-spacing:0.08em; color:${matchTone.color};">JAVA MATCH</div>
                            <div style="font-size:18px; font-weight:800; color:${matchTone.color};">${esc(javaMatch.title || '')}</div>
                        </div>
                        <span style="font-size:11px; padding:3px 8px; border-radius:999px; color:${matchTone.color}; background:rgba(255,255,255,0.52);">${matchTone.label}</span>
                    </div>
                    <div style="font-size:13px; line-height:1.8; opacity:0.84;">${esc(javaMatch.detail || '')}</div>
                </div>

                <div class="card" style="padding:16px; margin-bottom:14px; border:1px solid ${levelTone.border}; background:${levelTone.bg};">
                    <div style="display:flex; justify-content:space-between; gap:10px; align-items:center; flex-wrap:wrap; margin-bottom:8px;">
                        <div>
                            <div style="font-size:11px; font-weight:700; letter-spacing:0.08em; color:${levelTone.color};">RECOMMENDATION LEVEL</div>
                            <div style="font-size:18px; font-weight:800; color:${levelTone.color};">${esc(recommendationLevel.label || '进阶')}</div>
                        </div>
                        <span style="font-size:11px; padding:3px 8px; border-radius:999px; color:${levelTone.color}; background:rgba(255,255,255,0.52); border:1px solid ${levelTone.border};">方案等级</span>
                    </div>
                    <div style="font-size:13px; line-height:1.8; opacity:0.84;">${esc(recommendationLevel.desc || '')}</div>
                </div>

                <div class="card" style="padding:16px; margin-bottom:14px;">
                    <h3 style="margin:0 0 10px 0;">场景总结</h3>
                    <ul style="margin:0; padding-left:18px; line-height:1.9; font-size:13px; opacity:0.85;">${summaryList}</ul>
                </div>

                <div style="display:grid; grid-template-columns:1fr; gap:12px; margin-bottom:14px;">
                    ${launcherGuidePanel}
                    ${scopePanel}
                </div>
            </div>

            <div data-jvm-subpage="java" style="display:none;">
                <h3 style="margin:0 0 10px 0;">本机 Java 检测</h3>
                <div style="display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); gap:12px; margin-bottom:14px;">${javaCards}</div>

                <h3 style="margin:14px 0 10px 0;">Java 版本建议</h3>
                <div style="display:grid; grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); gap:12px; margin-bottom:14px;">${javaVersionNotes}</div>
            </div>

            <div data-jvm-subpage="diff" style="display:none;">
                <h3 style="margin:0 0 10px 0;">当前启动器参数对比</h3>
                <div style="display:grid; grid-template-columns:1fr; gap:12px; margin-bottom:14px;">${launcherCards}</div>

                <h3 style="margin:14px 0 10px 0;">主方案差异面板</h3>
                <div style="display:grid; grid-template-columns:1fr; gap:12px; margin-bottom:14px;">${diffPanel}</div>
            </div>

            <div data-jvm-subpage="alternatives" style="display:none;">
                <h3 style="margin:0 0 10px 0;">备选方案</h3>
                <div style="display:grid; grid-template-columns:repeat(auto-fit,minmax(320px,1fr)); gap:12px; margin-bottom:14px;">${alternatives || '<div class="card" style="padding:14px; opacity:0.75;">当前没有额外备选项。</div>'}</div>
            </div>

            <div data-jvm-subpage="advanced" style="display:none;">
                <h3 style="margin:0 0 10px 0;">专业说明面板</h3>
                <div style="display:grid; grid-template-columns:1fr; gap:12px; margin-bottom:14px;">
                    ${parameterPanel}
                    ${riskPanel}
                    ${avoidPanel}
                    ${scopePanel}
                </div>

                <h3 style="margin:14px 0 10px 0;">兼容性提醒</h3>
                <div class="card" style="padding:16px;"><ul style="margin:0; padding-left:18px; line-height:1.9; font-size:13px; opacity:0.85;">${compatList}</ul></div>
            </div>
        `;
        switchJvmSubpage(currentSettings.jvm_subpage || 'overview', false);
    }

    async function loadJvmAdvisor(forceRefresh = false) {
        const container = document.getElementById('jvm-content');
        if (!container || jvmAdvisorLoading) return;
        const settings = getJvmAdvisorSettings();
        saveSettingsDebounced();

        if (jvmAdvisorLoadedOnce && !forceRefresh && jvmAdvisorCache) {
            renderJvmAdvisor(jvmAdvisorCache.javaVersions, jvmAdvisorCache.recommendation, jvmAdvisorCache.launcherProfiles);
            return;
        }

        jvmAdvisorLoading = true;
        container.innerHTML = '<div class="card" style="padding:24px; text-align:center; opacity:0.55;">正在检测 Java 与系统内存…</div>';
        try {
            const [javaRes, recRes, launcherRes] = await Promise.all([
                pywebview.api.detect_java_versions(),
                pywebview.api.get_jvm_recommendations(JSON.stringify(settings)),
                pywebview.api.get_launcher_jvm_profiles()
            ]);
            if (!javaRes.success) throw new Error(javaRes.error || 'Java 检测失败');
            if (!recRes.success) throw new Error(recRes.error || '推荐数据加载失败');
            if (!launcherRes.success) throw new Error(launcherRes.error || '启动器参数检测失败');
            jvmAdvisorCache = {
                javaVersions: javaRes.data || [],
                recommendation: recRes.data || {},
                launcherProfiles: launcherRes.data || []
            };
            applyJvmTemplateFromResult(jvmAdvisorCache.recommendation?.template);
            jvmAdvisorLoadedOnce = true;
            renderJvmAdvisor(jvmAdvisorCache.javaVersions, jvmAdvisorCache.recommendation, jvmAdvisorCache.launcherProfiles);
        } catch (e) {
            container.innerHTML = '<div class="card" style="padding:24px; color:#ef4444;">JVM 调优向导加载失败：' + esc(String(e)) + '</div>';
        } finally {
            jvmAdvisorLoading = false;
        }
    }

    function setupJvmAdvisorEvents() {
        const templateEl = document.getElementById('jvm-scene-template');
        if (templateEl && !templateEl.dataset.jvmBound) {
            templateEl.dataset.jvmBound = '1';
            templateEl.addEventListener('change', () => {
                currentSettings.jvm_template = templateEl.value || 'custom';
                loadJvmAdvisor(true);
            });
        }
        const ids = ['jvm-mc-version', 'jvm-loader', 'jvm-modpack-scale', 'jvm-cpu-tier', 'jvm-preferred-java'];
        ids.forEach(id => {
            const el = document.getElementById(id);
            if (el && !el.dataset.jvmBound) {
                el.dataset.jvmBound = '1';
                el.addEventListener('change', () => loadJvmAdvisor(true));
            }
        });
        const x3d = document.getElementById('jvm-is-x3d');
        if (x3d && !x3d.dataset.jvmBound) {
            x3d.dataset.jvmBound = '1';
            x3d.addEventListener('change', () => loadJvmAdvisor(true));
        }
    }

    window.toggleJvmPanel = toggleJvmPanel;
    window.switchJvmSubpage = switchJvmSubpage;
    window.copyEncodedText = copyEncodedText;
    window.fillJvmAdvisorFormFromSettings = fillJvmAdvisorFormFromSettings;
    window.loadJvmAdvisor = loadJvmAdvisor;
    window.setupJvmAdvisorEvents = setupJvmAdvisorEvents;
})();
