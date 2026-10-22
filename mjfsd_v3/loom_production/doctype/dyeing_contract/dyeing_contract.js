frappe.ui.form.on("Dyeing Contract", {
	refresh(frm) {
		if (frm.doc.docstatus === 1) {
			frm.add_custom_button(__("Issue Fabric"), () => open_issue_fabric_dialog(frm));
			// New 2026-09-15 - same "create a prefilled draft and route to
			// it" pattern already used by Weaving Contract's own "Weaving
			// Receipt" button, reusing Dyeing Receipt's existing
			// Get-Items-From-Dyeing-Contract row-building logic so both
			// paths stay consistent.
			frm.add_custom_button(__("Dyeing Receipt"), () => create_dyeing_receipt(frm), __("Create"));
			// New 2026-09-16 - self-heals Issued Qty/Rolls/Weight from a
			// live query against actually-submitted Stock Entries every
			// time this form loads, instead of only ever trusting the
			// on_submit-hook-maintained accumulator (which needs a
			// hooks.py entry that hasn't been confirmed wired). Silent
			// no-op if the numbers are already correct.
			sync_issued_totals(frm);
		}
	}
});

function sync_issued_totals(frm) {
	frappe.call({
		method: "mjfsd_v3.loom_production.events.issue_fabric.sync_issued_totals",
		args: { dyeing_contract: frm.doc.name },
		callback: (r) => {
			if (r.message && r.message.changed) {
				frm.reload_doc();
			}
		}
	});
}

function create_dyeing_receipt(frm) {
	frappe.call({
		method: "mjfsd_v3.loom_production.events.create_dyeing_receipt.create_dyeing_receipt_from_dyeing_contract",
		args: { dyeing_contract: frm.doc.name },
		freeze: true,
		callback: (r) => {
			if (!r.message) return;
			frappe.model.sync(r.message);
			frappe.set_route("Form", r.message.doctype, r.message.name);
		}
	});
}

function open_issue_fabric_dialog(frm) {
	let rows = (frm.doc.items || []).map((row) => {
		let remaining = flt(row.order_qty) - flt(row.issued_qty);
		return {
			row_name: row.name,
			item: row.item,
			color: row.color,
			order_qty: row.order_qty,
			issued_qty: row.issued_qty,
			remaining: remaining
		};
	});

	if (!rows.length) {
		frappe.msgprint(__("No items on this Dyeing Contract."));
		return;
	}

	let dialog = new frappe.ui.Dialog({
		title: __("Issue Fabric"),
		size: "large",
		fields: [
			{
				fieldname: "items_html",
				fieldtype: "HTML"
			}
		],
		primary_action_label: __("Issue"),
		primary_action: () => {
			// Scoped to THIS dialog's own wrapper (dialog.$wrapper), not a
			// bare global $('#...') lookup - a Dialog stays in the DOM
			// (hidden) after it's closed rather than being removed, so a
			// global id-based lookup could silently grab a stale input
			// left over from an earlier time this dialog was opened,
			// instead of the one you just typed into. Scoping to this
			// dialog instance's own wrapper rules that out entirely.
			let entries = rows
				.map((r) => {
					let $row = dialog.$wrapper.find(`[data-row-name="${r.row_name}"]`);
					return {
						row_name: r.row_name,
						qty: flt($row.find('[data-field="qty"]').val()),
						no_of_rolls: flt($row.find('[data-field="no_of_rolls"]').val()),
						weight_kgs: flt($row.find('[data-field="weight_kgs"]').val())
					};
				})
				.filter((e) => e.qty > 0);

			if (!entries.length) {
				frappe.msgprint(__("Enter a qty to issue for at least one item."));
				return;
			}

			frappe.call({
				method: "mjfsd_v3.loom_production.events.issue_fabric.issue_fabric",
				args: {
					dyeing_contract: frm.doc.name,
					rows: entries
				},
				freeze: true,
				callback: (r) => {
					if (!r.message) {
						return;
					}
					dialog.hide();
					// 2026-09-15 (feature v3) - issue_fabric() now only
					// inserts a draft Stock Entry instead of submitting it
					// ("stock entry form gets opened in Stock Entry and he
					// submits it manually" - your words). Route to it
					// instead of showing an alert + reloading this form.
					frappe.model.sync(r.message);
					frappe.set_route("Form", r.message.doctype, r.message.name);
				}
			});
		}
	});

	let rows_html = rows
		.map(
			(r) => `
		<tr data-row-name="${frappe.utils.escape_html(r.row_name)}">
			<td>${frappe.utils.escape_html(r.item)}</td>
			<td>${frappe.utils.escape_html(r.color || "")}</td>
			<td class="text-right">${format_number(r.order_qty)}</td>
			<td class="text-right">${format_number(r.issued_qty)}</td>
			<td class="text-right">${format_number(r.remaining)}</td>
			<td><input type="number" step="any" class="form-control" data-field="qty" value="0"></td>
			<td><input type="number" step="any" class="form-control" data-field="no_of_rolls" value="0"></td>
			<td><input type="number" step="any" class="form-control" data-field="weight_kgs" value="0"></td>
		</tr>`
		)
		.join("");

	dialog.fields_dict.items_html.$wrapper.html(`
		<div style="overflow-x:auto">
		<table class="table table-bordered">
			<thead>
				<tr>
					<th>${__("Item")}</th>
					<th>${__("Color")}</th>
					<th class="text-right">${__("Order Qty")}</th>
					<th class="text-right">${__("Issued So Far")}</th>
					<th class="text-right">${__("Remaining")}</th>
					<th>${__("Qty To Issue")}</th>
					<th>${__("No. of Rolls")}</th>
					<th>${__("Weight (Kgs)")}</th>
				</tr>
			</thead>
			<tbody>${rows_html}</tbody>
		</table>
		</div>
	`);

	dialog.show();
}