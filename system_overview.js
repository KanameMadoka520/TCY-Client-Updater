(function () {
    let systemOverviewLoadedOnce = false;
    let systemOverviewLoading = false;
    let systemOverviewCache = null;

    function esc(value) {
        if (typeof escapeHtml === 'function') return escapeHtml(String(value ?? ''));
        return String(value ?? '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function formatValue(value, unit = '') {
        if (value === null || value === undefined || value === '') return '未知';
        if (typeof value === 'number' && Number.isFinite(value)) {
            return `${value}${unit}`;
        }
        return `${value}${unit}`;
    }

    function levelMeta(level) {
        const map = {
            good: { text: '环境良好', className: 'level-good' },
            ok: { text: '可运行', className: 'level-ok' },
            tight: { text: '偏吃紧', className: 'level-tight' },
            critical: { text: '建议先优化', className: 'level-critical' }
        };
        return map[level] || map.ok;
    }

    function formatLauncherSettingSource(source) {
        const key = String(source || '').toLowerCase();
        if (key === 'version') return '版本专属配置';
        if (key === 'global') return '全局配置';
        return '';
    }

    function formatLauncherJavaMode(mode) {
        const key = String(mode || '').toUpperCase();
        const map = {
            AUTO: '自动匹配 Java',
            DETECTED: '已检测 Java',
            CUSTOM: '自定义 Java 路径',
            VERSION: '按 Java 大版本选择',
            DEFAULT: '启动器默认 Java',
        };
        return map[key] || '';
    }

    function buildLauncherOverviewNote(client) {
        const lines = [];
        const source = formatLauncherSettingSource(client?.launcher_setting_source);
        const javaMode = formatLauncherJavaMode(client?.launcher_java_mode);
        if (client?.launcher_profile) lines.push(`Profile：${client.launcher_profile}`);
        if (client?.launcher_selected_version) lines.push(`当前版本：${client.launcher_selected_version}`);
        if (source) lines.push(`配置来源：${source}`);
        if (javaMode) lines.push(`Java 模式：${javaMode}`);
        if (client?.launcher_config_path) lines.push(`配置文件：${client.launcher_config_path}`);
        return lines.join(' · ');
    }

    function renderLauncherRuntimeDetail(client) {
        const target = document.getElementById('systemoverview-launcher-detail');
        if (!target) return;

        const hasAnyDetail = !!(
            client?.launcher_name ||
            client?.launcher_java_path ||
            client?.launcher_profile_path ||
            client?.launcher_jvm_args ||
            client?.launcher_config_path
        );

        if (!hasAnyDetail) {
            target.innerHTML = '<div class="system-overview-empty">当前还没有读到可展示的启动器运行详情。</div>';
            return;
        }

        const source = formatLauncherSettingSource(client?.launcher_setting_source) || '来源未知';
        const javaMode = formatLauncherJavaMode(client?.launcher_java_mode) || '模式未知';
        const summaryLines = [
            client?.launcher_name ? `启动器：${client.launcher_name}` : '',
            client?.launcher_profile ? `Profile：${client.launcher_profile}` : '',
            client?.launcher_selected_version ? `当前版本：${client.launcher_selected_version}` : '',
            `配置来源：${source}`,
            `Java 模式：${javaMode}`
        ].filter(Boolean);

        const jvmArgsText = String(client?.launcher_jvm_args || '').trim();
        const jvmArgsHtml = jvmArgsText
            ? `<textarea readonly style="width:100%; min-height:92px; resize:vertical; padding:10px; border-radius:10px; border:1px solid rgba(59,130,246,0.18); background:rgba(59,130,246,0.05); color:var(--text-color); font-family:Consolas,monospace; font-size:12px; box-sizing:border-box;">${esc(jvmArgsText)}</textarea>`
            : '<div class="system-overview-empty" style="padding:12px 14px; text-align:left;">当前没有读到显式 JVM 参数串。这通常意味着该实例仍在使用自动内存、自动 Java，或者启动器没有把参数固定写入当前配置。</div>';

        target.innerHTML = `
            <div class="card" style="padding:14px; border:1px solid rgba(59,130,246,0.18); background:rgba(59,130,246,0.05); box-shadow:none;">
                <div style="display:flex; justify-content:space-between; gap:8px; align-items:center; margin-bottom:10px; flex-wrap:wrap;">
                    <strong>启动器运行详情</strong>
                    <span style="font-size:11px; opacity:0.66;">用于解释当前 Java 与 JVM 参数是怎么读出来的</span>
                </div>
                <div style="font-size:12px; line-height:1.8; opacity:0.84; margin-bottom:10px;">
                    ${summaryLines.map(line => `<div>${esc(line)}</div>`).join('')}
                </div>
                ${client?.launcher_config_path ? `<div style="font-size:12px; line-height:1.8; opacity:0.76; margin-bottom:6px;">启动器配置文件：<code>${esc(client.launcher_config_path)}</code></div>` : ''}
                ${client?.launcher_profile_path ? `<div style="font-size:12px; line-height:1.8; opacity:0.76; margin-bottom:6px;">当前参数文件：<code>${esc(client.launcher_profile_path)}</code></div>` : ''}
                ${client?.launcher_java_path ? `<div style="font-size:12px; line-height:1.8; opacity:0.76; margin-bottom:10px;">当前 Java 路径：<code>${esc(client.launcher_java_path)}</code></div>` : ''}
                <div style="font-size:12px; opacity:0.72; margin-bottom:6px;">当前 JVM 参数串</div>
                ${jvmArgsHtml}
            </div>
        `;
    }

    function renderMetricGrid(items) {
        const rows = Array.isArray(items) ? items : [];
        if (!rows.length) {
            return '<div class="system-overview-empty" style="grid-column:1 / -1;">暂无可显示的数据。</div>';
        }
        return rows.map(item => `
            <div class="system-overview-item">
                <div class="system-overview-label">${esc(item.label || '')}</div>
                <div class="system-overview-value">${esc(item.value || '未知')}</div>
                ${item.note ? `<div class="system-overview-note">${esc(item.note)}</div>` : ''}
            </div>
        `).join('');
    }

    function renderSystemAdvice(advice) {
        const target = document.getElementById('systemoverview-advice');
        if (!target) return;

        const meta = levelMeta(advice?.level);
        const items = Array.isArray(advice?.items) ? advice.items : [];
        const listHtml = items.length
            ? `<div class="system-overview-advice-list">${items.map(item => `
                    <div class="system-overview-advice-item severity-${esc(item.severity || 'info')}">${esc(item.text || '')}</div>
               `).join('')}</div>`
            : '<div class="system-overview-empty">当前没有额外建议。</div>';

        target.innerHTML = `
            <div style="display:flex; justify-content:space-between; gap:10px; align-items:flex-start; flex-wrap:wrap;">
                <div style="max-width:760px;">
                    <div style="display:flex; gap:8px; align-items:center; flex-wrap:wrap; margin-bottom:8px;">
                        <span class="system-overview-badge ${meta.className}">${meta.text}</span>
                    </div>
                    <div style="font-size:14px; line-height:1.9; opacity:0.88;">${esc(advice?.summary || '当前没有可展示的摘要。')}</div>
                </div>
            </div>
            ${listHtml}
        `;
    }

    function renderSystemOverview(payload) {
        const system = payload?.system || {};
        const client = payload?.client || {};
        const statusEl = document.getElementById('systemoverview-status');
        const systemGrid = document.getElementById('systemoverview-system-grid');
        const clientGrid = document.getElementById('systemoverview-client-grid');
        const launcherDetail = document.getElementById('systemoverview-launcher-detail');

        if (statusEl) {
            const meta = levelMeta(payload?.advice?.level);
            statusEl.innerHTML = `
                <span class="system-overview-badge ${meta.className}">${meta.text}</span>
                <span>最近采样时间：${esc(payload?.generated_at || '未知')}</span>
            `;
        }

        if (systemGrid) {
            const systemItems = [
                {
                    label: '操作系统',
                    value: [system.os_name, system.os_version].filter(Boolean).join(' ')
                },
                {
                    label: 'CPU',
                    value: system.cpu_name || '未知 CPU',
                    note: system.cpu_threads ? `逻辑线程数 ${system.cpu_threads}` : ''
                },
                {
                    label: '总内存',
                    value: formatValue(system.ram_total_gb, ' GB')
                },
                {
                    label: '当前可用内存',
                    value: formatValue(system.ram_available_gb, ' GB')
                },
                {
                    label: '磁盘剩余空间',
                    value: formatValue(system.disk_free_gb, ' GB'),
                    note: system.disk_total_gb ? `所在磁盘总容量 ${system.disk_total_gb} GB` : ''
                }
            ];
            systemGrid.innerHTML = renderMetricGrid(systemItems);
        }

        if (clientGrid) {
            const clientItems = [
                {
                    label: '当前目录',
                    value: client.game_root || '未知',
                    note: '系统概览与其他功能共用同一游戏根目录'
                },
                {
                    label: '本地版本',
                    value: client.local_version || '未知'
                },
                {
                    label: '客户端当前使用的 Java',
                    value: client.current_java_label || '暂时无法可靠判断',
                    note: client.current_java_note || ''
                },
                {
                    label: '启动器上下文',
                    value: client.launcher_name || '暂未识别到启动器',
                    note: buildLauncherOverviewNote(client) || '如果你正在使用 HMCL / PCL，这里会显示当前读取到的实例与 Java 选择上下文。'
                },
                {
                    label: 'Mods',
                    value: `${client.mods_enabled || 0} 启用 / ${client.mods_disabled || 0} 禁用`
                },
                {
                    label: '存档数量',
                    value: `${client.save_count || 0}`
                },
                {
                    label: '截图数量',
                    value: `${client.screenshot_count || 0}`
                }
            ];
            clientGrid.innerHTML = renderMetricGrid(clientItems);
        }

        if (launcherDetail) {
            renderLauncherRuntimeDetail(client);
        }

        renderSystemAdvice(payload?.advice || {});
    }

    function setSystemOverviewStatus(html) {
        const statusEl = document.getElementById('systemoverview-status');
        if (statusEl) statusEl.innerHTML = html;
    }

    function setSystemOverviewBusy(isBusy) {
        const btn = document.getElementById('systemoverview-refresh-btn');
        if (!btn) return;
        btn.disabled = !!isBusy;
        btn.textContent = isBusy ? '刷新中…' : '刷新概览';
    }

    async function initSystemOverview(forceRefresh = false) {
        if (systemOverviewLoading) return;

        if (systemOverviewLoadedOnce && !forceRefresh && systemOverviewCache) {
            renderSystemOverview(systemOverviewCache);
            return;
        }

        systemOverviewLoading = true;
        setSystemOverviewBusy(true);
        setSystemOverviewStatus(`
            <span class="system-overview-badge">采样中</span>
            <span>正在读取当前机器与客户端环境，请稍候…</span>
        `);

        const systemGrid = document.getElementById('systemoverview-system-grid');
        const clientGrid = document.getElementById('systemoverview-client-grid');
        const adviceEl = document.getElementById('systemoverview-advice');
        const launcherDetail = document.getElementById('systemoverview-launcher-detail');
        if (systemGrid) systemGrid.innerHTML = '<div class="system-overview-empty" style="grid-column:1 / -1;">正在读取机器概况…</div>';
        if (clientGrid) clientGrid.innerHTML = '<div class="system-overview-empty" style="grid-column:1 / -1;">正在读取客户端概况…</div>';
        if (launcherDetail) launcherDetail.innerHTML = '<div class="system-overview-empty">正在读取启动器运行详情…</div>';
        if (adviceEl) adviceEl.innerHTML = '<div class="system-overview-empty">正在生成建议…</div>';

        try {
            const res = await pywebview.api.get_system_overview?.();
            if (!res || !res.success) {
                throw new Error(res?.error || '获取系统概览失败');
            }
            systemOverviewCache = res.data || {};
            systemOverviewLoadedOnce = true;
            renderSystemOverview(systemOverviewCache);
        } catch (e) {
            const message = String(e && e.message ? e.message : e || '未知错误');
            setSystemOverviewStatus(`
                <span class="system-overview-badge level-critical">加载失败</span>
                <span>${esc(message)}</span>
            `);
            if (systemGrid) systemGrid.innerHTML = '<div class="system-overview-empty" style="grid-column:1 / -1;">机器概况加载失败，请稍后重试。</div>';
            if (clientGrid) clientGrid.innerHTML = '<div class="system-overview-empty" style="grid-column:1 / -1;">客户端概况加载失败，请稍后重试。</div>';
            if (launcherDetail) launcherDetail.innerHTML = '<div class="system-overview-empty">启动器运行详情暂时不可用。</div>';
            if (adviceEl) adviceEl.innerHTML = '<div class="system-overview-empty">建议面板暂时不可用。</div>';
        } finally {
            systemOverviewLoading = false;
            setSystemOverviewBusy(false);
        }
    }

    window.initSystemOverview = initSystemOverview;
})();
