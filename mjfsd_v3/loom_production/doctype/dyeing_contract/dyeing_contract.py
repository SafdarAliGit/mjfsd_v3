import frappe
from frappe.model.document import Document
from frappe.utils import flt

from mjfsd_v3.loom_production.events.create_dyeing_contract import validate_dyeing_balance
from mjfsd_v3.loom_production.events.dyeing_calc import apply_row_details, get_tcs_finish_row
from mjfsd_v3.loom_production.events.issue_fabric import cancel_issued_stock_entries


class DyeingContract(Document):
	def validate(self):
		self.recalculate_totals()
		# 2026-09-26 - several dyers per Sales Order: Order Qty is checked
		# against the AB Qty still unassigned (warn on draft save, block on
		# submit). Skipped for later saves of an already-submitted contract.
		if self.docstatus == 0 or getattr(self, "_action", None) == "submit":
			validate_dyeing_balance(self, hard=self.docstatus == 1)

	def on_cancel(self):
		cancel_issued_stock_entries(self)

	def recalculate_totals(self):
		# 2026-09-28 (feature v3) - "Rename the fields Weight Kg to Weight
		# LBS in Dyeing Documents ... calculate weight as following
		# ((Pcs * finish weight mentioned in TCS)/1000)*2.2046" (your
		# words) - weight_issued_kg/weight_received_kg (labels now say
		# LBS - dyeing_contract_item.json) are no longer a manual/
		# accumulated-from-Stock-Entry figure; they're derived straight
		# from Issued/Received Qty and the TCS Finish Weight for this
		# row's Item, same formula Dyeing Receipt already used for its
		# own Finish Weight/Weight Actual (Lbs) fields. issue_fabric.py's
		# apply_issued_qty/reverse_issued_qty/sync_issued_totals no
		# longer touch weight_issued_kg for the same reason - it's now
		# always derived here, not accumulated there.
		#
		# "Amounts calculated will be amount = dyeing rate * weight
		# (lbs)" (your words) - was Rate x Order Qty (Pcs) before; now
		# Rate x the Issued weight in lbs (what was actually sent out
		# to be dyed - the billable moment).
		tcs_cache = {}
		for row in self.items or []:
			tcs_finish_weight = _get_tcs_finish_weight(tcs_cache, row.towel_costing_sheet, row.item)
			row.weight_issued_kg = calc_weight_lbs(row.issued_qty, tcs_finish_weight)
			row.weight_received_kg = calc_weight_lbs(row.received_qty, tcs_finish_weight)

			# Finish Weight, Cut Size, LBS and Solid / Stripe / Yarn Dyed (by the
			# TCS row's Dyeing Type); Amount = LBS x Rate
			apply_row_details(row, get_tcs_finish_row(tcs_cache, row.towel_costing_sheet, row.item))
			row.amount = flt(row.rate) * flt(row.lbs)

		self.contract_amount = sum(flt(row.amount) for row in self.items or [])

		self.total_issue_qty = sum(flt(row.issued_qty) for row in self.items or [])
		self.total_received_qty = sum(flt(row.received_qty) for row in self.items or [])
		self.total_rolls_issued = sum(flt(row.rolls_issued) for row in self.items or [])
		self.total_rolls_received = sum(flt(row.rolls_received) for row in self.items or [])
		self.total_weight_issued_kg = sum(flt(row.weight_issued_kg) for row in self.items or [])
		self.total_weight_received_kg = sum(flt(row.weight_received_kg) for row in self.items or [])

		self.balance_qty = self.total_issue_qty - self.total_received_qty
		self.balance_rolls = self.total_rolls_issued - self.total_rolls_received
		self.balance_weight_kg = self.total_weight_issued_kg - self.total_weight_received_kg


def calc_weight_lbs(pcs, tcs_finish_weight):
	"""2026-09-28 (feature v3) - "((Pcs * finish weight mentioned in TCS)
	/1000)*2.2046" (your words). TCS Finish Weight is grams per piece;
	/1000 -> kg, x2.2046 -> lbs."""
	return (flt(tcs_finish_weight) / 1000) * flt(pcs) * 2.2046


def _get_tcs_finish_weight(tcs_cache, towel_costing_sheet, item_code):
	if not (towel_costing_sheet and item_code):
		return 0.0
	tcs = tcs_cache.get(towel_costing_sheet)
	if tcs is None:
		tcs = frappe.get_doc("Towel Costing Sheet", towel_costing_sheet)
		tcs_cache[towel_costing_sheet] = tcs
	for row in tcs.finish_item_towel_costing or []:
		if row.article == item_code:
			return flt(row.finish_weight)
	return 0.0
