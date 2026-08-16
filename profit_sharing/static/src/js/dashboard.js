/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class ProfitSharingDashboard extends Component {
    static template = "profit_sharing.ProfitSharingDashboard";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = useState({
            loading: true,
            data: null,
            filters: {
                date_from: "",
                date_to: "",
                company_id: "",
                share_type_id: "",
                recipient_id: "",
                payment_state: "all",
            },
        });
        onWillStart(() => this.loadData());
    }

    async loadData() {
        this.state.loading = true;
        try {
            const filters = { ...this.state.filters };
            const data = await this.orm.call("profit.share.dashboard", "get_dashboard_data", [filters]);
            this.state.data = data;
            this.state.filters.date_from = data.filters.date_from || "";
            this.state.filters.date_to = data.filters.date_to || "";
            this.state.filters.company_id = data.filters.company_id || "";
            this.state.filters.share_type_id = data.filters.share_type_id || "";
            this.state.filters.recipient_id = data.filters.recipient_id || "";
            this.state.filters.payment_state = data.filters.payment_state || "all";
        } catch (error) {
            this.notification.add(error.message || "Unable to load Profit Sharing dashboard.", { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    onFilterChange(ev) {
        this.state.filters[ev.target.name] = ev.target.value;
    }

    sameId(left, right) {
        return `${left ?? ""}` === `${right ?? ""}`;
    }

    async applyFilters() {
        await this.loadData();
    }

    async resetFilters() {
        Object.assign(this.state.filters, {
            date_from: "",
            date_to: "",
            company_id: "",
            share_type_id: "",
            recipient_id: "",
            payment_state: "all",
        });
        await this.loadData();
    }

    formatMoney(value) {
        const currencyCode = this.state.data?.currency?.name || "IDR";
        try {
            const decimalPlaces = Number(this.state.data?.currency?.decimal_places ?? 0);
            return new Intl.NumberFormat(undefined, {
                style: "currency",
                currency: currencyCode,
                minimumFractionDigits: decimalPlaces,
                maximumFractionDigits: decimalPlaces,
            }).format(value || 0);
        } catch {
            return `${this.state.data?.currency?.symbol || ""} ${Number(value || 0).toLocaleString()}`;
        }
    }

    trendWidth(value, key) {
        const trend = this.state.data?.trend || [];
        const max = Math.max(...trend.map((item) => Math.abs(item[key] || 0)), 1);
        return Math.max(2, Math.round((Math.abs(value || 0) / max) * 100));
    }

    breakdownWidth(value) {
        const values = this.state.data?.share_type_breakdown || [];
        const max = Math.max(...values.map((item) => Math.abs(item.amount || 0)), 1);
        return Math.max(2, Math.round((Math.abs(value || 0) / max) * 100));
    }

    openBatch(batchId) {
        return this.action.doAction({
            type: "ir.actions.act_window",
            name: "Profit Sharing Computation",
            res_model: "profit.share.computation",
            res_id: batchId,
            views: [[false, "form"]],
            target: "current",
        });
    }
}

registry.category("actions").add("profit_sharing.dashboard", ProfitSharingDashboard);
