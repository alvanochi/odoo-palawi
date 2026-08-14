/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { loadBundle } from "@web/core/assets";
import { formatMonetary } from "@web/views/fields/formatters";
import { _t } from "@web/core/l10n/translation";
import {
    Component,
    onWillStart,
    onWillUnmount,
    useEffect,
    useRef,
    useState,
} from "@odoo/owl";

const PALETTE = [
    "#4C6FFF", "#8B5CF6", "#0EA5A5", "#EF4444", "#F59E0B",
    "#22C55E", "#3B82F6", "#EC4899", "#14B8A6", "#A855F7",
];

const MONTHS = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

const PERIODS = [
    { key: "today", label: "Today" },
    { key: "yesterday", label: "Yesterday" },
    { key: "this_week", label: "This Week" },
    { key: "this_month", label: "This Month" },
    { key: "last_month", label: "Last Month" },
    { key: "this_quarter", label: "This Quarter" },
    { key: "this_year", label: "This Year" },
];

function toDateString(date) {
    const year = date.getFullYear();
    const month = `${date.getMonth() + 1}`.padStart(2, "0");
    const day = `${date.getDate()}`.padStart(2, "0");
    return `${year}-${month}-${day}`;
}

function prettyDate(value) {
    if (!value) {
        return "";
    }
    const [year, month, day] = value.split("-").map(Number);
    return `${day} ${MONTHS[month - 1]} ${year}`;
}

export class PosPerformanceDashboard extends Component {
    static template = "pos_performance_dashboard.Dashboard";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.periods = PERIODS;

        const today = new Date();
        const yesterday = new Date();
        yesterday.setDate(yesterday.getDate() - 1);

        this.state = useState({
            loading: true,
            period: "today",
            dateFrom: toDateString(today),
            dateTo: toDateString(today),
            storeId: null,
            storeSearch: "",
            chartMode: "hourly",
            showPeriodMenu: false,
            showDateMenu: false,
            data: null,
        });

        this.charts = {};
        this.salesChartRef = useRef("salesChart");
        this.categoryChartRef = useRef("categoryChart");
        this.storeChartRef = useRef("storeChart");

        onWillStart(async () => {
            await loadBundle("web.chartjs_lib");
            await this.loadData();
        });

        useEffect(
            () => {
                this.renderCharts();
            },
            () => [this.state.data, this.state.chartMode]
        );

