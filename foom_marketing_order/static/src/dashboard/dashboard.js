/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

/**
 * Dashboard Marketing Order.
 *
 * Chart digambar sebagai SVG inline, tanpa library eksternal sama sekali.
 * Alasannya: tidak ada dependensi yang bisa hilang/berubah path antar versi
 * Odoo, dan tidak butuh akses internet dari server.
 */
export class MarketingDashboard extends Component {
    static template = "foom_marketing_order.MarketingDashboard";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");

        this.state = useState({
            loading: true,
            error: false,
            range: "this_year",
            dateFrom: false,
            dateTo: false,
            data: null,
        });

        onWillStart(async () => {
            await this.load();
        });
    }

    // ----------------------------------------------------------- data

   computeRange(range) {
        const today = new Date();
        const fmt = (d) => {
            const m = String(d.getMonth() + 1).padStart(2, "0");
            const day = String(d.getDate()).padStart(2, "0");
            return `${d.getFullYear()}-${m}-${day}`;
        };
        switch (range) {
            case "this_month":
                return [fmt(new Date(today.getFullYear(), today.getMonth(), 1)), fmt(today)];
            case "last_3_months": {
                // Set tanggal ke-1 terlebih dahulu untuk menghindari bug akhir bulan (misal tgl 31)
                const d = new Date(today.getFullYear(), today.getMonth() - 2, 1);
                return [fmt(d), fmt(today)];
            }
            case "this_year":
                return [fmt(new Date(today.getFullYear(), 0, 1)), fmt(today)];
            case "all":
            default:
                return [false, false];
        }
    }

    async load() {
        this.state.loading = true;
        this.state.error = false;
        const [dateFrom, dateTo] = this.computeRange(this.state.range);
        this.state.dateFrom = dateFrom;
        this.state.dateTo = dateTo;
        try {
            this.state.data = await this.orm.call(
                "marketing.order",
                "get_dashboard_data",
                [dateFrom, dateTo]
            );
        } catch (e) {
            this.state.error = true;
            throw e;
        } finally {
            this.state.loading = false;
        }
    }

    async setRange(range) {
        this.state.range = range;
        await this.load();
    }

    // ----------------------------------------------------------- format

    formatNumber(value) {
        return new Intl.NumberFormat("id-ID", { maximumFractionDigits: 0 }).format(value || 0);
    }

    formatCompact(value) {
        const v = value || 0;
        if (Math.abs(v) >= 1e9) return (v / 1e9).toFixed(1).replace(".0", "") + " M";
        if (Math.abs(v) >= 1e6) return (v / 1e6).toFixed(1).replace(".0", "") + " jt";
        if (Math.abs(v) >= 1e3) return (v / 1e3).toFixed(0) + " rb";
        return String(Math.round(v));
    }

    // ----------------------------------------------------------- chart helpers

    /** Skala 0..100 untuk lebar/tinggi bar. */
    pct(value, list, key) {
        const max = Math.max(...list.map((r) => Math.abs(r[key] || 0)), 0);
        if (!max) {
            return 0;
        }
        return (Math.abs(value || 0) / max) * 100;
    }

    get trendBars() {
        const trend = (this.state.data && this.state.data.trend) || [];
        const max = Math.max(...trend.map((t) => t.value || 0), 0);
        return trend.map((t) => ({
            ...t,
            height: max ? Math.max((t.value / max) * 100, 1) : 0,
        }));
    }

    get stateSegments() {
        const rows = (this.state.data && this.state.data.state) || [];
        const total = rows.reduce((s, r) => s + r.count, 0);
        const colors = {
            draft: "#94a3b8",
            submit: "#f59e0b",
            confirm: "#16a34a",
            reject: "#dc2626",
        };
        let offset = 0;
        return rows.map((r) => {
            const share = total ? (r.count / total) * 100 : 0;
            const seg = {
                ...r,
                share,
                offset,
                color: colors[r.key] || "#64748b",
            };
            offset += share;
            return seg;
        });
    }

    get deliverySegments() {
        const rows = (this.state.data && this.state.data.delivery) || [];
        const total = rows.reduce((s, r) => s + r.count, 0);
        const colors = {
            draft: "#f59e0b",
            partially: "#0ea5e9",
            done: "#16a34a",
            cancel: "#94a3b8",
        };
        return rows.map((r) => ({
            ...r,
            share: total ? (r.count / total) * 100 : 0,
            color: colors[r.key] || "#64748b",
        }));
    }

    // ----------------------------------------------------------- drill-down

    async openOrders(extraDomain, title) {
        const domain = await this.orm.call(
            "marketing.order",
            "get_dashboard_domain",
            [this.state.dateFrom, this.state.dateTo, extraDomain || []]
        );
        this.action.doAction({
            type: "ir.actions.act_window",
            name: title || "Marketing Order",
            res_model: "marketing.order",
            views: [
                [false, "list"],
                [false, "form"],
            ],
            domain: domain,
            target: "current",
        });
    }

    onClickRequestor(row) {
        this.openOrders(
            [["requestor", "=", row.key || false]],
            "Marketing Order - " + row.label
        );
    }

    onClickType(row) {
        if (!row.id) {
            return this.openOrders([["type_id", "=", false]], "Marketing Order - Tanpa Tipe");
        }
        this.openOrders([["type_id", "=", row.id]], "Marketing Order - " + row.label);
    }

    onClickState(row) {
        this.openOrders([["state", "=", row.key]], "Marketing Order - " + row.label);
    }

    onClickDelivery(row) {
        this.openOrders(
            [
                ["state", "=", "confirm"],
                ["delivery_state", "=", row.key],
            ],
            "Marketing Order - " + row.label
        );
    }

    onClickAnalytic(row) {
        if (!row.id) {
            return;
        }
        this.openOrders([["analytic_id", "=", row.id]], "Marketing Order - " + row.label);
    }

    async onClickTrend(bar) {
        const mm = String(bar.month).padStart(2, "0");
        const from = `${bar.year}-${mm}-01`;
        const lastDay = new Date(bar.year, bar.month, 0).getDate();
        const to = `${bar.year}-${mm}-${String(lastDay).padStart(2, "0")}`;
        const domain = await this.orm.call(
            "marketing.order",
            "get_dashboard_domain",
            [from, to, []]
        );
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Marketing Order - " + bar.label,
            res_model: "marketing.order",
            views: [
                [false, "list"],
                [false, "form"],
            ],
            domain: domain,
            target: "current",
        });
    }

    onClickAllOrders() {
        this.openOrders([], "Marketing Order");
    }

    onClickPendingDelivery() {
        this.openOrders(
            [
                ["state", "=", "confirm"],
                ["delivery_state", "in", ["draft", "partially"]],
            ],
            "Delivery Belum Selesai"
        );
    }
}

registry.category("actions").add("foom_marketing_dashboard", MarketingDashboard);
