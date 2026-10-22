import frappe
from frappe.model.document import Document
from frappe.utils import flt

from mjfsd_v3.loom_production.events.create_stock_entry_from_weaving_receipt import (
	cancel_linked_stock_entry,
	create_manufacture_stock_entry,
)


class WeavingReceipt(Document):
	def validate(self):
		self.recalculate_totals()

	def on_submit(self):
		create_manufacture_stock_entry(self)

	def on_cancel(self):
		cancel_linked_stock_entry(self)

	def recalculate_totals(self):
		"""Authoritative server-side recompute, run on every save -
		mirrors weaving_receipt.js's own rollups, but this is what
		actually governs what on_submit sees, regardless of whatever the
		browser did. Recomputes each Items row's Pcs (Actual)/Weight
		(Actual) fresh from its own Details rows (matched via row_key,
		not `name` - see the field's own description for why `name`
		can't be used) before rolling those up into the three parent
		Total fields, so a stale/unset weight_actual on an Items row can
		never silently reach the Manufacture Stock Entry's consumed-qty
		calculation on submit.
		"""
		details_by_row_key = {}
		for detail in self.details or []:
			details_by_row_key.setdefault(detail.item_row, []).append(detail)

		total_pcs_received = 0.0
		total_weight_challan = 0.0
		total_weight_actual = 0.0

		for row in self.items or []:
			if not row.row_key:
				row.row_key = frappe.generate_hash(length=10)

			rows = details_by_row_key.get(row.row_key, [])
			row.pcs_actual = sum(flt(d.total_pcs) for d in rows)
			row.weight_actual = sum(flt(d.weight) for d in rows)
			# 2026-09-15 (feature v3) - Weight (Actual) in Lbs. Used instead
			# of Weight (Actual) kg for the yarn consumed-qty formula (your
			# instruction: "yarn consumed qty is incorrect, just use the
			# weight actual (Lbs) now instead of weight actual") and for the
			# new Per LBS Rate / finish item basic rate formulas on the
			# Manufacture Stock Entry.
			row.weight_actual_lbs = flt(row.weight_actual) * 2.2046

			total_pcs_received += flt(row.pcs_actual)
			total_weight_challan += flt(row.weight_challan)
			total_weight_actual += flt(row.weight_actual)

		self.total_pcs_received = total_pcs_received
		self.total_weight_challan = total_weight_challan
		self.total_weight_actual = total_weight_actual
