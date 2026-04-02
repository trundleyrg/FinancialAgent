/**
 * Financial Report Analysis System - Main Application
 */

// API Base URL
const API_BASE = '/api';

// State
const state = {
    currentTab: 'parser',
    dbType: 'duckdb',
    selectedCompany: '',
    selectedYear: null,
    selectedPeriod: '',
    companies: [],
    years: [],
    periods: [],
    lastResult: null
};

// DOM Elements
const elements = {};

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    initElements();
    initEventListeners();
    loadQueryOptions();
});

function initElements() {
    // Tabs
    elements.parserTab = document.getElementById('parser-tab');
    elements.queryTab = document.getElementById('query-tab');
    elements.parserContent = document.getElementById('parser-content');
    elements.queryContent = document.getElementById('query-content');

    // Parser
    elements.dbTypeSelect = document.getElementById('db-type');
    elements.fileInput = document.getElementById('file-input');
    elements.uploadArea = document.getElementById('upload-area');
    elements.processBtn = document.getElementById('process-btn');
    elements.parserResult = document.getElementById('parser-result');
    elements.companyInfo = document.getElementById('company-info');
    elements.tablesList = document.getElementById('tables-list');
    elements.downloadLinks = document.getElementById('download-links');
    elements.parserLoading = document.getElementById('parser-loading');

    // Query
    elements.queryDbType = document.getElementById('query-db-type');
    elements.companySelect = document.getElementById('company-select');
    elements.yearSelect = document.getElementById('year-select');
    elements.periodSelect = document.getElementById('period-select');
    elements.queryBtn = document.getElementById('query-btn');
    elements.queryResult = document.getElementById('query-result');
    elements.queryLoading = document.getElementById('query-loading');
}

function initEventListeners() {
    // Tab switching
    elements.parserTab?.addEventListener('click', () => switchTab('parser'));
    elements.queryTab?.addEventListener('click', () => switchTab('query'));

    // File upload
    elements.uploadArea?.addEventListener('click', () => elements.fileInput?.click());
    elements.uploadArea?.addEventListener('dragover', handleDragOver);
    elements.uploadArea?.addEventListener('dragleave', handleDragLeave);
    elements.uploadArea?.addEventListener('drop', handleDrop);
    elements.fileInput?.addEventListener('change', handleFileSelect);

    // Process button
    elements.processBtn?.addEventListener('click', processPdf);

    // Query controls
    elements.dbTypeSelect?.addEventListener('change', (e) => state.dbType = e.target.value);
    elements.queryDbType?.addEventListener('change', (e) => {
        state.dbType = e.target.value;
        loadQueryOptions();
    });
    elements.companySelect?.addEventListener('change', handleCompanyChange);
    elements.yearSelect?.addEventListener('change', handleYearChange);
    elements.queryBtn?.addEventListener('click', queryData);
}

// Tab Management
function switchTab(tabName) {
    state.currentTab = tabName;

    document.querySelectorAll('.nav-tab').forEach(tab => tab.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));

    if (tabName === 'parser') {
        elements.parserTab?.classList.add('active');
        elements.parserContent?.classList.add('active');
    } else {
        elements.queryTab?.classList.add('active');
        elements.queryContent?.classList.add('active');
    }
}

// File Upload Handlers
function handleDragOver(e) {
    e.preventDefault();
    e.stopPropagation();
    elements.uploadArea?.classList.add('dragover');
}

function handleDragLeave(e) {
    e.preventDefault();
    e.stopPropagation();
    elements.uploadArea?.classList.remove('dragover');
}

function handleDrop(e) {
    e.preventDefault();
    e.stopPropagation();
    elements.uploadArea?.classList.remove('dragover');

    const files = e.dataTransfer?.files;
    if (files && files.length > 0) {
        handleFile(files[0]);
    }
}

function handleFileSelect(e) {
    const files = e.target.files;
    if (files && files.length > 0) {
        handleFile(files[0]);
    }
}

function handleFile(file) {
    if (!file.name.toLowerCase().endsWith('.pdf')) {
        showAlert('parser-result', 'error', '只支持PDF文件');
        return;
    }

    elements.uploadArea.querySelector('.file-upload-text').textContent = `已选择: ${file.name}`;
    elements.uploadArea.dataset.file = 'selected';
}

async function processPdf() {
    const file = elements.fileInput?.files[0];

    if (!file) {
        const uploadAreaHasFile = elements.uploadArea?.dataset.file === 'selected';
        if (!uploadAreaHasFile) {
            showAlert('parser-result', 'error', '请先选择PDF文件');
            return;
        }
    }

    showLoading('parser', true);
    hideAlert('parser-result');

    const formData = new FormData();
    formData.append('file', file || elements.fileInput.files[0]);
    formData.append('db_type', state.dbType);

    try {
        const response = await fetch(`${API_BASE}/pdf/upload`, {
            method: 'POST',
            body: formData
        });

        const result = await response.json();

        if (!response.ok) {
            throw new Error(result.detail || '处理失败');
        }

        state.lastResult = result;
        displayParserResult(result);

    } catch (error) {
        showAlert('parser-result', 'error', error.message);
    } finally {
        showLoading('parser', false);
    }
}

