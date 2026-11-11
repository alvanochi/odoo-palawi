/** @odoo-module **/
/**
 * FOOM Sales Dashboard — client action OWL.
 *
 * Seluruh agregasi dilakukan di sisi server (model foom.sales.report).
 * Komponen di sini hanya bertugas memilih filter, memanggil satu RPC,
 * dan menggambar hasilnya.
 */

import {
    Component,
    onWillStart,
    onWillUnmount,
    useEffect,
    useExternalListener,
    useRef,
    useState,
} from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { browser } from "@web/core/browser/browser";

// ---------------------------------------------------------------------------
// Konstanta
// ---------------------------------------------------------------------------

const DAY_LABELS = [
    _t("Monday"), _t("Tuesday"), _t("Wednesday"), _t("Thursday"),
    _t("Friday"), _t("Saturday"), _t("Sunday"),
];

const DAY_SHORT = [
    _t("Mon"), _t("Tue"), _t("Wed"), _t("Thu"),
    _t("Fri"), _t("Sat"), _t("Sun"),
];

const PRESETS = [
    { id: "today", label: _t("Today") },
    { id: "7d", label: _t("7 days") },
    { id: "30d", label: _t("30 days") },
    { id: "mtd", label: _t("This month") },
    { id: "qtd", label: _t("This quarter") },
    { id: "ytd", label: _t("This year") },
    { id: "custom", label: _t("Custom") },
];

const GRANULARITIES = [
    { id: "auto", label: _t("Auto") },
    { id: "hour", label: _t("Hour") },
    { id: "day", label: _t("Day") },
    { id: "week", label: _t("Week") },
    { id: "month", label: _t("Month") },
    { id: "year", label: _t("Year") },
];

// Enam langkah ramp biru sekuensial. Sel bernilai nol tidak memakai ramp ini
// melainkan warna permukaan, supaya "kosong" tidak tertukar dengan "sedikit".
const HEAT_STEPS = 6;

// ---------------------------------------------------------------------------
// Helper format
// ---------------------------------------------------------------------------

