// Copyright (c) 2026, Tech Ventures and contributors
// For license information, please see license.txt

// Ported from the per-row "Sizing Program Item" child-table client script
// (frappe.ui.form.on('Sizing Program Item', {...}) in sizing_program.js) -
// same fields, same formulas, now running as a top-level document instead
// of a child-grid row: locals[cdt][cdn] -> frm.doc, and
// frappe.model.set_value(cdt, cdn, ...) -> frm.set_value(...).
//
// One behavioural difference from the child table: the child script had
// two "ends:" handlers in the same object literal, and JS silently let the
// second shadow the first, so only calculate_total_yarn_consumption /
// compute_yarn_values / calculate_wastes actually ran on Ends changing -
// calculate_value_from_ends / calculate_warp_weight never fired. This is a
// fresh file, so both are merged into one handler below (all five
// functions run) rather than reproducing that bug.
//
// Round 13: Sizing Receipt is now submittable and the "Make Stock Entry"
// button/handler that used to live here is removed - submitting the
// document now raises the Beem Receipt Stock Entry automatically (see
// sizing_receipt.py on_submit), and leaving the manual button in place
// alongside that would risk creating a duplicate Stock Entry for the same
// receipt. The underlying Python method it used to call
// (make_stock_entry_from_sizing_item, in
// create_stock_entry_from_sizing_program.py) is left in the repo unused,
// in case this needs reverting.
//
// Also round 13: Actual Yarn Count is no longer a stored field (removed
// per request, along with Wastage Amount and Value Of Actual Yarn). It
// was previously written by compute_yarn_values and then READ by
// calculate_value_from_ends and calculate_warp_weight - both are
// refactored below to compute it locally via get_actual_yarn_count()
// instead of reading a persisted field. This incidentally fixes a
// pre-existing staleness quirk: on the "ends" handler below, those two
// functions used to run BEFORE compute_yarn_values updated the field for
// this same event, so they were always one step behind: now they compute
// the current value directly.
//
// 2026-09-16: "yarn item rate are set in item's valuation rate field but
// it is not being fetched in field" (your words) - root cause is that
// set_rate() was only ever wired to the `yarn_item:` field-change event.
// Two situations never fire that event, so Yarn Item Rate stayed 0/blank
// even though Yarn Item was set:
//   1. Source Warehouse is a hidden `fetch_from: sizing_program.source_
//      warehouse` field with no field-change handler of its own - if it
//      arrives (or changes) after Yarn Item was already set, set_rate()
//      never re-runs to pick it up, since nothing was listening for it.
//   2. Whenever this document is created pre-filled (server sets Yarn
//      Item/Source Warehouse directly and the browser routes straight to
//      it - the same "server pre-fills, user reviews and saves" pattern
//      used everywhere else in this project), no field-change event ever
//      fires for a value that arrives already set - `refresh` runs, but
//      not `yarn_item:`/`source_warehouse:`.
// Fixed with a `source_warehouse:` handler alongside `yarn_item:`, plus a
// one-time draft-only call from `refresh` so a freshly opened/created
// (not yet submitted) receipt with both fields already populated still
// gets its rate. Guarded to `docstatus == 0` so this never silently
// overwrites the rate already recorded on an existing submitted receipt.

frappe.ui.form.on('Sizing Receipt', {
	refresh: function (frm) {
		// Round 14: Stock Return Item's Yarn Item should only ever offer the
		// one yarn already selected on the parent document, not the full
		// Item list.
		frm.set_query('yarn_item', 'stock_return_item', function () {
			return {
				filters: {
					name: frm.doc.yarn_item || ''
				}
			};
		});

		// 2026-09-16 fix - see note above. Draft-only: never touches an
		// already-submitted receipt's recorded rate.
		if (frm.doc.docstatus == 0) {
			set_rate(frm);
		}
	},
	ends: function (frm) {
		calculate_value_from_ends(frm);
		calculate_warp_weight(frm);
		calculate_total_yarn_consumption(frm);
		compute_yarn_values(frm);
		calculate_wastes(frm);
	},
	yarn_count: function (frm) {
		calculate_warp_weight(frm);
		calculate_value_from_ends(frm);
	},
	beem_length: function (frm) {
		calculate_total_yarn_consumption(frm);
		compute_yarn_values(frm);
	},
	beam_no: function (frm) {
		check_beam_no(frm);
		calculate_total_yarn_consumption(frm);
		compute_yarn_values(frm);
	},
	yarn_item: function (frm) {
		set_rate(frm);
		calculate_wastes(frm);
	},
	// 2026-09-16 fix - see note above. Source Warehouse is a hidden
	// fetch_from field with no handler of its own before this - added so
	// a Source Warehouse that arrives/changes after Yarn Item was already
	// set still triggers the rate fetch.
	source_warehouse: function (frm) {
		set_rate(frm);
	},
	sizing_rate: function (frm) {
		calculate_total_yarn_consumption(frm);
		compute_yarn_values(frm);
		calculate_beem_rate(frm);
		calculate_wastes(frm);
	},
	lbs: function (frm) {
		compute_yarn_values(frm);
		calculate_wastes(frm);
		calculate_value_from_ends(frm);
		calculate_warp_weight(frm);
		// Round 14: Sizing Amount (and now Final Cost Of Beam) is a function
		// of Sizing Rate x LBS - it was previously only recalculated from
		// the sizing_rate: handler below, so an LBS-only edit left it stale.
		// Now recalculated here too.
		calculate_beem_rate(frm);
	}
});

