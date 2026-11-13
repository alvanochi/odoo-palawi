/** @odoo-module */
import { ClosePosPopup } from "@point_of_sale/app/navbar/closing_popup/closing_popup";
import { patch } from "@web/core/utils/patch";

// Odoo only sends `default_cash_details.moves` when the POS config has a cash
// payment method. Without it, core's cashMoveData crashes on `.moves.reduce`.
patch(ClosePosPopup.prototype, {
    get cashMoveData() {
        if (!this.props.default_cash_details?.moves) {
            return [];
        }
        return super.cashMoveData;
    },
});
