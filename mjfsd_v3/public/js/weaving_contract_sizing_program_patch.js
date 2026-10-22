/*
 * PATCH, not a full file - see CHANGES.md for why.
 *
 * Apply to: emadi_v3/emadi_v3/emadi/doctype/weaving_contract/weaving_contract.js
 *
 * STEP 1 - find your existing "Sizing Program" button. It's the one that
 * currently calls:
 *
 *   emadi_v3.emadi.events.create_sizing_program_from_weaving_contract.create_sizing_program_from_weaving_contract
 *
 * with just `{ weaving_contract: frm.doc.name }`, shown when
 * `frm.doc.docstatus == 1 && frm.doc.custom_status == "Open"`. Whatever the
 * exact button code looks like on your site, replace ONLY its click handler
 * body with a call to the new function below - keep your existing
 * add_custom_button(...) call, label and the docstatus/custom_status
 * condition exactly as they are. For example, if it currently reads:
 *
 *   frm.add_custom_button("Sizing Program", () => {
 *       frappe.call({
 *           method: "emadi_v3.emadi.events.create_sizing_program_from_weaving_contract.create_sizing_program_from_weaving_contract",
 *           args: { weaving_contract: frm.doc.name },
 *           callback: (r) => {
 *               if (!r.exc && r.message) {
 *                   frappe.model.sync(r.message);
 *                   frappe.set_route("Form", r.message.doctype, r.message.name);
 *               }
 *           }
 *       });
 *   });
 *
 * change the handler body to just:
 *
 *   frm.add_custom_button("Sizing Program", () => {
 *       open_sizing_program_dialog(frm);
 *   });
 *
 * (keeping wherever this sits inside your docstatus==1/custom_status=="Open"
 * block, and whatever button group it's already under.)
 *
 * STEP 2 - add these two functions anywhere in the file at the top level
 * (alongside your existing get_items_from_sales_order / pick_sales_order_item
 * / apply_sales_order_item / calculate_total functions):
 */

function open_sizing_program_dialog(frm) {
	let rows = (frm.doc.bom_items || []).filter(
		(r) => ["Pile", "Ground"].includes(r.for) && r.yarn_count
	);

	if (!rows.length) {
		frappe.msgprint(__("No Pile/Ground item with a Yarn Count found in this Weaving Contract's BOM Items."));
		return;
	}

	let options = [];
	let by_label = {};
	rows.forEach((r) => {
		let label = `${r.for} - ${r.yarn_count}`;
		// guard against two rows sharing the same for/yarn_count pair
		if (by_label[label]) {
			label = `${label} (row ${r.idx})`;
		}
		options.push(label);
		by_label[label] = r;
	});

	frappe.prompt(
		[
			{
				fieldname: "bom_item",
				label: __("Pile / Ground Item"),
				fieldtype: "Select",
				options: options,
				reqd: 1
			}
		],
		(values) => {
			let row = by_label[values.bom_item];
			create_sizing_program_from_row(frm, row);
		},
		__("Create Sizing Program"),
		__("Create")
	);
}

function create_sizing_program_from_row(frm, row) {
	frappe.call({
		method: "emadi_v3.emadi.events.create_sizing_program_from_weaving_contract.create_sizing_program_from_weaving_contract",
		args: {
			weaving_contract: frm.doc.name,
			item: row.yarn_count,
			beam_for: row.for
		},
		callback: (r) => {
			if (!r.exc && r.message) {
				frappe.model.sync(r.message);
				frappe.set_route("Form", r.message.doctype, r.message.name);
			}
		}
	});
}

/*
 * That's the whole patch - everything else in weaving_contract.js (Get
 * Items From Sales Order, calculate_total, the BOM Items child handlers,
 * the other buttons) is untouched.
 *
 * If your actual button code doesn't match the shape assumed in STEP 1
 * closely enough to edit by eye, paste back just that one
 * add_custom_button(...) block and I'll give you the exact replacement
 * instead of this find-and-replace version.
 */
