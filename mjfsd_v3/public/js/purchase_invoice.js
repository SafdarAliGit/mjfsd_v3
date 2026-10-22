// New file (mjfsd_v3 app). Adds a "Get Charges From Sizing Receipt" button to
// Purchase Invoice: picks a charge Item once, lets the user check off one
// or more of the invoice's Supplier's submitted-but-not-yet-invoiced Sizing
// Receipts, and appends one Purchase Invoice Item row per receipt checked -
// qty = that receipt's LBS, rate = that receipt's Sizing Rate, uom = "Lbs"
// (the charge is billed per LBS sized, regardless of the item's own stock
// UOM). Each created row remembers which Sizing Receipt it came from
// (custom_sizing_receipt, a new hidden-ish Purchase Invoice Item field) so
// the same receipt can't be pulled into a second invoice later.

frappe.ui.form.on('Purchase Invoice', {
	refresh: function (frm) {
		if (frm.doc.docstatus !== 0) {
			return;
		}

		frm.add_custom_button(__('Get Charges From Sizing Receipt'), function () {
			open_sizing_receipt_dialog(frm);
		}).css('background-color', '#6f42c1').css('color', '#ffffff').css('font-weight', 'bold');
	}
});

function open_sizing_receipt_dialog(frm) {
	if (!frm.doc.supplier) {
		frappe.msgprint(__('Set Supplier on this Purchase Invoice first.'));
		return;
	}

	frappe.call({
		method:
			'mjfsd_v3.loom_production.events.get_sizing_receipts_for_purchase_invoice.get_sizing_receipts_for_supplier',
		args: { supplier: frm.doc.supplier },
		freeze: true,
		callback: function (r) {
			const receipts = r.message || [];
			if (!receipts.length) {
				frappe.msgprint(
					__('No submitted Sizing Receipts found for {0} that are not already on another invoice.').format(
						frm.doc.supplier
					)
				);
				return;
			}
			show_sizing_receipt_dialog(frm, receipts);
		}
	});
}

function show_sizing_receipt_dialog(frm, receipts) {
	const dialog = new frappe.ui.Dialog({
		title: __('Get Charges From Sizing Receipt'),
		fields: [
			{
				fieldname: 'charge_item',
				fieldtype: 'Link',
				options: 'Item',
				label: __('Sizing Charges Item'),
				reqd: 1,
				description: __('This item is used on every row created below - qty is billed in Lbs.')
			},
			{
				fieldname: 'section_break_receipts',
				fieldtype: 'Section Break',
				label: __('Sizing Receipts')
			},
			{
				fieldname: 'sizing_receipts',
				fieldtype: 'MultiCheck',
				label: __('Select Sizing Receipts'),
				options: receipts.map((sr) => ({
					label: `${sr.name} — ${sr.beam_item || sr.yarn_item} — ${flt(sr.lbs).toFixed(2)} Lbs @ ${flt(sr.sizing_rate).toFixed(2)}`,
					value: sr.name,
					checked: 0
				})),
				columns: 1
			}
		],
		primary_action_label: __('Create Rows'),
		primary_action: function (values) {
			const selected = values.sizing_receipts || [];
			if (!selected.length) {
				frappe.msgprint(__('Select at least one Sizing Receipt.'));
				return;
			}

			selected.forEach((name) => {
				const sr = receipts.find((r) => r.name === name);
				if (!sr) {
					return;
				}
				const row = frm.add_child('items');
				frappe.model.set_value(row.doctype, row.name, 'item_code', values.charge_item);
				frappe.model.set_value(row.doctype, row.name, 'qty', flt(sr.lbs));
				frappe.model.set_value(row.doctype, row.name, 'uom', 'Lbs');
				frappe.model.set_value(row.doctype, row.name, 'rate', flt(sr.sizing_rate));
				frappe.model.set_value(row.doctype, row.name, 'custom_sizing_receipt', sr.name);
			});

			frm.refresh_field('items');
			dialog.hide();
		}
	});

	dialog.show();
}
