frappe.ui.form.on("Weaving Receipt", {
	refresh(frm) {
		if (frm.doc.docstatus === 0) {
			frm.add_custom_button(
				__("Weaving Contract"),
				() => open_weaving_contract_dialog(frm),
				__("Get Items From")
			);
		}
	},

	items_remove(frm) {
		recalc_parent_totals(frm);
	},

	details_remove(frm) {
		recalc_parent_totals(frm);
	}
});

frappe.ui.form.on("Weaving Receipt Item", {
	no_of_rolls(frm, cdt, cdn) {
		maybe_generate_rolls(frm, cdt, cdn);
	},
	pcs_challan(frm, cdt, cdn) {
		maybe_generate_rolls(frm, cdt, cdn);
	},
	weight_challan(frm, cdt, cdn) {
		maybe_generate_rolls(frm, cdt, cdn);
	}
});

frappe.ui.form.on("Weaving Receipt Detail", {
	a_pcs(frm, cdt, cdn) {
		recalc_detail_row(frm, cdt, cdn);
	},
	b_pcs(frm, cdt, cdn) {
		recalc_detail_row(frm, cdt, cdn);
	},
	c_pcs(frm, cdt, cdn) {
		recalc_detail_row(frm, cdt, cdn);
	},
	cut_pcs(frm, cdt, cdn) {
		recalc_detail_row(frm, cdt, cdn);
	},
	weight(frm, cdt, cdn) {
		recalc_detail_row(frm, cdt, cdn);
	}
});

function open_weaving_contract_dialog(frm) {
	frappe.call({
		method: "mjfsd_v3.loom_production.events.create_weaving_receipt.get_weaving_contracts_for_selection",
		callback: (r) => {
			let contracts = r.message || [];
			if (!contracts.length) {
				frappe.msgprint(__("No submitted Weaving Contracts are available to receive from."));
				return;
			}

			let options = contracts.map((c) => ({
				label: `${c.name} — ${c.finish_item || __("(no Finish Item)")} `
					+ `(${c.weaver_hint || __("Weaver n/a")}, balance ${format_number(c.balance_qty)} pcs)`,
				value: c.name,
				checked: 0
			}));

			let dialog = new frappe.ui.Dialog({
				title: __("Get Items From Weaving Contract"),
				fields: [
					{
						fieldname: "weaving_contracts",
						fieldtype: "MultiCheck",
						label: __("Weaving Contracts"),
						options: options,
						columns: 1,
						reqd: 1
					}
				],
				primary_action_label: __("Fetch"),
				primary_action: (values) => {
					let selected = values.weaving_contracts || [];
					if (!selected.length) {
						frappe.msgprint(__("Select at least one Weaving Contract."));
						return;
					}
					frappe.call({
						method: "mjfsd_v3.loom_production.events.create_weaving_receipt.get_weaving_contract_items",
						args: { weaving_contracts: selected },
						callback: (res) => {
							let rows = res.message || [];
							rows.forEach((data) => {
								frm.add_child("items", {
									finish_item: data.finish_item,
									gross_weight: data.gross_weight,
									finish_weight: data.finish_weight,
									order_qty: data.order_qty,
									weaving_contract: data.weaving_contract,
									sales_order: data.sales_order,
									towel_costing_sheet: data.towel_costing_sheet,
									row_key: make_row_key()
								});
							});
							frm.refresh_field("items");
							recalc_parent_totals(frm);

							// 2026-09-28 (feature v3) - "when user gets item
							// from Weaving Contract, the weaver should be
							// automatically fetched and set to read only"
							// (your words). Only set/locked when every
							// selected contract agrees on the weaver - a
							// receipt combining contracts from different
							// weavers is left editable rather than silently
							// picking one.
							let weavers = [...new Set(rows.map((d) => d.weaver).filter(Boolean))];
							if (weavers.length === 1) {
								frm.set_value("weaver", weavers[0]);
								frm.set_df_property("weaver", "read_only", 1);
							} else {
								frm.set_df_property("weaver", "read_only", 0);
							}

							// 2026-09-28 - "Source and Target warehouse is
							// also empty. The source warehouse will be
							// Supplier - PT by default and target warehouse
							// will be Finished Goods - PT" (your words).
							// Same fixed pair as the "Weaving Receipt"
							// button on Weaving Contract itself
							// (create_weaving_receipt_from_weaving_contract.py)
							// - only filled in if not already set, so it
							// never overwrites a value you picked yourself.
							if (!frm.doc.source_warehouse) {
								frm.set_value("source_warehouse", "Supplier - PT");
							}
							if (!frm.doc.target_warehouse) {
								frm.set_value("target_warehouse", "Finished Goods - PT");
							}

							dialog.hide();
						}
					});
				}
			});
			dialog.show();
		}
	});
}

