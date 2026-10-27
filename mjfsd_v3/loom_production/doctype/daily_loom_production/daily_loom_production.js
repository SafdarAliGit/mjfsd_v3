// Copyright (c) 2026, Tech Ventures and contributors
// For license information, please see license.txt

// Round 14 Part B (2026-09-09): see claude/daily-towel-production.md for
// the full spec this was built against.
//
// Round 19 (2026-09-16) NOTE: unlike round 18's events-file rewrite,
// Kabeer's round 18 paste confirmed this specific file was unchanged from
// this history at that point - but this round's change (warehouse
// defaults in the Raw Material Selection dialog) needs to land in the
// dialog-building code below, and a fresh live copy wasn't re-pasted this
// round. Rebuilt from the documented spec plus the one change described
// under "Round 19" below - the rest (item query, Total Finish Qty
// rollup) should match what's already live; flag anything that's drifted
// so it can be reconciled against your real file.
//
// Round 19 change: the Raw Material Selection dialog's Source Warehouse
// field now arrives pre-filled (Beam Items -> the Sizing Receipt's own
// Target Warehouse, via the new `default_warehouse` the Python side now
// returns; Yarn Items -> "Stores - PT") instead of blank - still a plain
// editable Link field, not read-only, per Kabeer: "yarn item warehouse
// will be Stores - PT by default but editable."
//
// 2026-09-28 (feature v3): doctype renamed "Daily Towel Production" ->
// "Daily Loom Production" (your words) - this file itself is unchanged
// other than the event binding's name below; the events module it calls
// into (create_stock_entry_from_daily_towel_production.py) still has its
// old name/path, on purpose - see the controller .py's own note.

frappe.ui.form.on('Daily Loom Production', {
	refresh: function (frm) {
		toggle_commercial(frm);
		frm.set_query('weaver', 'items', function () {
			return { filters: { supplier_group: 'Weaver' } };
		});
		['pile', 'ground'].forEach(function (type) {
			frm.set_query(type + '_beam', 'items', function () {
				return {
					query: 'mjfsd_v3.loom_production.events.create_stock_entry_from_daily_towel_production.get_beam_batches',
					filters: { beam_type: type === 'pile' ? 'Pile' : 'Ground' }
				};
			});
		});
		frm.set_query('weaving_contract', 'items', function () {
			return { filters: { docstatus: 1, custom_status: 'Open' } };
		});
		frm.set_query('item', 'items', function (doc, cdt, cdn) {
			const row = locals[cdt][cdn];
			// Commercial rows have no Sales Order - any item (it is filled
			// from the Weaving Contract's Finish Item anyway).
			if (frm.doc.commercial) {
				return {};
			}
			return {
				query: 'mjfsd_v3.loom_production.events.create_stock_entry_from_daily_towel_production.get_sales_order_items',
				filters: {
					sales_order: row.sales_order
				}
			};
		});
	},
	commercial: function (frm) {
		toggle_commercial(frm);
	},
	shift: function (frm) {
		(frm.doc.items || []).forEach(function (row) {
			recalc_metrics(frm, row.doctype, row.name);
		});
	}
});

// Commercial: rows use a Weaving Contract; otherwise a Sales Order.
function toggle_commercial(frm) {
	const grid = frm.fields_dict.items && frm.fields_dict.items.grid;
	if (!grid) {
		return;
	}
	const commercial = frm.doc.commercial ? 1 : 0;
	grid.update_docfield_property('sales_order', 'reqd', commercial ? 0 : 1);
	grid.update_docfield_property('sales_order', 'hidden', commercial);
	grid.update_docfield_property('weaving_contract', 'reqd', commercial);
	grid.update_docfield_property('weaving_contract', 'hidden', commercial ? 0 : 1);
	frm.refresh_field('items');
}

frappe.ui.form.on('Daily Loom Production Item', {
	weaving_contract: function (frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.weaving_contract) {
			return;
		}
		// Item follows the Weaving Contract's Finish Item.
		frappe.db.get_value('Weaving Contract', row.weaving_contract, 'construction').then(function (r) {
			const construction = r.message && r.message.construction;
			if (construction) {
				frappe.model.set_value(cdt, cdn, 'item', construction);
			}
			refresh_material_fields(frm, cdt, cdn);
		});
	},
	sales_order: function (frm, cdt, cdn) {
		// A stale Item pick from a different Sales Order can't linger
		// once the Sales Order itself changes.
		frappe.model.set_value(cdt, cdn, 'item', '');
	},
	// 2026-09-28 (feature v3) - per your request: A/B/C/Cut Pcs Qty feed
	// Finish Qty, which now feeds Total Greige Weight, which needs Greige
	// Weight fetched off Sales Order + Item first. Wired as one small
	// cascade rather than four separate recomputes.
	loom: function (frm, cdt, cdn) {
		recalc_metrics(frm, cdt, cdn);
	},
	rpm: function (frm, cdt, cdn) {
		recalc_metrics(frm, cdt, cdn);
	},
	total_greige_weight_scale: function (frm, cdt, cdn) {
		recalc_metrics(frm, cdt, cdn);
	},
	item: function (frm, cdt, cdn) {
		recalc_metrics(frm, cdt, cdn);
		fetch_greige_weight(frm, cdt, cdn);
		refresh_material_fields(frm, cdt, cdn);
	},
	pile_beam: function (frm, cdt, cdn) {
		default_beam_warehouse(cdt, cdn, 'pile');
	},
	ground_beam: function (frm, cdt, cdn) {
		default_beam_warehouse(cdt, cdn, 'ground');
	},
	a_qty: function (frm, cdt, cdn) {
		recalc_finish_qty(frm, cdt, cdn);
	},
	b_qty: function (frm, cdt, cdn) {
		recalc_finish_qty(frm, cdt, cdn);
	},
	c_qty: function (frm, cdt, cdn) {
		recalc_finish_qty(frm, cdt, cdn);
	},
	cut_pcs_qty: function (frm, cdt, cdn) {
		recalc_finish_qty(frm, cdt, cdn);
	},
	finish_qty: function (frm, cdt, cdn) {
		recalc_metrics(frm, cdt, cdn);
		recalc_total_greige_weight(frm, cdt, cdn);
		recalculate_total_finish_qty(frm);
	},
	greige_weight: function (frm, cdt, cdn) {
		recalc_total_greige_weight(frm, cdt, cdn);
	},
	items_add: function (frm) {
		recalculate_total_finish_qty(frm);
	},
	items_remove: function (frm) {
		recalculate_total_finish_qty(frm);
	}
});

