// Stitching and Finishing - see mjfsd_v3/loom_production/events/stitching_and_finishing.py
// Totals / Total Ctn / Trims Qty Required are recalculated on the server on
// every save; the functions below are only a live preview while typing.

frappe.ui.form.on("Stitching and Finishing", {
	refresh(frm) {
		if (frm.doc.docstatus === 0) {
			frm.add_custom_button(
				__("Long Hemming"),
				() => get_items_from_long_hemming(frm),
				__("Get Items From")
			);
			frm.add_custom_button(__("Refresh Trims from TCS"), () => {
				frm.call({ method: "refresh_trims_from_tcs", doc: frm.doc, freeze: true }).then(() => {
					frm.dirty();
					frm.refresh_fields();
				});
			});
		}
		frm.set_query("finish_item", "items", () => ({ filters: { is_stock_item: 1 } }));
	},
	items_remove(frm) {
		recalc_all(frm);
	}
});

frappe.ui.form.on("Stitching and Finishing Item", {
	a_qty: recalc_all,
	b_qty: recalc_all,
	pcs_per_pack: recalc_all,
	pack_per_ctn: recalc_all
});

frappe.ui.form.on("Stitching and Finishing Trim", {
	consumed_qty: recalc_all,
	consumption_unit: recalc_all
});

function get_items_from_long_hemming(frm) {
	frappe.prompt(
		[{
			fieldname: "long_hemming",
			label: __("Long Hemming"),
			fieldtype: "Link",
			options: "Long Hemming",
			reqd: 1,
			get_query: () => ({ filters: { docstatus: 1 } })
		}],
		(values) => {
			frm.call({
				method: "get_items_from_long_hemming",
				doc: frm.doc,
				args: { long_hemming: values.long_hemming },
				freeze: true
			}).then(() => {
				frm.dirty();
				frm.refresh_fields();
			});
		},
		__("Get Items From Long Hemming"),
		__("Fetch")
	);
}

function total_ctn(qty, pcs_per_pack, pack_per_ctn) {
	let per_ctn = flt(pcs_per_pack) * flt(pack_per_ctn);
	return per_ctn ? flt(qty) / per_ctn : 0;
}

function trim_qty(trim, row) {
	let total = flt(row.a_qty) + flt(row.b_qty);
	let consumed = flt(trim.consumed_qty);
	switch ((trim.consumption_unit || "").trim()) {
		case "Per Pcs":
			return consumed * total;
		case "Per Pack":
			return flt(row.pcs_per_pack) ? (consumed * total) / flt(row.pcs_per_pack) : 0;
		case "Per Ctn":
			return consumed * total_ctn(total, row.pcs_per_pack, row.pack_per_ctn);
	}
	return 0;
}

function recalc_all(frm) {
	let total_a = 0, total_b = 0, ctn = 0;
	(frm.doc.items || []).forEach((row) => {
		row.total_qty = flt(row.a_qty) + flt(row.b_qty);
		row.total_ctn = total_ctn(row.total_qty, row.pcs_per_pack, row.pack_per_ctn);
		total_a += flt(row.a_qty);
		total_b += flt(row.b_qty);
		ctn += flt(row.total_ctn);
	});
	(frm.doc.trims || []).forEach((trim) => {
		let qty = 0;
		(frm.doc.items || []).forEach((row) => {
			if (row.finish_item !== trim.finish_item) return;
			if (trim.towel_costing_sheet && row.towel_costing_sheet && trim.towel_costing_sheet !== row.towel_costing_sheet) return;
			qty += trim_qty(trim, row);
		});
		trim.qty_required = qty;
	});
	frm.doc.total_a_qty = total_a;
	frm.doc.total_b_qty = total_b;
	frm.doc.total_qty = total_a + total_b;
	frm.doc.total_ctn = ctn;
	frm.refresh_fields(["items", "trims", "total_a_qty", "total_b_qty", "total_qty", "total_ctn"]);
}