        onWillUnmount(() => this.destroyCharts());
    }

    // ------------------------------------------------------------------
    // Data
    // ------------------------------------------------------------------
    get configIds() {
        return this.state.storeId ? [this.state.storeId] : [];
    }

    async loadData() {
        this.state.loading = true;
        try {
            this.state.data = await this.orm.call(
                "pos.performance.dashboard",
                "get_dashboard_data",
                [this.state.dateFrom, this.state.dateTo, this.configIds]
            );
        } finally {
            this.state.loading = false;
        }
    }

    get data() {
        return this.state.data || {};
    }

    get kpi() {
        return this.data.kpi || {};
    }

    get store() {
        return this.data.store || null;
    }

    get sessionStock() {
        return this.data.session_stock || {};
    }

    get stores() {
        return this.data.stores || [];
    }

    get visibleStores() {
        const query = this.state.storeSearch.trim().toLowerCase();
        if (!query) {
            return this.stores;
        }
        return this.stores.filter(
            (store) =>
                store.name.toLowerCase().includes(query) ||
                (store.company || "").toLowerCase().includes(query)
        );
    }

    get topProducts() {
        return this.data.top_products || [];
    }

    get topCustomers() {
        return this.data.top_customers || [];
    }

    get cashiers() {
        return this.data.cashiers || [];
    }

    get paymentMethods() {
        return this.data.payment_methods || [];
    }

    get recentSessions() {
        return this.data.recent_sessions || [];
    }

    get outOfStock() {
        return this.data.out_of_stock || { count: 0, products: [] };
    }

    get periodLabel() {
        const found = PERIODS.find((p) => p.key === this.state.period);
        return found ? found.label : _t("Custom");
    }

    get dateLabel() {
        if (this.state.dateFrom === this.state.dateTo) {
            return prettyDate(this.state.dateFrom);
        }
        return `${prettyDate(this.state.dateFrom)} - ${prettyDate(
            this.state.dateTo
        )}`;
    }

    get salesChartTitle() {
        return this.state.chartMode === "hourly"
            ? _t("Hourly Sales")
            : _t("Daily Sales");
    }

    // ------------------------------------------------------------------
    // Formatting
    // ------------------------------------------------------------------
    formatCurrency(value) {
        return formatMonetary(value || 0, {
            currencyId: this.data.currency_id,
            digits: [false, 2],
        });
    }

    formatNumber(value) {
        return new Intl.NumberFormat().format(
            Math.round((value || 0) * 100) / 100
        );
    }

    formatSigned(value) {
        const rounded = Math.round((value || 0) * 10) / 10;
        return `${rounded > 0 ? "+" : ""}${rounded}%`;
    }

    barWidth(value) {
        return Math.max(0, Math.min(value || 0, 100));
    }

    growthClass(value) {
        if ((value || 0) > 0) {
            return "text-success";
        }
        return (value || 0) < 0 ? "text-danger" : "text-muted";
    }

    rankColor(index) {
        return PALETTE[index % PALETTE.length];
    }

    // ------------------------------------------------------------------
    // Filters & navigation
    // ------------------------------------------------------------------
    async setPeriod(period) {
        const today = new Date();
        let from = new Date(today);
        let to = new Date(today);
        switch (period) {
            case "today":
                break;
            case "yesterday":
                from.setDate(from.getDate() - 1);
                to = new Date(from);
                break;
            case "this_week": {
                const offset = (from.getDay() + 6) % 7; // week starts Monday
                from.setDate(from.getDate() - offset);
                break;
            }
            case "this_month":
                from = new Date(today.getFullYear(), today.getMonth(), 1);
                break;
            case "last_month":
                from = new Date(today.getFullYear(), today.getMonth() - 1, 1);
                to = new Date(today.getFullYear(), today.getMonth(), 0);
                break;
            case "this_quarter": {
                const quarterStart = Math.floor(today.getMonth() / 3) * 3;
                from = new Date(today.getFullYear(), quarterStart, 1);
                break;
            }
            case "this_year":
                from = new Date(today.getFullYear(), 0, 1);
                break;
        }
        this.state.period = period;
        this.state.dateFrom = toDateString(from);
        this.state.dateTo = toDateString(to);
        this.state.showPeriodMenu = false;
        this.state.chartMode =
            this.state.dateFrom === this.state.dateTo ? "hourly" : "daily";
        await this.loadData();
    }

    async onDateChange(field, ev) {
        if (!ev.target.value) {
            return;
        }
        this.state[field] = ev.target.value;
        this.state.period = "custom";
        this.state.chartMode =
            this.state.dateFrom === this.state.dateTo ? "hourly" : "daily";
        await this.loadData();
    }

    async selectStore(storeId) {
        this.state.storeId = storeId;
        await this.loadData();
    }

    async backToAllStores() {
        this.state.storeId = null;
        await this.loadData();
    }

    setChartMode(mode) {
        this.state.chartMode = mode;
    }

    togglePeriodMenu() {
        this.state.showPeriodMenu = !this.state.showPeriodMenu;
        this.state.showDateMenu = false;
    }

    toggleDateMenu() {
        this.state.showDateMenu = !this.state.showDateMenu;
        this.state.showPeriodMenu = false;
    }

    async onRefresh() {
        await this.loadData();
    }

    // ------------------------------------------------------------------
    // Drill-down
    // ------------------------------------------------------------------
    async openOrders(extraDomain = [], name = _t("POS Orders")) {
        const domain = await this.orm.call(
            "pos.performance.dashboard",
            "get_order_domain",
            [this.state.dateFrom, this.state.dateTo, this.configIds, extraDomain]
        );
        this.action.doAction({
            type: "ir.actions.act_window",
            name: name,
            res_model: "pos.order",
            views: [
                [false, "list"],
                [false, "form"],
            ],
            domain: domain,
            target: "current",
        });
    }

    openRecord(resModel, resId, name) {
        if (!resId) {
            return;
        }
        this.action.doAction({
            type: "ir.actions.act_window",
            name: name,
            res_model: resModel,
            res_id: resId,
            views: [[false, "form"]],
            target: "current",
        });
    }

    openOutOfStock() {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: _t("Out of Stock Products"),
            res_model: "product.product",
            views: [
                [false, "list"],
                [false, "form"],
            ],
            domain: [
                ["available_in_pos", "=", true],
                ["is_storable", "=", true],
                ["qty_available", "<=", 0],
            ],
            target: "current",
        });
    }

    openSessions() {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: _t("POS Sessions"),
            res_model: "pos.session",
            views: [
                [false, "list"],
                [false, "form"],
            ],
            domain: this.state.storeId
                ? [["config_id", "=", this.state.storeId]]
                : [],
            target: "current",
        });
    }

    // ------------------------------------------------------------------
    // Charts
    // ------------------------------------------------------------------
    destroyCharts() {
        for (const key of Object.keys(this.charts)) {
            if (this.charts[key]) {
                this.charts[key].destroy();
                delete this.charts[key];
            }
        }
    }

    renderCharts() {
        if (!this.state.data || typeof Chart === "undefined") {
            return;
        }
        this.destroyCharts();
        this.renderSalesChart();
        this.renderCategoryChart();
        this.renderStoreChart();
    }

    _moneyTicks() {
        return { callback: (value) => this.formatNumber(value) };
    }

    renderSalesChart() {
        const canvas = this.salesChartRef.el;
        if (!canvas) {
            return;
        }
        const hourly = this.state.chartMode === "hourly";
        const source = hourly ? this.data.sales_by_hour : this.data.sales_trend;
        if (!source) {
            return;
        }
        this.charts.sales = new Chart(canvas, {
            // Mixed chart: type wajib ada di level atas, dataset line
            // menimpanya lewat "type" masing-masing.
            type: "bar",
            data: {
                labels: source.labels,
                datasets: [
                    {
                        type: "bar",
                        label: _t("Revenue"),
                        data: source.sales,
                        backgroundColor: "#F5A623",
                        borderRadius: 4,
                        yAxisID: "y",
                        order: 2,
                    },
                    {
                        type: "line",
                        label: _t("Orders"),
                        data: source.orders,
                        borderColor: "#EF4444",
                        backgroundColor: "#EF4444",
                        pointRadius: 3,
                        tension: 0.3,
                        yAxisID: "y1",
                        order: 1,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: "index", intersect: false },
                plugins: { legend: { display: false } },
                scales: {
                    y: {
                        position: "left",
                        beginAtZero: true,
                        ticks: this._moneyTicks(),
                        grid: { color: "rgba(0,0,0,0.05)" },
                    },
                    y1: {
                        position: "right",
                        beginAtZero: true,
                        ticks: { precision: 0, color: "#EF4444" },
                        grid: { drawOnChartArea: false },
                    },
                    x: { grid: { display: false } },
                },
            },
        });
    }

    renderCategoryChart() {
        const canvas = this.categoryChartRef.el;
        const categories = this.data.top_categories || [];
        if (!canvas || !categories.length) {
            return;
        }
        this.charts.category = new Chart(canvas, {
            type: "doughnut",
            data: {
                labels: categories.map((c) => c.name),
                datasets: [
                    {
                        data: categories.map((c) => c.amount),
                        backgroundColor: categories.map((c, i) =>
                            this.rankColor(i)
                        ),
                        borderWidth: 0,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: "60%",
                plugins: { legend: { position: "bottom" } },
            },
        });
    }

    renderStoreChart() {
        const canvas = this.storeChartRef.el;
        const stores = this.stores;
        if (!canvas || !stores.length) {
            return;
        }
        this.charts.store = new Chart(canvas, {
            type: "bar",
            data: {
                labels: stores.map((s) => s.name),
                datasets: [
                    {
                        label: _t("Sales"),
                        data: stores.map((s) => s.sales),
                        backgroundColor: "#4C6FFF",
                        borderRadius: 4,
                    },
                    {
                        label: _t("Target"),
                        data: stores.map((s) => s.target),
                        backgroundColor: "rgba(148, 163, 184, 0.35)",
                        borderRadius: 4,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                indexAxis: "y",
                plugins: { legend: { position: "bottom" } },
                scales: {
                    x: { ticks: this._moneyTicks() },
                    y: { grid: { display: false } },
                },
            },
        });
    }
}

registry
    .category("actions")
    .add("pos_performance_dashboard", PosPerformanceDashboard);
