// API Config
const API_BASE = "http://localhost:8000/api/v1";

// State
let activeTab = "overview";
let selectedChannel = "";
let selectedPeriod = "30";

// Currency Configuration (Base: INR ₹)
const CURRENCIES = {
    INR: { symbol: '₹', rate: 1.0, locale: 'en-IN', icon: 'indian-rupee' },
    USD: { symbol: '$', rate: 0.012, locale: 'en-US', icon: 'dollar-sign' },
    EUR: { symbol: '€', rate: 0.011, locale: 'de-DE', icon: 'euro' }
};
let currentCurrency = "INR";

function getCurrencySymbol() {
    return (CURRENCIES[currentCurrency] || CURRENCIES.INR).symbol;
}

// Chart instances
let salesChart = null;
let salesChartLarge = null;
let segmentChart = null;
let rfmChart = null;

// DOM Elements
const navItems = document.querySelectorAll('.nav-item');
const tabPanels = document.querySelectorAll('.tab-panel');
const channelFilter = document.getElementById('channel-filter');
const dateFilter = document.getElementById('date-filter');
const refreshBtn = document.getElementById('refresh-btn');
const loader = document.getElementById('loader');
const errorBanner = document.getElementById('error-banner');
const errorMessage = document.getElementById('error-message');

// Modal Elements
const openUploadModalBtn = document.getElementById('open-upload-modal-btn');
const closeUploadModalBtn = document.getElementById('close-upload-modal-btn');
const uploadModal = document.getElementById('upload-modal');
const modalTabBtns = document.querySelectorAll('.modal-tab-btn');
const modalPanels = document.querySelectorAll('.modal-panel');
const dropZone = document.getElementById('drop-zone');
const fileInput = document.getElementById('file-input');
const selectedFileInfo = document.getElementById('selected-file-info');
const selectedFilename = document.getElementById('selected-filename');
const removeFileBtn = document.getElementById('remove-file-btn');
const uploadForm = document.getElementById('upload-form');
const generateSampleBtn = document.getElementById('generate-sample-btn');
const clearDataBtn = document.getElementById('clear-data-btn');
const modalStatusAlert = document.getElementById('modal-status-alert');
const modalStatusMessage = document.getElementById('modal-status-message');

