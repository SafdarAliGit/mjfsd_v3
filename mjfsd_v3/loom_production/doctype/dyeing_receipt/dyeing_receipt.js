frappe.ui.form.on("Dyeing Receipt", {
	refresh(frm) {
		if (frm.doc.docstatus === 0) {
			frm.add_custom_button(
				__("Dyeing Contract"),
				() => open_dyeing_contract_dialog(frm),
				__("Get Items From")
			);
		}
		if (frm.doc.docstatus === 1) {
			frm.add_custom_button(
				__("Dyed Fabric Issuance"),
				() => create_dyed_fabric_issuance(frm),
				__("Create")
			);
		}
	},

	items_remove(frm) {
		recalc_parent_total(frm);
	}
});

frappe.ui.form.on("Dyeing Receipt Item", {
	received_qty(frm, cdt, cdn) {
		recalc_finish_weight(frm, cdt, cdn);
		recalc_parent_total(frm);
	}
});

function recalc_finish_weight(frm, cdt, cdn) {
	// Live preview only - Dyeing Receipt's own validate() recomputes this
	// authoritatively on save regardless, same "server is the source of
	// truth" pattern used everywhere else in this project.
	let row = locals[cdt][cdn];
	if (!row.towel_costing_sheet || !row.item) {
		return;
	}
	frappe.call({
		method: "mjfsd_v3.loom_production.events.create_dyeing_receipt.get_tcs_finish_weight",
		args: { towel_costing_sheet: row.towel_costing_sheet, item_code: row.item },
		callback: (r) => {
			let tcs_finish_weight = flt(r.message);
			let finish_weight = (tcs_finish_weight / 1000) * flt(row.received_qty);
			frappe.model.set_value(cdt, cdn, "finish_weight", finish_weight);
			// 2026-09-28 (feature v3) - "calculate weight as following
			// ((Pcs * finish weight mentioned in TCS)/1000)*2.2046 ...
			// amount = dyeing rate * weight (lbs)" (your words). Was
			// Rate x Received Qty (Pcs) - fixed to match the server
			// (dyeing_receipt.py recalculate_totals), which this had
			// drifted from.
			let weight_lbs = finish_weight * 2.2046;
			frappe.model.set_value(cdt, cdn, "weight_received_lbs", weight_lbs);
			frappe.model.set_value(cdt, cdn, "amount", flt(row.rate) * weight_lbs);
		}
	});
}

function open_dyeing_contract_dialog(frm) {
	frappe.call({
		method: "mjfsd_v3.loom_production.events.create_dyeing_receipt.get_dyeing_contracts_for_selection",
		callback: (r) => {
			let contracts = r.message || [];
			if (!contracts.length) {
				frappe.msgprint(__("No submitted Dyeing Contracts are available to receive from."));
				return;
			}

			let options = contracts.map((c) => ({
				label: `${c.name} — ${c.supplier || __("(no Supplier)")}`,
				value: c.name,
				checked: 0
			}));

			let dialog = new frappe.ui.Dialog({
				title: __("Get Items From Dyeing Contract"),
				fields: [
					{
						fieldname: "dyeing_contracts",
						fieldtype: "MultiCheck",
						label: __("Dyeing Contracts"),
						options: options,
						columns: 1,
						reqd: 1
					}
				],
				primary_action_label: __("Fetch"),
				primary_action: (values) => {
					let selected = values.dyeing_contracts || [];
					if (!selected.length) {
						frappe.msgprint(__("Select at least one Dyeing Contract."));
						return;
					}
					frappe.call({
						method: "mjfsd_v3.loom_production.events.create_dyeing_receipt.get_dyeing_contract_items",
						args: { dyeing_contracts: selected },
						callback: (res) => {
							let rows = res.message || [];
							rows.forEach((data, i) => {
								frm.add_child("items", data);
								if (i === 0) {
									// Warehouses default off the first contract fetched -
									// not in your original field list, needed for the Repack
									// entry (see the field's own description). Review/adjust
									// if a single Dyeing Receipt shouldn't mix contracts with
									// different warehouses.
									if (!frm.doc.source_warehouse) {
										frm.set_value("source_warehouse", data.source_warehouse);
									}
									if (!frm.doc.target_warehouse) {
										frm.set_value("target_warehouse", data.target_warehouse);
									}
								}
							});
							frm.refresh_field("items");
							recalc_parent_total(frm);

							// 2026-09-28 (feature v3) - "same issues occur in
							// Dyeing Contract, user can select different
							// supplier in Dyeing Receipt" (your words). Only
							// set/locked when every selected contract agrees
							// on the supplier - same rule as Weaving
							// Receipt's weaver.
							let suppliers = [...new Set(rows.map((d) => d.supplier).filter(Boolean))];
							if (suppliers.length === 1) {
								frm.set_value("supplier", suppliers[0]);
								frm.set_df_property("supplier", "read_only", 1);
							} else {
								frm.set_df_property("supplier", "read_only", 0);
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

function create_dyed_fabric_issuance(frm) {
	frappe.call({
		method: "mjfsd_v3.loom_production.events.create_dyed_fabric_issuance.create_dyed_fabric_issuance_from_dyeing_receipt",
		args: { dyeing_receipt: frm.doc.name },
		freeze: true,
		callback: (r) => {
			if (!r.message) return;
			let doc = r.message;
			frappe.model.sync(doc);
			frappe.set_route("Form", doc.doctype, doc.name);
		}
	});
}

function recalc_parent_total(frm) {
	let total = 0;
	(frm.doc.items || []).forEach((row) => {
		total += flt(row.received_qty);
	});
	frm.set_value("total_received_qty", total);
}