function displayParserResult(result) {
    // Show success message
    showAlert('parser-result', 'success', result.message);

    // Display company info
    if (result.company_info) {
        const info = result.company_info;
        elements.companyInfo.innerHTML = `
            <div class="info-grid">
                <div class="info-item">
                    <div class="info-label">公司名称</div>
                    <div class="info-value">${info.company_name || '-'}</div>
                </div>
                <div class="info-item">
                    <div class="info-label">公司简称</div>
                    <div class="info-value">${info.company_short_name || '-'}</div>
                </div>
                <div class="info-item">
                    <div class="info-label">股票代码</div>
                    <div class="info-value">${info.stock_code || '-'}</div>
                </div>
                <div class="info-item">
                    <div class="info-label">报告年份</div>
                    <div class="info-value">${info.report_year || '-'}</div>
                </div>
                <div class="info-item">
                    <div class="info-label">报告期间</div>
                    <div class="info-value">${info.report_period || 'FY'}</div>
                </div>
                <div class="info-item">
                    <div class="info-label">提取表格数</div>
                    <div class="info-value">${result.tables?.length || 0}</div>
                </div>
            </div>
        `;
    }

    // Display tables list
    if (result.tables && result.tables.length > 0) {
        let tablesHtml = `
            <table class="data-table">
                <thead>
                    <tr>
                        <th>表格名称</th>
                        <th>行数</th>
                        <th>列数</th>
                        <th>页码</th>
                        <th>单位</th>
                    </tr>
                </thead>
                <tbody>
        `;

        result.tables.forEach(table => {
            tablesHtml += `
                <tr>
                    <td>${table.table_name}</td>
                    <td>${table.row_count}</td>
                    <td>${table.col_count}</td>
                    <td>${table.page_range}</td>
                    <td>${table.unit || '-'}</td>
                </tr>
            `;
        });

        tablesHtml += '</tbody></table>';
        elements.tablesList.innerHTML = tablesHtml;
    } else {
        elements.tablesList.innerHTML = '<p class="text-secondary">未提取到表格</p>';
    }

    // Display download links
    if (result.download_urls && result.download_urls.length > 0) {
        let linksHtml = '<div class="download-links">';
        result.download_urls.forEach((url, index) => {
            const tableName = result.tables[index]?.table_name || `表格${index + 1}`;
            linksHtml += `
                <a href="${url}" class="download-link" download>
                    ⬇️ ${tableName}
                </a>
            `;
        });
        linksHtml += '</div>';
        elements.downloadLinks.innerHTML = linksHtml;
    } else {
        elements.downloadLinks.innerHTML = '';
    }
}

// Query Functions
async function loadQueryOptions() {
    try {
        const response = await fetch(`${API_BASE}/database/options?db_type=${state.dbType}`);
        const data = await response.json();

        state.companies = data.companies || [];
        state.years = data.years || [];

        populateCompanySelect();
        populateYearSelect();

    } catch (error) {
        console.error('Failed to load options:', error);
    }
}

function populateCompanySelect() {
    if (!elements.companySelect) return;

    let html = '<option value="">选择公司</option>';
    state.companies.forEach(company => {
        html += `<option value="${company.value}">${company.label}</option>`;
    });
    elements.companySelect.innerHTML = html;
}

function populateYearSelect() {
    if (!elements.yearSelect) return;

    let html = '<option value="">选择年份</option>';
    state.years.forEach(year => {
        html += `<option value="${year.value}">${year.label}</option>`;
    });
    elements.yearSelect.innerHTML = html;
}

async function handleCompanyChange(e) {
    state.selectedCompany = e.target.value;
    state.selectedPeriod = '';
    elements.periodSelect.innerHTML = '<option value="">选择报告周期</option>';

    if (state.selectedCompany && state.selectedYear) {
        await loadPeriods();
    }
}

async function handleYearChange(e) {
    state.selectedYear = e.target.value ? parseInt(e.target.value) : null;
    state.selectedPeriod = '';
    elements.periodSelect.innerHTML = '<option value="">选择报告周期</option>';

    if (state.selectedCompany && state.selectedYear) {
        await loadPeriods();
    }
}