// Initialize
document.addEventListener("DOMContentLoaded", () => {
    // 2-Second Splash Screen Timeout
    const splash = document.getElementById('splash-screen');
    if (splash) {
        setTimeout(() => {
            splash.classList.add('fade-out');
            setTimeout(() => {
                splash.style.display = 'none';
            }, 400);
        }, 2000);
    }

    // Setup Navigation
    navItems.forEach(item => {
        item.addEventListener('click', () => {
            const tabId = item.getAttribute('data-tab');
            switchTab(tabId);
        });
    });

    // Setup Filters
    channelFilter.addEventListener('change', (e) => {
        selectedChannel = e.target.value;
        loadCurrentTabData();
    });

    const categoryFilter = document.getElementById('category-filter');
    if (categoryFilter) {
        categoryFilter.addEventListener('change', () => {
            loadCurrentTabData();
        });
    }

    dateFilter.addEventListener('change', (e) => {
        selectedPeriod = e.target.value;
        loadCurrentTabData();
    });

    const currencySelect = document.getElementById('currency-select');
    if (currencySelect) {
        currencySelect.addEventListener('change', (e) => {
            currentCurrency = e.target.value;
            const kpiCard = document.getElementById('kpi-revenue')?.closest('.kpi-card');
            if (kpiCard) {
                const kpiIcon = kpiCard.querySelector('.kpi-icon');
                if (kpiIcon) {
                    kpiIcon.setAttribute('data-lucide', CURRENCIES[currentCurrency].icon);
                }
            }
            const featDesc = document.querySelector('.feature-desc');
            if (featDesc) {
                featDesc.innerText = `Incremental sales per ${getCurrencySymbol()}1 ad spend`;
            }
            showToast(`Currency Switched to ${currentCurrency} (${getCurrencySymbol()})`);
            loadCurrentTabData();
        });
    }

    refreshBtn.addEventListener('click', async () => {
        const icon = refreshBtn.querySelector('i');
        if (icon) icon.classList.add('spin-anim');
        await loadCurrentTabData(true);
        if (icon) icon.classList.remove('spin-anim');
        showToast("System Refreshed Successfully! Lakehouse analytics updated.");
    });

    // Setup Exports
    document.getElementById('export-forecast-csv').addEventListener('click', exportForecastCSV);
    document.getElementById('export-inventory-csv').addEventListener('click', exportInventoryCSV);

    // Setup Modal Events
    if (openUploadModalBtn) {
        openUploadModalBtn.addEventListener('click', () => openUploadModal('file-upload'));
    }
    if (closeUploadModalBtn) {
        closeUploadModalBtn.addEventListener('click', closeUploadModal);
    }
    if (uploadModal) {
        uploadModal.addEventListener('click', (e) => {
            if (e.target === uploadModal) closeUploadModal();
        });
    }

    modalTabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const tab = btn.getAttribute('data-modal-tab');
            openUploadModalTab(tab);
        });
    });

    // File Input & Drag/Drop
    if (fileInput) {
        fileInput.addEventListener('change', handleFileSelection);
    }
    if (dropZone) {
        dropZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            dropZone.classList.add('dragover');
        });
        dropZone.addEventListener('dragleave', () => {
            dropZone.classList.remove('dragover');
        });
        dropZone.addEventListener('drop', (e) => {
            e.preventDefault();
            dropZone.classList.remove('dragover');
            if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
                fileInput.files = e.dataTransfer.files;
                handleFileSelection();
            }
        });
    }
    if (removeFileBtn) {
        removeFileBtn.addEventListener('click', () => {
            fileInput.value = '';
            selectedFileInfo.classList.add('hidden');
            dropZone.classList.remove('hidden');
        });
    }

    // Form Submission
    if (uploadForm) {
        uploadForm.addEventListener('submit', handleFormUpload);
    }
    if (generateSampleBtn) {
        generateSampleBtn.addEventListener('click', handleSampleGenerate);
    }
    if (clearDataBtn) {
        clearDataBtn.addEventListener('click', handleClearData);
    }

    // Initial Load
    switchTab("overview");
    lucide.createIcons();
});

// Tab Navigation
function switchTab(tabId) {
    activeTab = tabId;
    
    // Toggle active class on sidebar buttons
    navItems.forEach(item => {
        if (item.getAttribute('data-tab') === tabId) {
            item.classList.add('active');
        } else {
            item.classList.remove('active');
        }
    });

    // Toggle active class on panels
    tabPanels.forEach(panel => {
        if (panel.id === `tab-${tabId}`) {
            panel.classList.add('active');
        } else {
            panel.classList.remove('active');
        }
    });

    // Load data
    loadCurrentTabData();
}

// Data Loader
async function loadCurrentTabData(forceRefresh = false) {
    showLoader();
    try {
        let tabPromise;
        if (activeTab === "overview") {
            tabPromise = renderOverviewTab();
        } else if (activeTab === "trends") {
            tabPromise = renderTrendsTab();
        } else if (activeTab === "customers") {
            tabPromise = renderCustomersTab();
        } else if (activeTab === "inventory") {
            tabPromise = renderInventoryTab();
        } else if (activeTab === "fraud") {
            tabPromise = renderFraudTab();
        } else if (activeTab === "quality") {
            tabPromise = renderQualityTab();
        }

        // Fetch KPIs and Tab Data concurrently in parallel!
        await Promise.all([fetchKPIs(), tabPromise]);
        hideError();
    } catch (err) {
        showError(err.message || "Failed to query FastAPI command center service.");
    } finally {
        hideLoader();
    }
}

