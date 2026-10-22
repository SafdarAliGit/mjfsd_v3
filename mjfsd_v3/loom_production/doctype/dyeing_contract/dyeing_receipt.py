import frappe
from frappe.model.document import Document
from frappe.utils import flt

from mjfsd_v3.loom_production.events.create_repack_stock_entry_from_dyeing_receipt import (
	cancel_linked_stock_entry,
	create_repack_stock_entry,
)


class DyeingReceipt(Document):
	def validate(self):
		self.recalculate_totals()

	def on_submit(self):
		create_repack_stock_entry(self)

	def on_cancel(self):
		cancel_linked_stock_entry(self)

	def recalculate_totals(self):
		for row in self.items or []:
			row.amount = flt(row.rate) * flt(row.received_qty)
			# 2026-09-15 (feature v3) - Weight (Actual) in Lbs, needed by the
			# new Per LBS Rate field on the Repack Stock Entry's finish row.
			row.weight_received_lbs = flt(row.weight_received_kg) * 2.2046

		self.total_received_qty = sum(flt(row.received_qty) for row in self.items or [])
