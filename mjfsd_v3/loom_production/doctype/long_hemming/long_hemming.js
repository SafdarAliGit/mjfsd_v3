frappe.ui.form.on("Long Hemming", {
	refresh(frm) {
		frm.toggle_reqd("b_qty_warehouse", frm.doc.transfer_b_qty);

		// 2026-09-26 - next (last) workstation
		if (frm.doc.docstatus === 1) {
			frm.add_custom_button(
				__("Stitching and Finishing"),
				() => create_stitching_and_finishing(frm),
				__("Create")
			);
		}
	},

	transfer_b_qty(frm) {
		frm.toggle_reqd("b_qty_warehouse", frm.doc.transfer_b_qty);
	},

	hemming_rate(frm) {
		recalc_hemming_amount(frm);
	}
});

frappe.ui.form.on("Long Hemming Item", {
	a_qty(frm) {
		recalc_hemming_amount(frm);
	},
	b_qty(frm) {
		recalc_hemming_amount(frm);
	}
});

// Live preview only - recalculated on the server on save.
function recalc_hemming_amount(frm) {
	let total = 0;
	(frm.doc.items || []).forEach((row) => {
		total += flt(row.a_qty) + flt(row.b_qty);
	});
	frm.set_value("total_hemming_amount", flt(frm.doc.hemming_rate) * total);
}

function create_stitching_and_finishing(frm) {
	frappe.call({
		method: "mjfsd_v3.loom_production.events.stitching_and_finishing.create_stitching_and_finishing_from_long_hemming",
		args: { long_hemming: frm.doc.name },
		freeze: true,
		callback: (r) => {
			if (!r.message) return;
			frappe.model.sync(r.message);
			frappe.set_route("Form", r.message.doctype, r.message.name);
		}
	});
}