function toIsoDate(date) {
    const pad = (n) => String(n).padStart(2, "0");
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

/** Rentang tanggal lokal untuk sebuah preset. */
function presetRange(preset) {
    const today = new Date();
    const start = new Date(today);
    switch (preset) {
        case "today":
            break;
        case "7d":
            start.setDate(start.getDate() - 6);
            break;
        case "30d":
            start.setDate(start.getDate() - 29);
            break;
        case "mtd":
            start.setDate(1);
            break;
        case "qtd":
            start.setMonth(Math.floor(start.getMonth() / 3) * 3, 1);
            break;
        case "ytd":
            start.setMonth(0, 1);
            break;
        default:
            start.setDate(start.getDate() - 29);
    }
    return { date_from: toIsoDate(start), date_to: toIsoDate(today) };
}

class Formatter {
    constructor(currency, lang) {
        this.currency = currency || { symbol: "", position: "before", decimals: 2 };
        this.lang = lang || "en-US";
        this.number = this._intl({ maximumFractionDigits: 0 });
        this.compact = this._intl({ notation: "compact", maximumFractionDigits: 1 });
        this.decimal = this._intl({ maximumFractionDigits: 2 });
    }
    _intl(options) {
        try {
            return new Intl.NumberFormat(this.lang, options);
        } catch {
            return new Intl.NumberFormat("en-US", options);
        }
    }
    money(value, { compact = false } = {}) {
        const fmt = compact ? this.compact : this.number;
        const body = fmt.format(value || 0);
        const symbol = this.currency.symbol;
        if (!symbol) {
            return body;
        }
        return this.currency.position === "after"
            ? `${body} ${symbol}`
            : `${symbol} ${body}`;
    }
    int(value) {
        return this.number.format(value || 0);
    }
    float(value) {
        return this.decimal.format(value || 0);
    }
    percent(value) {
        if (value === null || value === undefined) {
            return "—";
        }
        const sign = value > 0 ? "+" : "";
        return `${sign}${this.decimal.format(value)}%`;
    }
}

// ---------------------------------------------------------------------------
// Komponen kecil
// ---------------------------------------------------------------------------

class KpiCard extends Component {
    static template = "sales_dashboard.KpiCard";
    static props = {
        label: String,
        value: String,
        growth: { optional: true },
        growthLabel: { type: String, optional: true },
        hint: { type: String, optional: true },
        icon: { type: String, optional: true },
    };

    get direction() {
        const g = this.props.growth;
        if (g === null || g === undefined || Math.abs(g) < 0.05) {
            return "flat";
        }
        return g > 0 ? "up" : "down";
    }
}

/**
 * Pembungkus Chart.js. Instance selalu dihancurkan sebelum dibuat ulang
 * supaya tidak ada canvas yang bocor saat filter berubah.
 */
class ChartCanvas extends Component {
    static template = "sales_dashboard.ChartCanvas";
    static props = {
        config: Object,
        // Kunci stabil yang hanya berubah saat data berubah. Tanpa ini, setiap
        // re-render (mis. tooltip heatmap) akan menggambar ulang seluruh chart.
        dataKey: String,
        height: { type: Number, optional: true },
    };

    setup() {
        this.canvasRef = useRef("canvas");
        this.chart = null;
        useEffect(
            () => {
                this._draw();
                return () => this._destroy();
            },
            () => [this.props.dataKey]
        );
        onWillUnmount(() => this._destroy());
    }

    _destroy() {
        if (this.chart) {
            this.chart.destroy();
            this.chart = null;
        }
    }

    _draw() {
        const ChartLib = browser.Chart || window.Chart;
        const canvas = this.canvasRef.el;
        if (!ChartLib || !canvas) {
            return;
        }
        this._destroy();
        this.chart = new ChartLib(canvas.getContext("2d"), this.props.config);
    }
}

class RankList extends Component {
    static template = "sales_dashboard.RankList";
    static props = {
        title: String,
        rows: Array,
        formatter: Object,
        emptyLabel: String,
        showQty: { type: Boolean, optional: true },
        onRowClick: { type: Function, optional: true },
    };

    get maxAmount() {
        return Math.max(1, ...this.props.rows.map((r) => Math.abs(r.amount)));
    }

    width(row) {
        return Math.max(2, (Math.abs(row.amount) / this.maxAmount) * 100);
    }

    onClick(row) {
        if (this.props.onRowClick) {
            this.props.onRowClick(row);
        }
    }
}

// ---------------------------------------------------------------------------
// Komponen utama
// ---------------------------------------------------------------------------

export class FoomDashboard extends Component {
    static template = "sales_dashboard.Dashboard";
    static components = { KpiCard, ChartCanvas, RankList };
    static props = ["*"];

    setup() {
        this.rootRef = useRef("root");

        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");

        const initial = presetRange("30d");
        this.state = useState({
            loading: true,
            error: null,
            preset: "30d",
            dateFrom: initial.date_from,
            dateTo: initial.date_to,
            granularity: "auto",
            heatMetric: "orders",
            companyIds: [],
            warehouseIds: [],
            locationIds: [],
            openMenu: null,
            options: {
                companies: [],
                warehouses: [],
                locations: [],
                multi_company: false,
            },
            data: null,
            tooltip: null,
        });

        // Tutup dropdown filter saat klik di luar komponennya.
        useExternalListener(window, "click", () => {
            this.state.openMenu = null;
        });

        this.formatter = new Formatter(null, "en-US");
        this.presets = PRESETS;
        this.granularities = GRANULARITIES;
        this.dayLabels = DAY_LABELS;
        this.dayShort = DAY_SHORT;
        this.hours = Array.from({ length: 24 }, (_, i) => i);

        onWillStart(async () => {
            await this.loadOptions();
            await this.loadData();
        });

        // Ukur ulang setelah setiap patch DOM (isi berubah saat filter diganti)
        // dan setiap kali jendela berubah ukuran atau zoom.
        useEffect(() => {
            this._fitToViewport();
        });
        useExternalListener(window, "resize", () => this._fitToViewport());
    }

    // ------------------------------------------------------------------
    // Scroll
    // ------------------------------------------------------------------

    /**
     * Jadikan dashboard sendiri sebagai scroller dengan tinggi piksel tetap.
     *
     * Tiga percobaan sebelumnya gagal karena semuanya bergantung pada leluhur:
     * `height: 100%` butuh induk bertinggi definit, dan menebak elemen pemotong
     * lewat selector `:has()` maupun penelusuran `scrollHeight` ternyata meleset
     * pada struktur Odoo yang sebenarnya.
     *
     * Cara ini tidak menyentuh leluhur sama sekali. Jarak dari puncak dashboard
     * ke dasar viewport diukur langsung, lalu dipasang sebagai tinggi tetap
     * dalam piksel. Tinggi definit + `overflow-y: scroll` selalu menghasilkan
     * scrollbar, apa pun yang dilakukan pembungkus di atasnya. Karena dashboard
     * jadi pas di area yang terlihat, leluhur tidak pernah kelebihan isi
     * sehingga tidak ada scrollbar ganda.
     */
    _fitToViewport() {
        const root = this.rootRef.el;
        if (!root) {
            return;
        }

        const top = root.getBoundingClientRect().top;
        const available = window.innerHeight - top;

        root.style.height = Math.max(240, Math.round(available)) + "px";
        root.style.overflowY = "scroll";
        root.style.overflowX = "hidden";
    }

    // -- data -------------------------------------------------------------

    /**
     * Lengkapi balasan server dengan nilai bawaan.
     *
     * Kalau Python dan asset JS tidak seumur — upgrade setengah jalan, atau
     * bundle lama yang masih ter-cache di browser — balasan server bisa
     * kehilangan kunci yang dibaca template. Tanpa penjaga ini satu kunci hilang
     * saja membuat SELURUH render OWL gagal, dan dashboard ikut kehilangan
     * tinggi yang dipasang `_fitToViewport`, sehingga gejalanya muncul sebagai
     * "scroll tiba-tiba hilang" alih-alih pesan error yang jelas.
     */
    _withDefaults(payload, defaults) {
        const safe = { ...defaults };
        for (const [key, fallback] of Object.entries(defaults)) {
            const value = payload && payload[key];
            if (value === undefined || value === null) {
                continue;
            }
            // Jangan biarkan tipe yang salah lolos: template mengharapkan array.
            if (Array.isArray(fallback) && !Array.isArray(value)) {
                continue;
            }
            safe[key] = value;
        }
        return safe;
    }

    async loadOptions() {
        try {
            const options = await this.orm.call(
                "foom.sales.report",
                "get_filter_options",
                []
            );
            this.state.options = this._withDefaults(options, {
                companies: [],
                warehouses: [],
                locations: [],
                multi_company: false,
                tz: "",
                lang: "en-US",
                currency: { symbol: "", position: "before", decimals: 2 },
            });
            this.formatter = new Formatter(
                this.state.options.currency,
                this.state.options.lang
            );
        } catch (error) {
            this.state.error = error.message || String(error);
        }
    }

    async loadData() {
        this.state.loading = true;
        this.state.error = null;
        try {
            const payload = await this.orm.call(
                "foom.sales.report",
                "get_dashboard_data",
                [],
                {
                    date_from: this.state.dateFrom,
                    date_to: this.state.dateTo,
                    granularity: this.state.granularity,
                    company_ids: this.state.companyIds,
                    warehouse_ids: this.state.warehouseIds,
                    location_ids: this.state.locationIds,
                }
            );
            this.state.data = this._withDefaults(payload, {
                granularity: "day",
                has_data: false,
                heatmap: [],
                hourly: [],
                trend: [],
                top_products: [],
                top_warehouses: [],
                top_locations: [],
                top_partners: [],
                tax_breakdown: [],
                kpi: null,
            });
            if (!this.state.data.kpi) {
                // KPI tidak bisa digambar tanpa data; perlakukan seperti periode kosong.
                this.state.data.has_data = false;
            }
        } catch (error) {
            this.state.data = null;
            this.state.error = error.message || String(error);
        } finally {
            this.state.loading = false;
        }
    }

    // -- interaksi filter --------------------------------------------------

    async setPreset(preset) {
        this.state.preset = preset;
        if (preset !== "custom") {
            const range = presetRange(preset);
            this.state.dateFrom = range.date_from;
            this.state.dateTo = range.date_to;
            await this.loadData();
        }
    }

    async onDateChange(field, event) {
        const value = event.target.value;
        if (!value) {
            return;
        }
        this.state.preset = "custom";
        this.state[field] = value;
        await this.loadData();
    }

    async onGranularityChange(event) {
        this.state.granularity = event.target.value;
        await this.loadData();
    }

    toggleMenu(name) {
        this.state.openMenu = this.state.openMenu === name ? null : name;
    }

    /** Ringkasan isi dropdown: "Semua" atau nama tunggal atau jumlah terpilih. */
    _summary(selected, items, allLabel) {
        if (!selected.length) {
            return allLabel;
        }
        if (selected.length === 1) {
            const found = items.find((i) => i.id === selected[0]);
            return found ? found.name : allLabel;
        }
        return _t("%s selected", selected.length);
    }

    get warehouseSummary() {
        return this._summary(
            this.state.warehouseIds,
            this.state.options.warehouses,
            _t("All warehouses")
        );
    }

    get locationSummary() {
        return this._summary(
            this.state.locationIds,
            this.state.options.locations,
            _t("All locations")
        );
    }

    get companySummary() {
        return this._summary(
            this.state.companyIds,
            this.state.options.companies,
            _t("All companies")
        );
    }

    async _toggleId(field, id) {
        const current = this.state[field];
        this.state[field] = current.includes(id)
            ? current.filter((v) => v !== id)
            : [...current, id];
        await this.loadData();
    }

    async toggleWarehouse(id) {
        await this._toggleId("warehouseIds", id);
    }

    async toggleLocation(id) {
        await this._toggleId("locationIds", id);
    }

    async toggleCompany(id) {
        await this._toggleId("companyIds", id);
    }

    async clearSelection(field) {
        this.state[field] = [];
        await this.loadData();
    }

    setHeatMetric(metric) {
        this.state.heatMetric = metric;
    }

    // -- KPI ---------------------------------------------------------------

    get kpiCards() {
        const kpi = this.state.data && this.state.data.kpi;
        if (!kpi || !kpi.amount) {
            return [];
        }
        const f = this.formatter;
        // Jam puncak dihitung server; beri nilai netral bila balasan tidak memuatnya.
        const peak = kpi.peak_hour || { label: "\u2014", amount: 0 };
        return [
            {
                label: _t("Total Revenue"),
                value: f.money(kpi.amount.value),
                growth: kpi.amount.growth,
                hint: _t("Previous: %s", f.money(kpi.amount.previous, { compact: true })),
                icon: "fa-money",
            },
            {
                label: _t("Sales Tax"),
                value: f.money((kpi.tax || {}).value || 0),
                growth: (kpi.tax || {}).growth ?? null,
                hint: _t("Previous: %s", f.money((kpi.tax || {}).previous || 0, { compact: true })),
                icon: "fa-percent",
            },
            {
                label: _t("Orders"),
                value: f.int(kpi.orders.value),
                growth: kpi.orders.growth,
                hint: _t("Previous: %s", f.int(kpi.orders.previous)),
                icon: "fa-shopping-cart",
            },
            {
                label: _t("Average per Order"),
                value: f.money(kpi.avg_order.value),
                growth: kpi.avg_order.growth,
                hint: _t("Previous: %s", f.money(kpi.avg_order.previous, { compact: true })),
                icon: "fa-balance-scale",
            },
            {
                label: _t("Customers"),
                value: f.int(kpi.customers.value),
                growth: kpi.customers.growth,
                hint: _t("Previous: %s", f.int(kpi.customers.previous)),
                icon: "fa-users",
            },
            {
                label: _t("Quantity Sold"),
                value: f.float(kpi.quantity.value),
                growth: kpi.quantity.growth,
                hint: _t("Previous: %s", f.float(kpi.quantity.previous)),
                icon: "fa-cubes",
            },
            {
                label: _t("Peak Hour"),
                value: peak.label,
                growth: null,
                hint: _t("Revenue %s", f.money(peak.amount, { compact: true })),
                icon: "fa-clock-o",
            },
        ];
    }

    growthLabel(growth) {
        return this.formatter.percent(growth);
    }

    /** Kunci render chart: berubah hanya ketika data atau metrik berubah. */
    get dataKey() {
        const d = this.state.data;
        if (!d) {
            return "empty";
        }
        return [
            this.state.dateFrom,
            this.state.dateTo,
            this.state.granularity,
            d.granularity,
            this.state.heatMetric,
            this.state.companyIds.join("."),
            this.state.warehouseIds.join("."),
            this.state.locationIds.join("."),
            d.trend.length,
        ].join("|");
    }

    // -- heatmap -----------------------------------------------------------

    get heatmapRows() {
        const cells = (this.state.data && this.state.data.heatmap) || [];
        const metric = this.state.heatMetric;
        const max = Math.max(0, ...cells.map((c) => Math.abs(c[metric])));
        const byDow = new Map();
        for (const cell of cells) {
            if (!byDow.has(cell.dow)) {
                byDow.set(cell.dow, []);
            }
            const value = cell[metric];
            byDow.get(cell.dow).push({
                ...cell,
                value,
                // Level 0 = benar-benar kosong; 1..HEAT_STEPS = ramp sekuensial.
                level: !value || !max
                    ? 0
                    : Math.max(1, Math.ceil((Math.abs(value) / max) * HEAT_STEPS)),
            });
        }
        return [1, 2, 3, 4, 5, 6, 7].map((dow, index) => ({
            dow,
            label: this.dayLabels[index],
            short: this.dayShort[index],
            cells: byDow.get(dow) || [],
        }));
    }

    get heatLegendSteps() {
        return Array.from({ length: HEAT_STEPS }, (_, i) => i + 1);
    }

    onCellEnter(row, cell, event) {
        const f = this.formatter;
        this.state.tooltip = {
            title: `${row.label}, ${String(cell.hour).padStart(2, "0")}:00–${String(
                (cell.hour + 1) % 24
            ).padStart(2, "0")}:00`,
            lines: [
                `${_t("Orders")}: ${f.int(cell.orders)}`,
                `${_t("Revenue")}: ${f.money(cell.amount)}`,
            ],
            x: event.clientX,
            y: event.clientY,
        };
    }

    onCellLeave() {
        this.state.tooltip = null;
    }

    // -- konfigurasi Chart.js ---------------------------------------------

    /**
     * Token warna dibaca dari CSS custom property, bukan di-hardcode di JS,
     * supaya mode gelap Odoo cukup mengganti nilai variabel di satu tempat.
     */
    _cssVar(name, fallback) {
        const value = getComputedStyle(document.documentElement).getPropertyValue(name);
        return (value && value.trim()) || fallback;
    }

    get chartInk() {
        return {
            grid: this._cssVar("--foom-grid", "#e1e0d9"),
            text: this._cssVar("--foom-muted", "#898781"),
            amount: this._cssVar("--foom-series-1", "#2a78d6"),
            orders: this._cssVar("--foom-series-2", "#eb6834"),
            surface: this._cssVar("--foom-surface", "#ffffff"),
        };
    }

    _baseOptions(valueFormatter) {
        const ink = this.chartInk;
        return {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: "index", intersect: false },
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: (ctx) => `${ctx.dataset.label}: ${valueFormatter(ctx.parsed.y)}`,
                    },
                },
            },
            scales: {
                x: {
                    grid: { display: false },
                    border: { color: ink.grid },
                    ticks: { color: ink.text, maxRotation: 0, autoSkipPadding: 16 },
                },
                y: {
                    beginAtZero: true,
                    grid: { color: ink.grid, drawBorder: false },
                    border: { display: false },
                    ticks: {
                        color: ink.text,
                        callback: (value) => valueFormatter(value, true),
                    },
                },
            },
        };
    }

    /**
     * Tren omzet dan tren jumlah order sengaja dipisah menjadi dua grafik
     * dengan sumbu masing-masing. Menumpuk dua satuan berbeda pada satu
     * grafik bersumbu ganda membuat perpotongan garis terbaca sebagai
     * hubungan yang sebenarnya tidak ada.
     */
    get trendAmountConfig() {
        const trend = (this.state.data && this.state.data.trend) || [];
        const ink = this.chartInk;
        const f = this.formatter;
        return {
            type: "line",
            data: {
                labels: trend.map((t) => t.label),
                datasets: [
                    {
                        label: _t("Revenue"),
                        data: trend.map((t) => t.amount),
                        borderColor: ink.amount,
                        backgroundColor: ink.amount,
                        borderWidth: 2,
                        pointRadius: trend.length > 60 ? 0 : 3,
                        pointHoverRadius: 5,
                        tension: 0.25,
                        fill: false,
                    },
                ],
            },
            options: this._baseOptions((v, axis) => f.money(v, { compact: !!axis })),
        };
    }

    get trendOrdersConfig() {
        const trend = (this.state.data && this.state.data.trend) || [];
        const ink = this.chartInk;
        const f = this.formatter;
        return {
            type: "bar",
            data: {
                labels: trend.map((t) => t.label),
                datasets: [
                    {
                        label: _t("Order count"),
                        data: trend.map((t) => t.orders),
                        backgroundColor: ink.orders,
                        borderRadius: 4,
                        borderSkipped: "bottom",
                        borderWidth: 2,
                        borderColor: ink.surface,
                    },
                ],
            },
            options: this._baseOptions((v) => f.int(v)),
        };
    }

    get hourlyConfig() {
        const hourly = (this.state.data && this.state.data.hourly) || [];
        const ink = this.chartInk;
        const f = this.formatter;
        const metric = this.state.heatMetric;
        const isAmount = metric === "amount";
        return {
            type: "bar",
            data: {
                labels: hourly.map((h) => `${String(h.hour).padStart(2, "0")}:00`),
                datasets: [
                    {
                        label: isAmount ? _t("Revenue") : _t("Order count"),
                        data: hourly.map((h) => h[metric]),
                        backgroundColor: isAmount ? ink.amount : ink.orders,
                        borderRadius: 4,
                        borderSkipped: "bottom",
                        borderWidth: 2,
                        borderColor: ink.surface,
                    },
                ],
            },
            options: this._baseOptions((v, axis) =>
                isAmount ? f.money(v, { compact: !!axis }) : f.int(v)
            ),
        };
    }

    // -- drill-down & export ----------------------------------------------

    _openList(name, extraDomain) {
        const domain = [
            ["date_ts", ">=", `${this.state.dateFrom} 00:00:00`],
            ["date_ts", "<=", `${this.state.dateTo} 23:59:59`],
            ...extraDomain,
        ];
        this.action.doAction({
            type: "ir.actions.act_window",
            name,
            res_model: "foom.sales.report",
            view_mode: "list,pivot,graph",
            views: [[false, "list"], [false, "pivot"], [false, "graph"]],
            domain,
            target: "current",
        });
    }

    openProduct(row) {
        this._openList(row.name, [["product_tmpl_id", "=", row.id]]);
    }

    openWarehouse(row) {
        this._openList(row.name, [["warehouse_id", "=", row.id || false]]);
    }

    openLocation(row) {
        this._openList(row.name, [["location_id", "=", row.id || false]]);
    }

    openPartner(row) {
        this._openList(row.name, [["partner_id", "=", row.id || false]]);
    }

    openRawData() {
        this._openList(_t("Sales Data"), []);
    }

    exportCsv() {
        const data = this.state.data;
        if (!data) {
            return;
        }
        const rows = [["section", "key", "label", "orders", "quantity", "amount"]];
        for (const t of data.trend) {
            rows.push(["trend", t.key, t.label, t.orders, "", t.amount]);
        }
        for (const h of data.hourly) {
            rows.push(["hourly", h.hour, `${h.hour}:00`, h.orders, "", h.amount]);
        }
        for (const c of data.heatmap) {
            rows.push(["heatmap", `${c.dow}-${c.hour}`, "", c.orders, "", c.amount]);
        }
        const sections = [
            ["top_product", data.top_products],
            ["top_warehouse", data.top_warehouses],
            ["top_location", data.top_locations],
            ["top_partner", data.top_partners],
        ];
        for (const [section, list] of sections) {
            for (const r of list) {
                rows.push([section, r.id, r.name, r.orders, r.quantity, r.amount]);
            }
        }
        const csv = rows
            .map((row) =>
                row
                    .map((cell) => `"${String(cell === null ? "" : cell).replace(/"/g, '""')}"`)
                    .join(",")
            )
            .join("\n");
        const blob = new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8;" });
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = `foom_sales_${this.state.dateFrom}_${this.state.dateTo}.csv`;
        link.click();
        URL.revokeObjectURL(url);
        this.notification.add(_t("The CSV file is downloading."), { type: "success" });
    }
}

registry.category("actions").add("sales_dashboard.dashboard", FoomDashboard);
