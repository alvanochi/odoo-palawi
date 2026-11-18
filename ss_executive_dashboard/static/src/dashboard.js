/** @odoo-module **/
import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const pad = (n) => String(n).padStart(2, "0");
const ymd = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
// local midnight -> UTC "YYYY-MM-DD HH:MM:SS" (Odoo stores datetimes in UTC)
const utc = (d) => d.toISOString().slice(0, 19).replace("T", " ");
const sum = (arr, f) => arr.reduce((a, x) => a + (f(x) || 0), 0);

export function rp(v) {
    const a = Math.abs(v || 0);
    const s = v < 0 ? "-" : "";
    if (a >= 1e9) return `${s}Rp ${(a / 1e9).toFixed(2).replace(".", ",")} M`;
    if (a >= 1e6) return `${s}Rp ${(a / 1e6).toFixed(1).replace(".", ",")} jt`;
    return `${s}Rp ${Math.round(a).toLocaleString("id-ID")}`;
}
const pct = (v) => `${Math.round(v || 0)}%`;

class SSExecutiveDashboard extends Component {
    static template = "ss_executive_dashboard.Dashboard";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.rp = rp;
        this.pct = pct;
        this.state = useState({ loading: true, period: "month", data: null, error: null });
        onWillStart(() => this.load());
    }

    range() {
        const now = new Date();
        const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
        const tomorrow = new Date(today); tomorrow.setDate(today.getDate() + 1);
        let from, to = tomorrow, label;
        if (this.state.period === "last_month") {
            from = new Date(today.getFullYear(), today.getMonth() - 1, 1);
            to = new Date(today.getFullYear(), today.getMonth(), 1);
            label = from.toLocaleDateString("id-ID", { month: "long", year: "numeric" });
        } else if (this.state.period === "30d") {
            from = new Date(today); from.setDate(today.getDate() - 29);
            label = "30 hari terakhir";
        } else {
            from = new Date(today.getFullYear(), today.getMonth(), 1);
            label = today.toLocaleDateString("id-ID", { month: "long", year: "numeric" }) + " (s/d hari ini)";
        }
        const monthStart = new Date(from.getFullYear(), from.getMonth(), 1);
        const monthEnd = new Date(from.getFullYear(), from.getMonth() + 1, 1);
        const daysInMonth = Math.round((monthEnd - monthStart) / 864e5);
        const days = Math.max(1, Math.round((to - from) / 864e5));
        // fraction of the monthly target that should be reached in this window
        const targetFactor = this.state.period === "30d" ? 1 : Math.min(1, days / daysInMonth);
        return { now, today, from, to, label, days, daysInMonth, targetFactor };
    }

    async safe(p, fallback) {
        try { return await p; } catch (e) { console.warn("SS dashboard:", e); return fallback; }
    }

    async load() {
        this.state.loading = true;
        const r = this.range();
        const fromDt = utc(r.from), toDt = utc(r.to), nowDt = utc(r.now);
        const fromD = ymd(r.from), toD = ymd(r.to), todayD = ymd(r.today);
        const trendFrom = new Date(r.today); trendFrom.setDate(r.today.getDate() - 29);
        const orm = this.orm;
        const soDom = [["state", "=", "sale"], ["date_order", ">=", fromDt], ["date_order", "<", toDt]];
        const posted = [["parent_state", "=", "posted"]];
        const inPeriod = [["date", ">=", fromD], ["date", "<", toD]];

        const [
            byTeam, teams, trend, soLines, variants, live,
            income, cogs, opex, cash, recv, recvOverdue, pay, budget, ads,
            quants, products, lots, pos, mos, pickings,
            empCount, attToday, lateTasks, todaySales, approvals, posByTeam, posToday,
        ] = await Promise.all([
            orm.readGroup("sale.order", soDom, ["amount_untaxed:sum"], ["team_id"], { lazy: false }),
            orm.searchRead("crm.team", [["name", "=like", "SS - %"]], ["name", "invoiced_target"]),
            orm.readGroup("sale.order", [["state", "=", "sale"], ["date_order", ">=", utc(trendFrom)], ["date_order", "<", utc(new Date(r.today.getTime() + 864e5))]], ["amount_untaxed:sum"], ["date_order:day"], { lazy: false }),
            orm.searchRead("sale.order.line", [["order_id.state", "=", "sale"], ["order_id.date_order", ">=", fromDt], ["order_id.date_order", "<", toDt], ["display_type", "=", false]], ["product_id", "price_subtotal", "product_uom_qty"]),
            orm.searchRead("product.product", [["sale_ok", "=", true]], ["product_tmpl_id"]),
            this.safe(orm.searchRead("x_ss_live_session", [["x_start", ">=", fromDt], ["x_start", "<", toDt]], ["x_host_id", "x_target", "x_actual", "x_order_count", "x_duration", "x_state"]), []),
            orm.readGroup("account.move.line", [...posted, ...inPeriod, ["account_id.account_type", "in", ["income", "income_other"]]], ["balance:sum"], [], { lazy: false }),
            orm.readGroup("account.move.line", [...posted, ...inPeriod, ["account_id.account_type", "=", "expense_direct_cost"]], ["balance:sum"], [], { lazy: false }),
            orm.readGroup("account.move.line", [...posted, ...inPeriod, ["account_id.account_type", "in", ["expense", "expense_depreciation"]]], ["balance:sum"], [], { lazy: false }),
            orm.readGroup("account.move.line", [...posted, "|", ["account_id.account_type", "=", "asset_cash"], ["account_id.name", "ilike", "Outstanding"]], ["balance:sum"], ["journal_id"], { lazy: false }),
            orm.readGroup("account.move.line", [...posted, ["account_id.account_type", "=", "asset_receivable"], ["reconciled", "=", false]], ["amount_residual:sum"], ["partner_id"], { lazy: false }),
            orm.readGroup("account.move.line", [...posted, ["account_id.account_type", "=", "asset_receivable"], ["reconciled", "=", false], ["date_maturity", "<", todayD]], ["amount_residual:sum"], [], { lazy: false }),
            orm.readGroup("account.move.line", [...posted, ["account_id.account_type", "=", "liability_payable"], ["reconciled", "=", false]], ["amount_residual:sum"], [], { lazy: false }),
            this.safe(orm.searchRead("crossovered.budget.lines", [["date_from", "<=", todayD], ["date_to", ">=", todayD], ["crossovered_budget_state", "=", "validate"]], ["general_budget_id", "analytic_account_id", "planned_amount", "practical_amount", "theoritical_amount"]), []),
            orm.readGroup("account.move.line", [...posted, ...inPeriod, ["account_id.code", "in", ["61200010", "61200020", "61200030", "61200040"]]], ["balance:sum"], ["account_id"], { lazy: false }),
            orm.searchRead("stock.quant", [["location_id.usage", "=", "internal"]], ["value", "quantity"]),
            orm.searchRead("product.product", [["is_storable", "=", true], ["sale_ok", "=", true]], ["display_name", "qty_available", "product_tmpl_id"]),
            this.safe(orm.searchRead("stock.lot", [["alert_date", "<=", nowDt]], ["name", "product_id", "expiration_date", "product_qty"]), []),
            orm.searchRead("purchase.order", [["state", "in", ["to approve", "purchase"]]], ["name", "partner_id", "state", "amount_total", "date_planned", "receipt_status"]),
            orm.searchRead("mrp.production", [["state", "not in", ["done", "cancel"]]], ["name", "product_id", "state", "product_qty", "qty_producing", "date_deadline", "origin"]),
            orm.searchRead("stock.picking", [["state", "in", ["assigned", "waiting", "confirmed"]]], ["picking_type_id", "state", "scheduled_date"]),
            orm.searchCount("hr.employee", []),
            this.safe(orm.searchCount("hr.attendance", [["check_in", ">=", utc(r.today)]]), 0),
            this.safe(orm.searchCount("project.task", [["date_deadline", "<", nowDt], ["stage_id.fold", "=", false], ["project_id", "!=", false]]), 0),
            orm.readGroup("sale.order", [["state", "=", "sale"], ["date_order", ">=", utc(r.today)]], ["amount_untaxed:sum"], [], { lazy: false }),
            this.safe(orm.searchRead("x_ss_approval", [["x_state", "=", "submitted"]], ["x_number", "x_name", "x_amount", "x_approver_id", "x_over_budget", "x_type", "x_requester_id", "x_deadline"], { order: "x_over_budget desc, x_amount desc" }), []),
            this.safe(orm.readGroup("pos.order", [["state", "in", ["paid", "done", "invoiced"]], ["date_order", ">=", fromDt], ["date_order", "<", toDt]], ["amount_total:sum", "amount_tax:sum"], ["crm_team_id"], { lazy: false }), []),
            this.safe(orm.readGroup("pos.order", [["state", "in", ["paid", "done", "invoiced"]], ["date_order", ">=", utc(r.today)]], ["amount_total:sum", "amount_tax:sum"], [], { lazy: false }), []),
        ]);
        // POS sales count towards their sales team (Offline Store)
        for (const g of posByTeam) {
            if (!g.crm_team_id) continue;
            byTeam.push({ team_id: g.crm_team_id, amount_untaxed: (g.amount_total || 0) - (g.amount_tax || 0), __count: g.__count });
        }

        // ---- Sales ----
        const teamMap = Object.fromEntries(teams.map((t) => [t.id, t]));
        const channels = teams.map((t) => {
            const gs = byTeam.filter((x) => x.team_id && x.team_id[0] === t.id);
            const actual = sum(gs, (g) => g.amount_untaxed);
            const target = (t.invoiced_target || 0) * r.targetFactor;
            return { id: t.id, name: t.name.replace("SS - ", ""), actual, orders: sum(gs, (g) => g.__count), target, monthTarget: t.invoiced_target, ach: target ? (actual / target) * 100 : 0 };
        }).sort((a, b) => b.actual - a.actual);
        const salesTotal = sum(byTeam.filter((g) => g.team_id && teamMap[g.team_id[0]]), (g) => g.amount_untaxed);
        const ordersTotal = sum(channels, (c) => c.orders);
        const targetTotal = sum(channels, (c) => c.target);
        const trendMax = Math.max(1, ...trend.map((t) => t.amount_untaxed));
        const trendBars = trend.map((t) => ({ label: t["date_order:day"], value: t.amount_untaxed, h: Math.max(2, (t.amount_untaxed / trendMax) * 100) }));
        const tmplOf = Object.fromEntries(variants.map((v) => [v.id, v.product_tmpl_id]));
        const prodAgg = {};
        for (const l of soLines) {
            const t = tmplOf[l.product_id[0]];
            if (!t) continue;
            prodAgg[t[0]] = prodAgg[t[0]] || { id: t[0], name: t[1], value: 0, qty: 0 };
            prodAgg[t[0]].value += l.price_subtotal; prodAgg[t[0]].qty += l.product_uom_qty;
        }
        const topProducts = Object.values(prodAgg).sort((a, b) => b.value - a.value).slice(0, 6);
        const topMax = Math.max(1, ...topProducts.map((p) => p.value));
        topProducts.forEach((p) => (p.w = (p.value / topMax) * 100));

        // ---- Live streaming ----
        const hosts = {};
        for (const s of live) {
            const k = s.x_host_id ? s.x_host_id[1] : "-";
            hosts[k] = hosts[k] || { name: k, sessions: 0, target: 0, actual: 0, hours: 0, orders: 0 };
            hosts[k].sessions++; hosts[k].target += s.x_target || 0; hosts[k].actual += s.x_actual || 0;
            hosts[k].hours += s.x_duration || 0; hosts[k].orders += s.x_order_count || 0;
        }
        const liveHosts = Object.values(hosts).map((h) => ({ ...h, ach: h.target ? (h.actual / h.target) * 100 : 0 })).sort((a, b) => b.actual - a.actual);
        const liveTot = { sessions: live.length, actual: sum(liveHosts, (h) => h.actual), target: sum(liveHosts, (h) => h.target), hours: sum(liveHosts, (h) => h.hours) };
        liveTot.ach = liveTot.target ? (liveTot.actual / liveTot.target) * 100 : 0;

        // ---- Finance ----
        const g0 = (rg, f) => (rg[0] && rg[0][f]) || 0;
        const revenue = -g0(income, "balance");
        const cogsV = g0(cogs, "balance");
        const opexV = g0(opex, "balance");
        const fin = {
            revenue, cogs: cogsV, opex: opexV, gross: revenue - cogsV, net: revenue - cogsV - opexV,
            grossMargin: revenue ? ((revenue - cogsV) / revenue) * 100 : 0,
            cash: cash.map((c) => ({ name: c.journal_id ? c.journal_id[1] : "-", value: c.balance })).filter((c) => Math.abs(c.value) > 1).sort((a, b) => b.value - a.value),
            receivable: sum(recv, (g) => g.amount_residual),
            mpPending: sum(recv.filter((g) => g.partner_id && /TikTok Shop|Shopee/.test(g.partner_id[1])), (g) => g.amount_residual),
            overdue: g0(recvOverdue, "amount_residual"),
            payable: -g0(pay, "amount_residual"),
        };
        fin.cashTotal = sum(fin.cash, (c) => c.value);
        const budgets = budget.map((b) => ({
            name: (b.general_budget_id && b.general_budget_id[1] || "").replace("SS - ", ""),
            planned: Math.abs(b.planned_amount), actual: Math.abs(b.practical_amount), theo: Math.abs(b.theoritical_amount),
        })).map((b) => ({ ...b, used: b.planned ? (b.actual / b.planned) * 100 : 0, over: b.actual > b.planned || b.actual > b.theo * 1.1 }));

        // ---- Marketing ----
        const adsTotal = sum(ads, (a) => a.balance);
        const adsRows = ads.map((a) => ({ name: a.account_id[1].replace(/^\d+\s/, ""), value: a.balance }));
        const mpSales = sum(channels.filter((c) => /TikTok|Shopee/.test(c.name)), (c) => c.actual);
        const mkt = { total: adsTotal, rows: adsRows, roas: adsTotal ? mpSales / adsTotal : 0, ratio: salesTotal ? (adsTotal / salesTotal) * 100 : 0 };

        // ---- Operations ----
        const stockValue = sum(quants, (q) => q.value);
        const topIds = new Set(topProducts.slice(0, 4).map((p) => p.id));
        const lowStock = products.filter((p) => p.qty_available < 15).sort((a, b) => a.qty_available - b.qty_available)
            .map((p) => ({ ...p, best: topIds.has(p.product_tmpl_id[0]) })).slice(0, 8);
        const expiring = lots.filter((l) => l.product_qty > 0);
        const poApprove = pos.filter((p) => p.state === "to approve");
        const poLate = pos.filter((p) => p.state === "purchase" && p.receipt_status !== "full" && p.date_planned && p.date_planned < nowDt);
        const poOpen = pos.filter((p) => p.state === "purchase" && p.receipt_status !== "full");
        const moLate = mos.filter((m) => m.date_deadline && m.date_deadline < nowDt);
        const moProgress = mos.filter((m) => m.state === "progress");
        const wh = {};
        for (const p of pickings) {
            const k = p.picking_type_id ? p.picking_type_id[1] : "-";
            wh[k] = wh[k] || { name: k, ready: 0, waiting: 0, id: p.picking_type_id && p.picking_type_id[0] };
            p.state === "assigned" ? wh[k].ready++ : wh[k].waiting++;
        }
        const ops = { stockValue, lowStock, expiring, poApprove, poLate, poOpen, moLate, moProgress, moOpen: mos.length, warehouse: Object.values(wh).sort((a, b) => b.ready - a.ready) };

        // ---- HR ----
        const hr = { employees: empCount, present: attToday, lateTasks };

        // ---- Decision alerts ----
        const alerts = [];
        for (const c of channels) if (c.target && c.ach < 90) alerts.push({ level: c.ach < 70 ? "danger" : "warning", icon: "fa-line-chart", text: `Penjualan ${c.name} ${pct(c.ach)} dari target berjalan (${rp(c.actual)} / ${rp(c.target)})`, act: () => this.openList("sale.order", [["team_id", "=", c.id], ["state", "=", "sale"]], `Penjualan ${c.name}`) });
        for (const b of budgets) if (b.over) alerts.push({ level: "danger", icon: "fa-money", text: `${b.name} melewati anggaran: ${rp(b.actual)} dari budget ${rp(b.planned)} (${pct(b.used)})`, act: () => this.openList("crossovered.budget.lines", [], "Budget vs Realisasi") });
        for (const p of lowStock.filter((x) => x.best)) alerts.push({ level: "danger", icon: "fa-cubes", text: `Stok bestseller hampir habis: ${p.display_name} (sisa ${p.qty_available})`, act: () => this.openRecord("product.product", p.id) });
        for (const a of approvals) alerts.push({ level: a.x_over_budget ? "danger" : "warning", icon: "fa-check-square-o", text: `Butuh approval ${a.x_number}: ${a.x_name} (${rp(a.x_amount)})${a.x_over_budget ? " · MELEBIHI ANGGARAN" : ""} · menunggu ${a.x_approver_id ? a.x_approver_id[1] : "-"}`, act: () => this.openRecord("x_ss_approval", a.id) });
        for (const p of poApprove) alerts.push({ level: "warning", icon: "fa-check-square-o", text: `Butuh approval: ${p.name} - ${p.partner_id[1]} (${rp(p.amount_total)})`, act: () => this.openRecord("purchase.order", p.id) });
        for (const p of poLate) alerts.push({ level: "danger", icon: "fa-truck", text: `Supplier terlambat: ${p.name} - ${p.partner_id[1]} (jadwal ${p.date_planned.slice(0, 10)})`, act: () => this.openRecord("purchase.order", p.id) });
        for (const m of moLate) alerts.push({ level: "danger", icon: "fa-industry", text: `Produksi tidak sesuai jadwal: ${m.name} ${m.product_id[1]} (deadline ${m.date_deadline.slice(0, 10)})`, act: () => this.openRecord("mrp.production", m.id) });
        for (const l of expiring) alerts.push({ level: "warning", icon: "fa-hourglass-end", text: `Batch mendekati kedaluwarsa: ${l.name} ${l.product_id[1]} (${l.product_qty} pcs, exp ${(l.expiration_date || "").slice(0, 10)})`, act: () => this.openRecord("stock.lot", l.id) });
        if (fin.overdue > 0) alerts.push({ level: "warning", icon: "fa-clock-o", text: `Piutang jatuh tempo belum dibayar: ${rp(fin.overdue)}`, act: () => this.openList("account.move", [["move_type", "=", "out_invoice"], ["payment_state", "in", ["not_paid", "partial"]], ["invoice_date_due", "<", todayD], ["state", "=", "posted"]], "Piutang Jatuh Tempo") });
        if (hr.lateTasks) alerts.push({ level: "warning", icon: "fa-tasks", text: `${hr.lateTasks} pekerjaan melewati deadline (Creative, R&D, Legal, Event)`, act: () => this.openList("project.task", [["date_deadline", "<", nowDt], ["stage_id.fold", "=", false]], "Pekerjaan Terlambat") });
        const order = { danger: 0, warning: 1 };
        alerts.sort((a, b) => order[a.level] - order[b.level]);

        this.state.data = {
            r, label: r.label,
            sales: { total: salesTotal, orders: ordersTotal, target: targetTotal, ach: targetTotal ? (salesTotal / targetTotal) * 100 : 0, today: g0(todaySales, "amount_untaxed") + g0(posToday, "amount_total") - g0(posToday, "amount_tax"), todayCount: g0(todaySales, "__count") + g0(posToday, "__count"), aov: ordersTotal ? salesTotal / ordersTotal : 0, channels, trendBars, topProducts },
            live: { hosts: liveHosts, tot: liveTot },
            fin, budgets, mkt, ops, hr, alerts,
            approvals: { list: approvals, total: sum(approvals, (a) => a.x_amount), over: approvals.filter((a) => a.x_over_budget).length },
            filters: { soDom, fromD, toD, nowDt, todayD },
        };
        this.state.loading = false;
    }

    setPeriod(p) { this.state.period = p; this.load(); }
    openList(model, domain, name) {
        return this.action.doAction({ type: "ir.actions.act_window", name, res_model: model, domain, views: [[false, "list"], [false, "form"]], target: "current" });
    }
    openRecord(model, id) {
        return this.action.doAction({ type: "ir.actions.act_window", res_model: model, res_id: id, views: [[false, "form"]], target: "current" });
    }
    openSales(teamId) {
        const dom = [...this.state.data.filters.soDom];
        if (teamId) dom.push(["team_id", "=", teamId]);
        return this.openList("sale.order", dom, "Penjualan");
    }
    openLive() { return this.action.doAction({ type: "ir.actions.act_window", name: "Live Streaming", res_model: "x_ss_live_session", views: [[false, "list"], [false, "calendar"], [false, "pivot"], [false, "form"]], target: "current" }); }
    openPL() { return this.openList("account.move.line", [["parent_state", "=", "posted"], ["date", ">=", this.state.data.filters.fromD], ["date", "<", this.state.data.filters.toD], ["account_id.account_type", "in", ["income", "income_other", "expense", "expense_direct_cost", "expense_depreciation"]]], "Laba Rugi - Detail Jurnal"); }
    openReceivable() { return this.openList("account.move", [["move_type", "in", ["out_invoice", "out_refund"]], ["payment_state", "in", ["not_paid", "partial"]], ["state", "=", "posted"]], "Piutang"); }
    openPayable() { return this.openList("account.move", [["move_type", "in", ["in_invoice", "in_refund"]], ["payment_state", "in", ["not_paid", "partial"]], ["state", "=", "posted"]], "Utang Supplier"); }
    openMO() { return this.openList("mrp.production", [["state", "not in", ["done", "cancel"]]], "Produksi Berjalan"); }
    openPO() { return this.openList("purchase.order", [["state", "in", ["to approve", "purchase"]], ["receipt_status", "!=", "full"]], "Status PO"); }
    openPickings(typeId) { return this.openList("stock.picking", [["picking_type_id", "=", typeId], ["state", "in", ["assigned", "waiting", "confirmed"]]], "Aktivitas Gudang"); }
    openApprovals() { return this.openList("x_ss_approval", [["x_state", "=", "submitted"]], "Pengajuan Menunggu Approval"); }
    openStock() { return this.openList("stock.quant", [["location_id.usage", "=", "internal"]], "Stok Tersedia"); }
}

registry.category("actions").add("ss_executive_dashboard", SSExecutiveDashboard);
