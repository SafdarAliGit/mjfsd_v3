import frappe
from frappe.utils import flt

LBS_PER_KG = 2.2046
# Dyeing Type on the Towel Costing Sheet's Finish Item row -> the qty field it fills
DYEING_TYPE_FIELDS = {"Solid": "solid", "Stripe": "stripe", "Yarn Dyed": "yarn_dyed"}


def get_tcs_finish_row(cache, towel_costing_sheet, item_code):
	"""The Finish Item Towel Costing row of this item on the sheet (cached), as a dict."""
	if not (towel_costing_sheet and item_code):
		return None
	tcs = cache.get(towel_costing_sheet)
	if tcs is None:
		tcs = frappe.get_doc("Towel Costing Sheet", towel_costing_sheet)
		cache[towel_costing_sheet] = tcs
	for row in tcs.finish_item_towel_costing or []:
		if row.article == item_code:
			return {
				"finish_weight": flt(row.finish_weight),
				"uom": row.uom or "Gram",
				"dyeing_type": row.get("custom_dyeing_type"),
				"cut_size": row.get("custom_cut_size"),
			}
	return None


def calc_lbs(ab_qty, finish_weight, uom):
	"""LBS of a Dyeing Contract row.
	UOM Gram     : AB Qty x (Finish Weight / 1000) x 2.2046   (grams per piece -> lbs)
	UOM LBS/Dozen: AB Qty x (Finish Weight / 12)
	"""
	if uom == "LBS/Dozen":
		return flt(ab_qty) * (flt(finish_weight) / 12)
	return flt(ab_qty) * (flt(finish_weight) / 1000) * LBS_PER_KG


def apply_row_details(row, tcs_row):
	"""Fill a Dyeing Contract Item from its TCS Finish Item row: Finish Weight,
	Cut Size (only if blank), LBS, and the AB Qty into Solid / Stripe / Yarn Dyed
	according to the row's Dyeing Type."""
	if tcs_row:
		row.finish_weight = tcs_row["finish_weight"]
		row.finish_weight_uom = tcs_row["uom"]
		if not row.cut_size and tcs_row.get("cut_size"):
			row.cut_size = tcs_row["cut_size"]
	row.lbs = calc_lbs(row.order_qty, row.finish_weight, row.finish_weight_uom)

	for fieldname in DYEING_TYPE_FIELDS.values():
		row.set(fieldname, 0)
	field = DYEING_TYPE_FIELDS.get((tcs_row or {}).get("dyeing_type"))
	if field:
		row.set(field, flt(row.order_qty))
