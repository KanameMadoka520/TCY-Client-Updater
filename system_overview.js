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
        if (systemGrid) systemGrid.innerHTML = '<div class="system-overview-empty" style="grid-column:1 / -1;">正在读取机器概况…</div>';
        if (clientGrid) clientGrid.innerHTML = '<div class="system-overview-empty" style="grid-column:1 / -1;">正在读取客户端概况…</div>';
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
            if (adviceEl) adviceEl.innerHTML = '<div class="system-overview-empty">建议面板暂时不可用。</div>';
        } finally {
            systemOverviewLoading = false;
            setSystemOverviewBusy(false);
        }
    }

    window.initSystemOverview = initSystemOverview;
})();