async function loadPeriods() {
    try {
        const response = await fetch(
            `${API_BASE}/database/periods?stock_code=${state.selectedCompany}&year=${state.selectedYear}&db_type=${state.dbType}`
        );
        const data = await response.json();

        state.periods = data || [];

        let html = '<option value="">选择报告周期</option>';
        state.periods.forEach(period => {
            html += `<option value="${period.value}">${period.label}</option>`;
        });
        elements.periodSelect.innerHTML = html;

    } catch (error) {
        console.error('Failed to load periods:', error);
    }
}

async function queryData() {
    if (!state.selectedCompany || !state.selectedYear || !state.selectedPeriod) {
        showAlert('query-result', 'error', '请选择所有查询条件');
        return;
    }

    showLoading('query', true);
    hideAlert('query-result');

    try {
        const response = await fetch(
            `${API_BASE}/database/data?stock_code=${state.selectedCompany}&year=${state.selectedYear}&period=${state.selectedPeriod}&db_type=${state.dbType}`
        );

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || '查询失败');
        }

        const data = await response.json();
        displayQueryResult(data);

    } catch (error) {
        showAlert('query-result', 'error', error.message);
    } finally {
        showLoading('query', false);
    }
}

function displayQueryResult(data) {
    if (!data.report) {
        showAlert('query-result', 'warning', '未找到财务数据');
        return;
    }

    const report = data.report;
    let html = `
        <div class="card">
            <h3 class="card-header">财务报告信息</h3>
            <div class="info-grid">
                <div class="info-item">
                    <div class="info-label">公司名称</div>
                    <div class="info-value">${report.company_name}</div>
                </div>
                <div class="info-item">
                    <div class="info-label">股票代码</div>
                    <div class="info-value">${report.stock_code}</div>
                </div>
                <div class="info-item">
                    <div class="info-label">报告年份</div>
                    <div class="info-value">${report.report_year}</div>
                </div>
                <div class="info-item">
                    <div class="info-label">报告周期</div>
                    <div class="info-value">${report.report_period}</div>
                </div>
            </div>
        </div>
    `;

    // Balance Sheet
    if (data.balance_sheet) {
        html += displayFinancialTable('合并资产负债表', data.balance_sheet);
    }
    if (data.income_statement) {
        html += displayFinancialTable('合并利润表', data.income_statement);
    }
    if (data.cash_flow) {
        html += displayFinancialTable('合并现金流量表', data.cash_flow);
    }

    elements.queryResult.innerHTML = html;
}

function displayFinancialTable(title, data) {
    let html = `
        <div class="card section">
            <h3 class="card-header">${title}</h3>
            <div class="table-container">
                <table class="data-table financial-table">
                    <tbody>
    `;

    for (const [key, value] of Object.entries(data)) {
        if (value === null || value === undefined) continue;

        const label = formatFieldName(key);
        const displayValue = typeof value === 'number' ? formatNumber(value) : value;

        html += `
            <tr>
                <td>${label}</td>
                <td class="amount ${value >= 0 ? 'positive' : 'negative'}">${displayValue}</td>
            </tr>
        `;
    }

    html += '</tbody></table></div></div>';
    return html;
}

function formatFieldName(fieldName) {
    // Convert snake_case to Chinese
    const mappings = {
        'monetary_funds': '货币资金',
        'total_current_assets': '流动资产合计',
        'total_assets': '资产总计',
        'short_term_borrowings': '短期借款',
        'total_current_liabilities': '流动负债合计',
        'total_liabilities': '负债合计',
        'total_owners_equity': '所有者权益合计',
        'operating_revenue': '营业收入',
        'operating_costs': '营业成本',
        'net_profit': '净利润',
        'total_profit': '利润总额',
        'net_cash_from_operations': '经营活动现金流量净额',
        'net_cash_from_investing': '投资活动现金流量净额',
        'net_cash_from_financing': '筹资活动现金流量净额',
        'basic_eps': '基本每股收益',
        'diluted_eps': '稀释每股收益'
    };

    return mappings[fieldName] || fieldName.replace(/_/g, ' ');
}

function formatNumber(num) {
    if (Math.abs(num) >= 100000000) {
        return (num / 100000000).toFixed(2) + ' 亿';
    } else if (Math.abs(num) >= 10000) {
        return (num / 10000).toFixed(2) + ' 万';
    }
    return num.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

// UI Helpers
function showLoading(type, show) {
    if (type === 'parser') {
        elements.parserLoading.classList.toggle('active', show);
        elements.processBtn.disabled = show;
    } else {
        elements.queryLoading.classList.toggle('active', show);
        elements.queryBtn.disabled = show;
    }
}

function showAlert(elementId, type, message) {
    const element = document.getElementById(elementId);
    if (!element) return;

    element.innerHTML = `<div class="alert alert-${type}">${message}</div>`;
    element.style.display = 'block';
}

function hideAlert(elementId) {
    const element = document.getElementById(elementId);
    if (element) {
        element.innerHTML = '';
        element.style.display = 'none';
    }
}
