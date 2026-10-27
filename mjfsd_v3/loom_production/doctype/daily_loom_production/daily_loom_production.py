# Copyright (c) 2026, Tech Ventures and contributors
# For license information, please see license.txt

# 2026-09-28 (feature v3) - renamed from "Daily Towel Production" to
# "Daily Loom Production" (your words). The DocType record itself is
# renamed in place by a pre_model_sync patch (see
# mjfsd_v3/patches/rename_daily_towel_production_to_loom_production.py)
# so existing documents/history carry over - this is a new controller
# file matching the new name/module path Frappe requires, but the events
# module it delegates to (create_stock_entry_from_daily_towel_production.py)
# is unchanged: nothing in it is tied to the doctype's name, so renaming
# it too would only add risk for no benefit.

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt

from mjfsd_v3.loom_production.events.create_stock_entry_from_daily_towel_production import (
	create_stock_entries,
	cancel_linked_stock_entries,
	get_greige_weight,
	get_row_material_types,
)


LBS_PER_KG = 2.2046


def compute_row_metrics(rpm, shift_hours, picks, panel, scale_weight, finish_qty, loom_rate):
	"""Efficiency figures of one Daily Loom Production row.

	Avg Pcs Weight          = Total Greige Weight (Scale) / Finish Qty              (kg per piece)
	Efficiency (100%)       = ((RPM * Shift Hours * 60) / No of Picks) * Panel * Avg Pcs Weight * 2.2046   (LBS)
	Total Greige Wt (LBS)   = Total Greige Weight (Scale) * 2.2046
	Actual Efficiency       = Total Greige Weight (Scale LBS) / Efficiency (100%) * 100
	Unit Price              (only when Actual Efficiency >= 50) = ((RPM * Shift Hours * 60 * Actual Efficiency %) / 1000) * Loom Rate
	"""
	rpm, shift_hours, picks, panel = flt(rpm), flt(shift_hours), flt(picks), flt(panel)
	scale_weight, finish_qty, loom_rate = flt(scale_weight), flt(finish_qty), flt(loom_rate)

	avg_pcs_weight = scale_weight / finish_qty if finish_qty else 0
	efficiency_100 = (
		(rpm * shift_hours * 60 / picks) * panel * avg_pcs_weight * LBS_PER_KG if picks else 0
	)
	scale_lbs = scale_weight * LBS_PER_KG
	actual_efficiency = scale_lbs / efficiency_100 * 100 if efficiency_100 else 0
	# Unit Price is only earned from 50% Actual Efficiency upwards
	unit_price = (
		(rpm * shift_hours * 60 * actual_efficiency / 100 / 1000) * loom_rate
		if actual_efficiency >= 50
		else 0
	)

	return {
		"avg_pcs_weight": avg_pcs_weight,
		"efficiency_100": efficiency_100,
		"total_greige_weight_scale_lbs": scale_lbs,
		"actual_efficiency": actual_efficiency,
		"unit_price": unit_price,
	}


@frappe.whitelist()
def get_row_metrics(shift=None, loom=None, rpm=None, item=None, finish_qty=None, total_greige_weight_scale=None):
	"""Live preview for the form - the same calculation validate() runs on save."""
	shift_hours = frappe.db.get_value("Shift", shift, "shift_working_hours") if shift else 0
	loom_rate = frappe.db.get_value("Loom", loom, "rate") if loom else 0
	picks = panel = 0
	if item:
		picks, panel = frappe.db.get_value("Item", item, ["custom_no_of_pick", "custom_panel"]) or (0, 0)
	result = compute_row_metrics(rpm, shift_hours, picks, panel, total_greige_weight_scale, finish_qty, loom_rate)
	result.update({"no_of_picks": flt(picks), "panel": cint(panel)})
	return result


