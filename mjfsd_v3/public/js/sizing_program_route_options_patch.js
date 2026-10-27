/*
 * PATCH, not a full file.
 *
 * Apply to: mjfsd_v3/mjfsd_v3/loom_production/doctype/sizing_program/sizing_program.js
 *
 * Add two lines to the existing route_options block used by the
 * "Create > Sizing Receipt" button - this is the exact block on file in
 * the Towel project docs (claude/sizing-receipt.md, "Current mapping:
 * Sizing Program -> Sizing Receipt"), so this should be a direct match on
 * your site. Find this block:
 *
 *   frappe.route_options = {
 *       sizing_program: frm.doc.po_number,
 *       source_warehouse: frm.doc.source_warehouse,
 *       sizing_name: frm.doc.supplier,
 *       yarn_count: frm.doc.yarn_count,
 *       yarn_item: frm.doc.item,
 *       fabric_construction: frm.doc.fabric_construction,
 *       item: frm.doc.item_returnable,
 *       yarn_consumption_per_meter: frm.doc.yarn_consumption_per_meter,
 *       beam_no: cint(frm.doc.sizing_beam),
 *       ends: frm.doc.ends,
 *       beem_length: frm.doc.beam_length
 *   };
 *
 * and replace it with:
 */

frappe.route_options = {
	sizing_program: frm.doc.po_number,
	source_warehouse: frm.doc.source_warehouse,
	sizing_name: frm.doc.supplier,
	yarn_count: frm.doc.yarn_count,
	yarn_item: frm.doc.item,
	fabric_construction: frm.doc.fabric_construction,
	item: frm.doc.item_returnable,
	yarn_consumption_per_meter: frm.doc.yarn_consumption_per_meter,
	beam_no: cint(frm.doc.sizing_beam),
	ends: frm.doc.ends,
	beem_length: frm.doc.beam_length,
	weaving_contract: frm.doc.weaving_contract,
	sales_order: frm.doc.sales_order
};

/*
 * Only the last two lines are new (weaving_contract, sales_order) - both
 * fields now exist on Sizing Program (sales_order is the new custom field
 * in this delivery) and Sizing Receipt (weaving_contract is the new custom
 * field; sales_order already existed there since round 14), so this
 * carries both references straight through to the receipt with no other
 * changes needed on the Sizing Receipt side.
 *
 * If your live sizing_program.js has drifted from the block above since
 * round 6 (2026-09-09), paste back your current route_options block and
 * I'll merge these two lines into your actual version instead.
 */