// A child row's own `name` is only a temporary client-side value until
// the document is first saved - after that, Frappe replaces it with a
// permanent one, but any *other* field that had stored a copy of the old
// name (like Weaving Receipt Detail's item_row, previously set to
// row.name) is left pointing at a name that no longer exists. That's
// what was breaking the rollup after the first save: each roll's weight
// still displayed fine (it's just that row's own field), but it could no
// longer be matched back to its Items row, so Pcs (Actual)/Weight
// (Actual) - and everything downstream, including the Stock Entry's
// consumed qty on submit - silently stayed at 0. row_key is a plain
// value we generate and own ourselves, so it never changes.
function make_row_key() {
	return "rk-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 8);
}

// Fires as soon as No. of Rolls, Pcs (Challan) and Weight (Challan) are
// all filled on a row - not literally "moves to a new row" (Frappe's
// grid doesn't expose a reliable row-blur trigger at the field level),
// but functionally equivalent for the normal left-to-right fill order,
// and details_generated guards against firing twice on the same row.
function maybe_generate_rolls(frm, cdt, cdn) {
	let row = locals[cdt][cdn];
	if (row.details_generated) {
		return;
	}
	if (!row.no_of_rolls || !row.pcs_challan || !row.weight_challan) {
		return;
	}

	let n = cint(row.no_of_rolls);
	if (n <= 0) {
		return;
	}

	if (!row.row_key) {
		// Fallback for a row that didn't go through the Get Items From
		// dialog (e.g. added manually) and so never got a row_key yet.
		frappe.model.set_value(cdt, cdn, "row_key", make_row_key());
		row = locals[cdt][cdn];
	}

	for (let i = 1; i <= n; i++) {
		frm.add_child("details", {
			item_row: row.row_key,
			finish_item: row.finish_item,
			roll_no: i
		});
	}

	frappe.model.set_value(cdt, cdn, "details_generated", 1);
	frm.refresh_field("details");
	recalc_item_row_totals(frm, row.row_key);
}

function recalc_detail_row(frm, cdt, cdn) {
	let row = locals[cdt][cdn];
	let total_pcs = flt(row.a_pcs) + flt(row.b_pcs) + flt(row.c_pcs) + flt(row.cut_pcs);
	frappe.model.set_value(cdt, cdn, "total_pcs", total_pcs);
	frappe.model.set_value(cdt, cdn, "weight_per_pcs", total_pcs ? flt(row.weight) / total_pcs : 0);
	recalc_item_row_totals(frm, row.item_row);
}

function recalc_item_row_totals(frm, row_key) {
	let item_row = (frm.doc.items || []).find((r) => r.row_key === row_key);
	if (!item_row) {
		return;
	}

	let rows = (frm.doc.details || []).filter((d) => d.item_row === row_key);
	let pcs_actual = 0;
	let weight_actual = 0;
	rows.forEach((d) => {
		pcs_actual += flt(d.total_pcs);
		weight_actual += flt(d.weight);
	});

	frappe.model.set_value(item_row.doctype, item_row.name, "pcs_actual", pcs_actual);
	frappe.model.set_value(item_row.doctype, item_row.name, "weight_actual", weight_actual);
	recalc_parent_totals(frm);
}

// Sums straight off Weaving Receipt Details (the ground truth for Total
// Pcs Received/Total Weight (Actual), per their own field descriptions)
// rather than off Items' pcs_actual/weight_actual - avoids depending on
// those two set_value calls above having already landed in frm.doc by
// the time this runs.
function recalc_parent_totals(frm) {
	let total_pcs_received = 0;
	let total_weight_actual = 0;
	(frm.doc.details || []).forEach((d) => {
		total_pcs_received += flt(d.total_pcs);
		total_weight_actual += flt(d.weight);
	});

	let total_weight_challan = 0;
	(frm.doc.items || []).forEach((r) => {
		total_weight_challan += flt(r.weight_challan);
	});

	frm.set_value("total_pcs_received", total_pcs_received);
	frm.set_value("total_weight_challan", total_weight_challan);
	frm.set_value("total_weight_actual", total_weight_actual);
}