class DailyLoomProduction(Document):
	def validate(self):
		# 2026-09-28 (feature v3) - "Finish Qty (Read only) = A Qty + B Qty +
		# C Qty + Cut Pcs Qty" and "Total Greige Weight (Calculated) (greige
		# weight * Finish Qty)" (your words). Both recomputed here so they
		# can't be edited around - mirrors daily_loom_production.js's own
		# live-preview versions of the same two formulas ("server is the
		# source of truth" pattern used throughout this project). Greige
		# Weight itself is also re-fetched here (not just client-side on
		# Sales Order/Item change) so a row added without the browser
		# JS having fired still ends up with a real value on save.
		commercial = cint(self.commercial)
		for row in self.items:
			if row.weaver and frappe.db.get_value("Supplier", row.weaver, "supplier_group") != "Weaver":
				frappe.throw(_("Row {0}: {1} is not in the Supplier Group 'Weaver'.").format(row.idx, row.weaver))
			if commercial:
				self.validate_commercial_row(row)
			elif not row.sales_order:
				frappe.throw(_("Row {0}: Sales Order is required (or tick Commercial to use a Weaving Contract).").format(row.idx))
			else:
				row.weaving_contract = None

			# which warehouse / beam fields this row needs (Pile, Ground, Weft, Fancy)
			types = get_row_material_types(
				None if commercial else row.sales_order, row.item, row.weaving_contract if commercial else None
			)
			for key, value in types.items():
				row.set(f"has_{key}", value)

			row.finish_qty = flt(row.a_qty) + flt(row.b_qty) + flt(row.c_qty) + flt(row.cut_pcs_qty)
			if commercial:
				row.greige_weight = get_greige_weight(weaving_contract=row.weaving_contract)
			elif row.sales_order and row.item:
				row.greige_weight = get_greige_weight(row.sales_order, row.item)
			# Greige Weight is in grams; Total Greige Weight (Calculated) is in kg
			row.total_greige_weight = flt(row.greige_weight) * flt(row.finish_qty) / 1000

		# Efficiency figures (Item picks / panel, Shift hours, Loom rate)
		shift_hours = flt(frappe.db.get_value("Shift", self.shift, "shift_working_hours")) if self.shift else 0
		for row in self.items:
			picks, panel = (
				frappe.db.get_value("Item", row.item, ["custom_no_of_pick", "custom_panel"]) or (0, 0)
				if row.item
				else (0, 0)
			)
			row.no_of_picks = flt(picks)
			row.panel = cint(panel)
			loom_rate = frappe.db.get_value("Loom", row.loom, "rate") if row.loom else 0
			for key, value in compute_row_metrics(
				row.rpm, shift_hours, row.no_of_picks, row.panel,
				row.total_greige_weight_scale, row.finish_qty, loom_rate,
			).items():
				row.set(key, value)

		# Total Finish Qty is a read-only auto-sum of the child rows - not
		# explicitly specified as auto vs manual, but "Total Finish Qty" next
		# to a child table that already carries Finish Qty per row reads as a
		# rollup. Recalculated server-side (in addition to the client-side
		# total in daily_loom_production.js) so it can't be edited around.
		self.total_finish_qty = sum(flt(row.finish_qty) for row in self.items)

	def validate_commercial_row(self, row):
		"""Commercial rows run off a submitted Weaving Contract - no Sales
		Order, no Towel Costing Sheet."""
		if not row.weaving_contract:
			frappe.throw(_("Row {0}: Weaving Contract is required for a Commercial document.").format(row.idx))
		contract = frappe.db.get_value(
			"Weaving Contract", row.weaving_contract, ["docstatus", "construction"], as_dict=True
		)
		if not contract or contract.docstatus != 1:
			frappe.throw(_("Row {0}: Weaving Contract {1} is not submitted.").format(row.idx, row.weaving_contract))
		row.sales_order = None
		if not row.item:
			row.item = contract.construction
		elif row.item != contract.construction:
			frappe.throw(
				_("Row {0}: Item {1} is not the Finish Item of Weaving Contract {2} ({3}).").format(
					row.idx, row.item, row.weaving_contract, contract.construction
				)
			)

	def on_submit(self):
		# One Manufacture Stock Entry per child row, per spec ("Each Daily
		# Towel Production will contain multiple entries so multiple
		# manufacture entries will be created.").
		create_stock_entries(self)

	def on_cancel(self):
		cancel_linked_stock_entries(self)