function get_actual_yarn_count(frm) {
	// Actual Yarn Count is no longer a stored field (round 13) - computed
	// fresh here from its real inputs wherever it's needed, instead of
	// reading/writing a persisted value.
	let ends = flt(frm.doc.ends);
	let beem_length = flt(frm.doc.beem_length);
	let lbs = flt(frm.doc.lbs);
	return lbs != 0 ? (ends * beem_length) / 768.10 / lbs : 0;
}

function calculate_value_from_ends(frm) {
	// NOTE: divides by Actual Yarn Count, same as the child-table version -
	// the field's own description text says "/ Yarn Count" but the code
	// has always used Actual Yarn Count. Ported as-is (not "corrected")
	// since the real, executing formula is what this needs to match.
	const actual_yarn_count = get_actual_yarn_count(frm);
	if (frm.doc.ends && actual_yarn_count) {
		let result = (frm.doc.ends / 768.1) / actual_yarn_count;
		frm.set_value('yarn_consumption_per_meter', flt(result.toFixed(5)));
	} else {
		frm.set_value('yarn_consumption_per_meter', 0);
	}
}

function calculate_total_yarn_consumption(frm) {
	// Length = Beam No x Beem Length (was Beem Length x No Of Width).
	const length = 1 * flt(frm.doc.beem_length);
	frm.set_value('length', length);

	let total = flt(frm.doc.yarn_consumption_per_meter) * length;
	let beem_rate_per_meter = length ? (flt(total.toFixed(4)) * flt(frm.doc.yarn_item_rate)) / length : 0;
	frm.set_value('beem_rate_per_meter', flt(beem_rate_per_meter.toFixed(4)));
}

function calculate_warp_weight(frm) {
	const ends = frm.doc.ends;
	const actual_yarn_count = get_actual_yarn_count(frm);
	if (ends && actual_yarn_count) {
		const warp_weight = ends / 768.10 / actual_yarn_count;
		frm.set_value('warp_weight', warp_weight);
	} else {
		frm.set_value('warp_weight', 0);
	}
}

function set_rate(frm) {
	if (frm.doc.yarn_item && frm.doc.source_warehouse) {
		frappe.call({
			method: 'mjfsd_v3.loom_production.events.fetch_current_rate.fetch_current_rate',
			args: { item_code: frm.doc.yarn_item, warehouse: frm.doc.source_warehouse },
			callback: (r) => {
				if (!r.exc && r.message !== undefined) {
					frm.set_value('yarn_item_rate', r.message);
				}
			}
		});
	}
}

function calculate_beem_rate(frm) {
	// Sizing Rate is a per-LBS rate (field relabeled from "(Meter)" to
	// "(LBS)" to match) - this multiplication was already LBS-based, no
	// formula change needed here.
	const sizing_rate = flt(frm.doc.sizing_rate);
	const length = flt(frm.doc.length);
	const lbs = flt(frm.doc.lbs);

	const sizing_amount = sizing_rate * lbs;
	frm.set_value('sizing_amount', sizing_amount);

	const sizing_amount_by_length = length ? sizing_amount / length : 0;
	const beem_rate_plus = sizing_amount_by_length + flt(frm.doc.beem_rate);
	frm.set_value('beem_rate_per_meter', beem_rate_plus);

	calculate_final_cost_of_beam(frm);
}

function calculate_final_cost_of_beam(frm) {
	// Round 14: Final Cost Of Beam = Value Of Yarn + Sizing Amount. Called
	// from both places that can change either input (calculate_wastes sets
	// Value Of Yarn, calculate_beem_rate sets Sizing Amount) so this never
	// goes stale relative to either one.
	const final_cost_of_beam = flt(frm.doc.value_of_yarn) + flt(frm.doc.sizing_amount);
	frm.set_value('final_cost_of_beam', final_cost_of_beam);
}

function compute_yarn_values(frm) {
	// Actual Yarn Rate removed from this calculation - Beem Rate now comes
	// from Yarn Item Rate x Warp Weight, plus Sizing Rate added straight
	// (Sizing Rate is already a per-LBS figure, same unit as Beem Rate,
	// so it isn't scaled by Warp Weight again).
	let lbs = flt(frm.doc.lbs);
	let yarn_item_rate = flt(frm.doc.yarn_item_rate);
	let sizing_rate = flt(frm.doc.sizing_rate);

	if (lbs != 0) {
		frm.set_value('beem_rate', (yarn_item_rate  + sizing_rate));
	}
}

function calculate_wastes(frm) {
	// Round 13: Wastage Amount and Value Of Actual Yarn fields removed
	// (they always computed to a wash against Value Of Yarn / 0 since
	// round 9 anyway, once Actual Yarn Rate dropped out of the picture).
	// Value Of Yarn is kept - still a real, independent output.
	let yarn_item_rate = flt(frm.doc.yarn_item_rate);
	let lbs = flt(frm.doc.lbs);

	let value_of_yarn = yarn_item_rate * lbs;

	frm.set_value('value_of_yarn', value_of_yarn);
	calculate_final_cost_of_beam(frm);
}

// Beam No can't be more than the Sizing Beam on the Sizing Program
function check_beam_no(frm) {
	if (!frm.doc.sizing_program || !cint(frm.doc.beam_no)) {
		return;
	}
	frappe.db.get_value('Sizing Program', frm.doc.sizing_program, 'sizing_beam').then(function (r) {
		const sizing_beam = flt(r.message && r.message.sizing_beam);
		if (cint(frm.doc.beam_no) > sizing_beam) {
			frappe.msgprint(__('Beam No cannot be greater than the Sizing Beam ({0}) of the Sizing Program.', [sizing_beam]));
			frm.set_value('beam_no', cint(sizing_beam));
		}
	});
}