// 2026-09-28 - "Finish Qty (Read only) = A Qty + B Qty + C Qty + Cut Pcs
// Qty" (your words). Live preview only - daily_loom_production.py's own
// validate() recomputes this authoritatively on save regardless, same
// "server is the source of truth" pattern used everywhere else in this
// project.
function recalc_finish_qty(frm, cdt, cdn) {
	let row = locals[cdt][cdn];
	let finish_qty = flt(row.a_qty) + flt(row.b_qty) + flt(row.c_qty) + flt(row.cut_pcs_qty);
	frappe.model.set_value(cdt, cdn, 'finish_qty', finish_qty);
}

// "Total Greige Weight (Calculated) (greige weight * Finish Qty)" (your
// words). Live preview only, same reasoning as above.
function recalc_total_greige_weight(frm, cdt, cdn) {
	let row = locals[cdt][cdn];
	let total = flt(row.greige_weight) * flt(row.finish_qty) / 1000;
	frappe.model.set_value(cdt, cdn, 'total_greige_weight', total);
}

// "Fetch ... greige weight (from TCS finish table)(New Field)" (your
// words). Live preview only, same reasoning as above - needs both Sales
// Order and Item set, same lookup Raw Material Selection already uses.
function fetch_greige_weight(frm, cdt, cdn) {
	let row = locals[cdt][cdn];
	if (!(frm.doc.commercial ? row.weaving_contract : row.sales_order) || !row.item) {
		return;
	}
	frappe.call({
		method: 'mjfsd_v3.loom_production.events.create_stock_entry_from_daily_towel_production.get_greige_weight',
		args: {
			sales_order: frm.doc.commercial ? null : row.sales_order,
			item_code: row.item,
			weaving_contract: frm.doc.commercial ? row.weaving_contract : null
		},
		callback: function (r) {
			if (r.message === undefined) {
				return;
			}
			frappe.model.set_value(cdt, cdn, 'greige_weight', flt(r.message));
			recalc_total_greige_weight(frm, cdt, cdn);
		}
	});
}

function recalculate_total_finish_qty(frm) {
	let total = 0;
	(frm.doc.items || []).forEach(function (row) {
		total += flt(row.finish_qty);
	});
	frm.set_value('total_finish_qty', total);
}

// Show only the warehouse / beam fields this row's item needs: Pile, Ground,
// Weft, Fancy - read from the Weaving Contract (Commercial) or Towel Costing Sheet.
function refresh_material_fields(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	if (!row.item || !(frm.doc.commercial ? row.weaving_contract : row.sales_order)) {
		return;
	}
	frappe.call({
		method: 'mjfsd_v3.loom_production.events.create_stock_entry_from_daily_towel_production.get_row_material_types',
		args: {
			sales_order: frm.doc.commercial ? null : row.sales_order,
			item_code: row.item,
			weaving_contract: frm.doc.commercial ? row.weaving_contract : null
		},
		callback: function (r) {
			const types = r.message || {};
			Object.keys(types).forEach(function (key) {
				frappe.model.set_value(cdt, cdn, 'has_' + key, types[key]);
			});
			// yarn goes out of the usual yarn store unless changed
			['weft', 'fancy'].forEach(function (key) {
				if (types[key] && !row[key + '_warehouse']) {
					frappe.model.set_value(cdt, cdn, key + '_warehouse', 'Stores - PT');
				}
			});
		}
	});
}

// Picking a beam batch defaults its warehouse to where that beam was received.
function default_beam_warehouse(cdt, cdn, type) {
	const row = locals[cdt][cdn];
	if (!row[type + '_beam']) {
		return;
	}
	frappe.call({
		method: 'mjfsd_v3.loom_production.events.create_stock_entry_from_daily_towel_production.get_beam_batch_info',
		args: { batch: row[type + '_beam'] },
		callback: function (r) {
			if (r.message && r.message.target_warehouse && !row[type + '_warehouse']) {
				frappe.model.set_value(cdt, cdn, type + '_warehouse', r.message.target_warehouse);
			}
		}
	});
}

// Efficiency figures (No of Picks, Panel, Avg Pcs Weight, Efficiency (100%),
// Total Greige Weight (Scale LBS), Actual Efficiency, Unit Price). The server's
// validate() recalculates them on save with the same function.
function recalc_metrics(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	frappe.call({
		method: 'mjfsd_v3.loom_production.doctype.daily_loom_production.daily_loom_production.get_row_metrics',
		args: {
			shift: frm.doc.shift,
			loom: row.loom,
			rpm: row.rpm,
			item: row.item,
			finish_qty: row.finish_qty,
			total_greige_weight_scale: row.total_greige_weight_scale
		},
		callback: function (r) {
			Object.entries(r.message || {}).forEach(function ([field, value]) {
				frappe.model.set_value(cdt, cdn, field, value);
			});
		}
	});
}
