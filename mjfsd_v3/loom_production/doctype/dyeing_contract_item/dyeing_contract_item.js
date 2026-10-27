// Live preview only - Dyeing Contract's own validate() (recalculate_totals
// in dyeing_contract.py) is the authoritative source, same "server is the
// source of truth" pattern used everywhere else in this project. Added
// 2026-09-15: Order Qty became user-editable (was previously locked to
// whatever 'Create Dyeing Contract' fetched off the Sales Order), and
// Amount had never actually been wired up to recompute from Rate x Order
// Qty despite its own description saying so - both fixed together here.
frappe.ui.form.on("Dyeing Contract Item", {
	order_qty(frm, cdt, cdn) {
		recalc_amount(frm, cdt, cdn);
	},
	rate(frm, cdt, cdn) {
		recalc_amount(frm, cdt, cdn);
	}
});

function recalc_amount(frm, cdt, cdn) {
	let row = locals[cdt][cdn];
	frappe.model.set_value(cdt, cdn, "amount", flt(row.rate) * flt(row.order_qty));
}