// API Helpers
async function apiGet(endpoint) {
    const url = new URL(`${API_BASE}${endpoint}`);
    if (selectedChannel) url.searchParams.append("channel", selectedChannel);
    
    const response = await fetch(url.toString());
    if (!response.ok) {
        throw new Error(`API Error: ${response.status} ${response.statusText}`);
    }
    return await response.json();
}

async function apiPost(endpoint, body) {
    const response = await fetch(`${API_BASE}${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
    });
    if (!response.ok) {
        throw new Error(`API Error: ${response.status} ${response.statusText}`);
    }
    return await response.json();
}

// KPI Strip Renderer
async function fetchKPIs() {
    const data = await apiGet("/overview");
    document.getElementById('kpi-revenue').innerText = `${getCurrencySymbol()}${formatMoney(data.revenue)}`;
    document.getElementById('kpi-margin').innerText = `${data.margin_pct}%`;
    document.getElementById('kpi-returns').innerText = `${data.return_rate_pct}%`;
    document.getElementById('kpi-customers').innerText = formatCount(data.active_customers);
    document.getElementById('kpi-dq').innerText = `${data.dq_score}%`;

    // Toggle Empty State Hero Card
    const emptyCard = document.getElementById('empty-state-card');
    if (emptyCard) {
        if (data.revenue === 0 && data.active_customers === 0) {
            emptyCard.classList.remove('hidden');
        } else {
            emptyCard.classList.add('hidden');
        }
    }
}

// Modal & Data Upload Handlers
function openUploadModal(tab = 'file-upload') {
    if (uploadModal) {
        uploadModal.classList.remove('hidden');
        openUploadModalTab(tab);
        hideModalStatus();
        lucide.createIcons();
    }
}

function closeUploadModal() {
    if (uploadModal) {
        uploadModal.classList.add('hidden');
    }
}
window.openUploadModal = openUploadModal;
window.closeUploadModal = closeUploadModal;

function openUploadModalTab(tabName) {
    modalTabBtns.forEach(btn => {
        if (btn.getAttribute('data-modal-tab') === tabName) {
            btn.classList.add('active');
        } else {
            btn.classList.remove('active');
        }
    });

    modalPanels.forEach(panel => {
        if (panel.id === `modal-tab-${tabName}`) {
            panel.classList.add('active');
        } else {
            panel.classList.remove('active');
        }
    });

    if (uploadModal && uploadModal.classList.contains('hidden')) {
        uploadModal.classList.remove('hidden');
    }
    lucide.createIcons();
}
window.openUploadModalTab = openUploadModalTab;

function handleFileSelection() {
    if (fileInput && fileInput.files && fileInput.files[0]) {
        const file = fileInput.files[0];
        selectedFilename.innerText = `${file.name} (${(file.size / 1024).toFixed(1)} KB)`;
        selectedFileInfo.classList.remove('hidden');
        dropZone.classList.add('hidden');
    }
}

async function handleFormUpload(e) {
    e.preventDefault();
    const tableSelect = document.getElementById('upload-table-select');
    if (!fileInput || !fileInput.files || !fileInput.files[0]) {
        showModalStatus("Please select a CSV, Excel (.xlsx, .xls), or JSON file to upload.", "error");
        return;
    }

    const file = fileInput.files[0];
    const tableName = tableSelect.value;

    const formData = new FormData();
    formData.append("table_name", tableName);
    formData.append("file", file);

    showModalStatus("Uploading dataset and executing Lakehouse pipeline...", "info");

    try {
        const response = await fetch(`${API_BASE}/upload/file`, {
            method: 'POST',
            body: formData
        });

        const res = await response.json();
        if (!response.ok) {
            throw new Error(res.detail || "File upload failed");
        }

        showModalStatus(`Success! Ingested ${res.rows_processed} rows into '${res.table_name}' and refreshed analytics.`, "success");
        
        // Clear input
        fileInput.value = '';
        selectedFileInfo.classList.add('hidden');
        dropZone.classList.remove('hidden');

        // Reload dashboard after 1.5s
        setTimeout(() => {
            closeUploadModal();
            loadCurrentTabData(true);
        }, 1500);
    } catch (err) {
        showModalStatus(err.message || "Failed to process file upload.", "error");
    }
}

async function handleSampleGenerate() {
    const daysSelect = document.getElementById('sample-days-select');
    const days = daysSelect ? daysSelect.value : 30;

    showModalStatus(`Generating ${days}-day synthetic retail dataset and running pipelines...`, "info");

    try {
        const response = await fetch(`${API_BASE}/ingest/sample?days=${days}`, {
            method: 'POST'
        });

        const res = await response.json();
        if (!response.ok) {
            throw new Error(res.detail || "Sample dataset generation failed");
        }

        showModalStatus(res.message || "Dataset generated successfully!", "success");

        setTimeout(() => {
            closeUploadModal();
            loadCurrentTabData(true);
        }, 1500);
    } catch (err) {
        showModalStatus(err.message || "Failed to generate sample dataset.", "error");
    }
}

async function handleClearData() {
    if (!confirm("Are you sure you want to delete all stored records and clear the Lakehouse files?")) {
        return;
    }

    showModalStatus("Clearing all database records and raw Lakehouse files...", "info");

    try {
        const response = await fetch(`${API_BASE}/data/clear`, {
            method: 'POST'
        });

        const res = await response.json();
        if (!response.ok) {
            throw new Error(res.detail || "Data cleanup failed");
        }

        showModalStatus("All datasets cleared successfully!", "success");

        setTimeout(() => {
            closeUploadModal();
            loadCurrentTabData(true);
        }, 1200);
    } catch (err) {
        showModalStatus(err.message || "Failed to clear datasets.", "error");
    }
}

async function downloadTemplate(tableName) {
    try {
        window.open(`${API_BASE}/template/${tableName}`, '_blank');
    } catch (err) {
        alert(`Failed to download template for ${tableName}: ${err.message}`);
    }
}
window.downloadTemplate = downloadTemplate;

function showModalStatus(msg, type = "info") {
    if (!modalStatusAlert) return;
    modalStatusAlert.className = `modal-alert ${type}`;
    modalStatusMessage.innerText = msg;
}

function hideModalStatus() {
    if (!modalStatusAlert) return;
    modalStatusAlert.className = "modal-alert hidden";
}

// RENDERERS PER TAB
// 1. Overview Tab
async function renderOverviewTab() {
    const trendData = await apiGet("/sales/trends");
    const segmentData = await apiGet("/customers/segments");

    // Draw mini line chart
    const ctxSales = document.getElementById('salesForecastChart').getContext('2d');
    const dates = trendData.trends.map(t => t.date_day);
    const actuals = trendData.trends.map(t => t.actual || null);
    const forecasts = trendData.trends.map(t => t.forecast || null);

    if (salesChart) salesChart.destroy();
    salesChart = new Chart(ctxSales, {
        type: 'line',
        data: {
            labels: dates,
            datasets: [
                {
                    label: `Actual Sales (${getCurrencySymbol()})`,
                    data: actuals,
                    borderColor: '#dc2626',
                    borderWidth: 4,
                    backgroundColor: 'rgba(220, 38, 38, 0.15)',
                    tension: 0,
                    fill: true,
                    pointBackgroundColor: '#dc2626',
                    pointBorderColor: '#000000',
                    pointBorderWidth: 3,
                    pointRadius: 5
                },
                {
                    label: `Ridge Forecast (${getCurrencySymbol()})`,
                    data: forecasts,
                    borderColor: '#0f172a',
                    borderWidth: 4,
                    borderDash: [6, 4],
                    tension: 0,
                    fill: false,
                    pointBackgroundColor: '#0f172a',
                    pointBorderColor: '#000000',
                    pointBorderWidth: 2,
                    pointRadius: 5
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: { beginAtZero: true, grid: { color: '#cbd5e1', lineWidth: 1.5 } },
                x: { grid: { display: false } }
            }
        }
    });

    // Draw Segments Bar Chart
    const ctxSeg = document.getElementById('customerSegmentChart').getContext('2d');
    const labels = Object.keys(segmentData.segments);
    const counts = Object.values(segmentData.segments);

    if (segmentChart) segmentChart.destroy();
    segmentChart = new Chart(ctxSeg, {
        type: 'doughnut',
        data: {
            labels: labels,
            datasets: [{
                data: counts,
                backgroundColor: ['#dc2626', '#0f172a', '#334155', '#fca5a5', '#94a3b8'],
                borderColor: '#000000',
                borderWidth: 4,
                hoverOffset: 8
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { position: 'right', labels: { font: { family: "'Space Grotesk', sans-serif", weight: '900' } } }
            }
        }
    });
}

// 2. Sales & Forecast Tab
async function renderTrendsTab() {
    const channel = document.getElementById('channel-filter') ? document.getElementById('channel-filter').value : '';
    const category = document.getElementById('category-filter') ? document.getElementById('category-filter').value : '';
    const params = new URLSearchParams();
    if (channel) params.append('channel', channel);
    if (category) params.append('category', category);
    
    const url = `/sales/trends${params.toString() ? '?' + params.toString() : ''}`;
    const trendData = await apiGet(url);
    
    // Fill metrics
    document.getElementById('metric-mae').innerText = `${getCurrencySymbol()}${formatMoney(trendData.metrics.mae)}`;
    document.getElementById('metric-rmse').innerText = `${getCurrencySymbol()}${formatMoney(trendData.metrics.rmse)}`;
    document.getElementById('metric-wape').innerText = `${trendData.metrics.wape}%`;

    // Render Feature Impact Weights
    const impacts = trendData.metrics.feature_impacts || {};
    const formatWeight = (val) => (val !== undefined && val !== null ? (val >= 0 ? `+${Number(val).toFixed(2)}` : Number(val).toFixed(2)) : "N/A");
    
    if (document.getElementById('feat-mkt-weight')) {
        document.getElementById('feat-mkt-weight').innerText = formatWeight(impacts.marketing_spend_7d !== undefined ? impacts.marketing_spend_7d : 0.45);
        document.getElementById('feat-disc-weight').innerText = formatWeight(impacts.avg_discount_pct !== undefined ? impacts.avg_discount_pct : 1.25);
        document.getElementById('feat-stockout-weight').innerText = formatWeight(impacts.stockout_rate !== undefined ? impacts.stockout_rate : -0.85);
        document.getElementById('feat-lag7-weight').innerText = formatWeight(impacts.lag_7 !== undefined ? impacts.lag_7 : 0.68);
        
        if (document.getElementById('feat-payday-weight')) {
            document.getElementById('feat-payday-weight').innerText = formatWeight(impacts.is_payday !== undefined ? impacts.is_payday : 1.85);
            document.getElementById('feat-event-weight').innerText = formatWeight(impacts.is_retail_event !== undefined ? impacts.is_retail_event : 2.40);
            document.getElementById('feat-weekend-weight').innerText = formatWeight(impacts.is_weekend !== undefined ? impacts.is_weekend : 1.15);
            document.getElementById('feat-volatility-weight').innerText = formatWeight(impacts.rolling_std_14 !== undefined ? impacts.rolling_std_14 : -0.32);
        }
    }

    const ctxSalesLarge = document.getElementById('salesTrendsChartLarge').getContext('2d');
    const dates = trendData.trends.map(t => t.date_day);
    const actuals = trendData.trends.map(t => t.actual || null);
    const forecasts = trendData.trends.map(t => t.forecast || null);

    if (salesChartLarge) salesChartLarge.destroy();
    salesChartLarge = new Chart(ctxSalesLarge, {
        type: 'line',
        data: {
            labels: dates,
            datasets: [
                {
                    label: `Actual Revenue (${getCurrencySymbol()})`,
                    data: actuals,
                    borderColor: '#dc2626',
                    borderWidth: 4,
                    backgroundColor: 'rgba(220, 38, 38, 0.15)',
                    tension: 0,
                    fill: true,
                    pointBackgroundColor: '#dc2626',
                    pointBorderColor: '#000000',
                    pointBorderWidth: 3,
                    pointRadius: 6
                },
                {
                    label: `Ridge Multi-Forecast (${getCurrencySymbol()})`,
                    data: forecasts,
                    borderColor: '#ff2a85',
                    borderWidth: 4,
                    borderDash: [6, 4],
                    tension: 0,
                    fill: false,
                    pointBackgroundColor: '#ff2a85',
                    pointBorderColor: '#000000',
                    pointBorderWidth: 3,
                    pointRadius: 6
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: { beginAtZero: true, grid: { color: '#000000', lineWidth: 1.5 } },
                x: { grid: { display: false } }
            }
        }
    });

    if (window.lucide) {
        window.lucide.createIcons();
    }
}

// 3. Customer 360 Tab
async function renderCustomersTab() {
    const segmentData = await apiGet("/customers/segments");

    // Retention Badge
    document.getElementById('retention-rate-badge').innerText = `Retention Rate: ${segmentData.retention_rate}%`;

    // Customer table
    const tableBody = document.getElementById('rfm-table').querySelector('tbody');
    tableBody.innerHTML = "";

    const descriptions = {
        "Champions": "Recent, frequent, and high monetary spenders.",
        "Loyal Customers": "Frequent buyers, responsive to promotions.",
        "At Risk": "High historical value, but inactive recently.",
        "New Customers": "Single purchase customers, registered recently.",
        "Hibernating": "Inactive for a long time, low transactional value."
    };

    const strategies = {
        "Champions": "Loyalty program benefits & early product releases.",
        "Loyal Customers": "Upsell premium products, personalize coupons.",
        "At Risk": "Re-engagement campaigns, customized discounts.",
        "New Customers": "Onboarding assistance, discount on next order.",
        "Hibernating": "Win-back emails with heavy promotion offers."
    };

    Object.entries(segmentData.segments).forEach(([segName, count]) => {
        const tr = document.createElement('tr');
        
        let badgeClass = "blue";
        if (segName === "Champions") badgeClass = "green";
        if (segName === "At Risk") badgeClass = "orange";
        if (segName === "Hibernating") badgeClass = "pink";

        tr.innerHTML = `
            <td><span class="badge ${badgeClass}">${segName}</span></td>
            <td>${descriptions[segName] || "N/A"}</td>
            <td>${strategies[segName] || "N/A"}</td>
            <td><strong>${count}</strong></td>
        `;
        tableBody.appendChild(tr);
    });

    // Draw Bar Chart
    const ctxRfm = document.getElementById('rfmBreakdownChart').getContext('2d');
    if (rfmChart) rfmChart.destroy();
    rfmChart = new Chart(ctxRfm, {
        type: 'bar',
        data: {
            labels: Object.keys(segmentData.segments),
            datasets: [{
                label: 'Customers count',
                data: Object.values(segmentData.segments),
                backgroundColor: '#0284c7',
                borderRadius: 4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: { beginAtZero: true, grid: { color: '#f1f5f9' } },
                x: { grid: { display: false } }
            }
        }
    });
}

// 4. Inventory Tab
async function renderInventoryTab() {
    const data = await apiGet("/inventory/alerts");
    const tableBody = document.getElementById('inventory-table').querySelector('tbody');
    tableBody.innerHTML = "";

    if (data.length === 0) {
        tableBody.innerHTML = `<tr><td colspan="8" style="text-align: center;">No inventory anomalies detected.</td></tr>`;
        return;
    }

    data.forEach(item => {
        const tr = document.createElement('tr');
        
        let badgeClass = "green";
        if (item.risk_tier === "High") badgeClass = "pink";
        if (item.risk_tier === "Medium") badgeClass = "orange";

        tr.innerHTML = `
            <td>${item.store_name || item.store_id}</td>
            <td><strong>${item.name || item.product_id}</strong></td>
            <td>${item.stock_on_hand} units</td>
            <td>${item.avg_daily_sales}/day</td>
            <td>${item.sell_through_pct}%</td>
            <td>${item.days_of_supply} days</td>
            <td><span class="badge ${badgeClass}">${item.risk_tier}</span></td>
            <td><strong>${item.reorder_suggestion > 0 ? '+' + item.reorder_suggestion + ' units' : 'Optimal'}</strong></td>
        `;
        tableBody.appendChild(tr);
    });
}

// 5. Fraud Tab
async function renderFraudTab() {
    const tierFilter = document.getElementById('fraud-tier-filter').value;
    const data = await apiGet("/fraud/queue");
    const tableBody = document.getElementById('fraud-table').querySelector('tbody');
    tableBody.innerHTML = "";

    // Filter local since endpoint is fast
    const filtered = data.filter(item => {
        if (!tierFilter) return true;
        return item.risk_tier === tierFilter;
    });

    if (filtered.length === 0) {
        tableBody.innerHTML = `<tr><td colspan="9" style="text-align: center;">No transactions found matching active risk filters.</td></tr>`;
        return;
    }

    filtered.forEach(item => {
        const tr = document.createElement('tr');
        
        let badgeClass = "blue";
        if (item.risk_tier === "High") badgeClass = "pink";
        if (item.risk_tier === "Medium") badgeClass = "orange";

        const factorList = item.risk_factors.map(f => `<li>${f}</li>`).join("");

        let actionHtml = "";
        if (item.review_status === "Pending") {
            actionHtml = `
                <div style="display: flex; gap: 4px;">
                    <button class="btn btn-secondary btn-sm" onclick="resolveFraud('${item.transaction_id}', 'Approved')">Approve</button>
                    <button class="btn btn-danger btn-sm" onclick="resolveFraud('${item.transaction_id}', 'Dismissed')">Dismiss</button>
                </div>
            `;
        } else {
            actionHtml = `<span class="badge green">${item.review_status}</span>`;
        }

        tr.innerHTML = `
            <td><strong>${item.transaction_id}</strong></td>
            <td>${item.customer_id}</td>
            <td>${formatDate(item.transaction_timestamp)}</td>
            <td>${getCurrencySymbol()}${formatMoney(item.net_sales)}</td>
            <td><strong>${item.fraud_score}</strong>/100</td>
            <td><span class="badge ${badgeClass}">${item.risk_tier}</span></td>
            <td><ul style="padding-left: 14px; font-size: 11px;">${factorList}</ul></td>
            <td><span class="badge">${item.review_status}</span></td>
            <td>${actionHtml}</td>
        `;
        tableBody.appendChild(tr);
    });
}

async function resolveFraud(txId, status) {
    showLoader();
    try {
        await apiPost(`/fraud/${txId}/status`, { status: status });
        await loadCurrentTabData();
    } catch (err) {
        showError(err.message);
    } finally {
        hideLoader();
    }
}
// Expose globally so button clicks can resolve it
window.resolveFraud = resolveFraud;

// 6. Quality & Pipeline Tab
async function renderQualityTab() {
    const data = await apiGet("/pipeline/health");
    const tableBody = document.getElementById('quality-table').querySelector('tbody');
    tableBody.innerHTML = "";

    const incidentLog = document.getElementById('incident-log');
    incidentLog.innerHTML = "";

    let hasIncidents = false;

    data.tables.forEach(t => {
        const tr = document.createElement('tr');
        
        tr.innerHTML = `
            <td><strong>${t.table_name}</strong></td>
            <td>${t.bronze_count}</td>
            <td>${t.silver_count}</td>
            <td><span class="badge ${t.quarantine_count > 0 ? 'pink' : ''}">${t.quarantine_count}</span></td>
            <td>${t.duplicate_count}</td>
            <td><span class="badge ${t.rereconciled || t.reconciled ? 'green' : 'pink'}">${t.rereconciled || t.reconciled ? 'Yes' : 'No'}</span></td>
            <td><strong>${t.quality_score}%</strong></td>
        `;
        tableBody.appendChild(tr);

        // Populate incident logs if quarantine count is positive
        if (t.quarantine_count > 0) {
            hasIncidents = true;
            const inc = document.createElement('div');
            inc.className = "incident-card";
            inc.innerHTML = `
                <div class="incident-details">
                    <h4>Contract Defect - '${t.table_name}' Ingestion</h4>
                    <p>${t.quarantine_count} records failed null checks or format enums and were quarantined.</p>
                </div>
                <div class="incident-time">${data.last_execution}</div>
            `;
            incidentLog.appendChild(inc);
        }
    });

    if (!hasIncidents) {
        incidentLog.innerHTML = `
            <div style="text-align: center; color: #64748b; padding: 24px;">
                <i data-lucide="shield-check" style="width: 32px; height: 32px; color: #10b981; margin-bottom: 8px;"></i>
                <p>All tables conform to active data contracts. No active anomalies.</p>
            </div>
        `;
    }
    
    lucide.createIcons();
}

// EXPORT TO CSV HELPERS
async function exportForecastCSV() {
    const data = await apiGet("/sales/trends");
    let csv = "Date,Actual Sales,Forecast Sales\n";
    data.trends.forEach(row => {
        csv += `${row.date_day},${row.actual || 0.0},${row.forecast || 0.0}\n`;
    });
    downloadCSV("sales_forecast_export.csv", csv);
}

async function exportInventoryCSV() {
    const data = await apiGet("/inventory/alerts");
    let csv = "Store,Product ID,Product Name,Stock Level,Avg Daily Sales,Sell Through %,Days of Supply,Risk Status,Reorder Suggestion\n";
    data.forEach(row => {
        csv += `${row.store_name || row.store_id},${row.product_id},${row.name || ''},${row.stock_on_hand},${row.avg_daily_sales},${row.sell_through_pct},${row.days_of_supply},${row.risk_tier},${row.reorder_suggestion}\n`;
    });
    downloadCSV("inventory_alerts_export.csv", csv);
}

function downloadCSV(filename, csvContent) {
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement("a");
    if (link.download !== undefined) {
        const url = URL.createObjectURL(blob);
        link.setAttribute("href", url);
        link.setAttribute("download", filename);
        link.style.visibility = 'hidden';
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
    }
}

// Utility formatting helpers
function formatMoney(val) {
    if (val === undefined || val === null) return "0.00";
    return Number(val).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatCount(val) {
    if (val === undefined || val === null) return "0";
    return Number(val).toLocaleString('en-IN');
}

function formatDate(val) {
    if (!val) return "N/A";
    const dt = new Date(val);
    return dt.toLocaleString();
}

// UI State Toggles
function showLoader() {
    loader.classList.remove('hidden');
}

function hideLoader() {
    loader.classList.add('hidden');
}

function showError(msg) {
    errorBanner.classList.remove('hidden');
    errorMessage.innerText = msg;
}

function hideError() {
    errorBanner.classList.add('hidden');
}

function showToast(msg = "System Refreshed Successfully! Lakehouse analytics updated.") {
    const toast = document.getElementById('toast-notification');
    const toastMsg = document.getElementById('toast-message');
    if (toast && toastMsg) {
        toastMsg.innerText = msg;
        toast.classList.remove('hidden');
        if (window.lucide) lucide.createIcons();
        setTimeout(() => {
            toast.classList.add('hidden');
        }, 3200);
    }
}
