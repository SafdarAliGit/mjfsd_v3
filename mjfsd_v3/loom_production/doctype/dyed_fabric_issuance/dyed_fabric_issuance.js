frappe.ui.form.on("Dyed Fabric Issuance", {
	refresh(frm) {
		if (frm.doc.docstatus === 0) {
			frm.add_custom_button(
				__("Dyeing Receipt"),
				() => open_dyeing_receipt_dialog(frm),
				__("Get Items From")
			);
		}
		if (frm.doc.docstatus === 1) {
			frm.add_custom_button(
				__("Long Hemming"),
				() => create_long_hemming(frm),
				__("Create")
			);
		}
	},

	items_remove(frm) {
		recalc_parent_total(frm);
	}
});

frappe.ui.form.on("Dyed Fabric Issuance Item", {
	pcs(frm) {
		recalc_parent_total(frm);
	}
});

function open_dyeing_receipt_dialog(frm) {
	frappe.call({
		method: "mjfsd_v3.loom_production.events.create_dyed_fabric_issuance.get_dyeing_receipts_for_selection",
		callback: (r) => {
			let receipts = r.message || [];
			if (!receipts.length) {
				frappe.msgprint(__("No submitted Dyeing Receipts are available."));
				return;
			}

			let options = receipts.map((d) => ({
				label: `${d.name} — ${d.supplier || __("(no Supplier)")} (${d.date || ""})`,
				value: d.name,
				checked: 0
			}));

			let dialog = new frappe.ui.Dialog({
				title: __("Get Items From Dyeing Receipt"),
				fields: [
					{
						fieldname: "dyeing_receipts",
						fieldtype: "MultiCheck",
						label: __("Dyeing Receipts"),
						options: options,
						columns: 1,
						reqd: 1
					}
				],
				primary_action_label: __("Fetch"),
				primary_action: (values) => {
					let selected = values.dyeing_receipts || [];
					if (!selected.length) {
						frappe.msgprint(__("Select at least one Dyeing Receipt."));
						return;
					}
					frappe.call({
						method: "mjfsd_v3.loom_production.events.create_dyed_fabric_issuance.get_dyeing_receipt_items",
						args: { dyeing_receipts: selected },
						callback: (res) => {
							let rows = res.message || [];
							if (!rows.length) {
								frappe.msgprint(
									__(
										"Nothing left to issue on the selected Dyeing Receipt(s) - everything may already be on another Dyed Fabric Issuance."
									)
								);
								return;
							}
							rows.forEach((data) => frm.add_child("items", data));
							frm.refresh_field("items");
							recalc_parent_total(frm);
							dialog.hide();
						}
					});
				}
			});
			dialog.show();
		}
	});
}

function create_long_hemming(frm) {
	frappe.call({
		method: "mjfsd_v3.loom_production.events.create_long_hemming.create_long_hemming_from_dyed_fabric_issuance",
		args: { dyed_fabric_issuance: frm.doc.name },
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
		total += flt(row.pcs);
	});
	frm.set_value("total_fabric_issued", total);
}
