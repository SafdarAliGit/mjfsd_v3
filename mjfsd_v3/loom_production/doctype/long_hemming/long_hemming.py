import frappe
from frappe.model.document import Document
from frappe.utils import flt

from mjfsd_v3.loom_production.events.create_stock_entry_from_long_hemming import (
	cancel_linked_stock_entries,
	create_transfer_stock_entries,
	create_wastage_receipt_entry,
)


class LongHemming(Document):
	def validate(self):
		self.recalculate_totals()
		if self.transfer_b_qty and not self.b_qty_warehouse:
			frappe.throw(frappe._("B Qty Warehouse is required when Transfer B Qty is checked."))

	def on_submit(self):
		create_transfer_stock_entries(self)
		create_wastage_receipt_entry(self)

	def on_cancel(self):
		cancel_linked_stock_entries(self)

	def recalculate_totals(self):
		self.total_fabric_issued = sum(flt(row.issued_pcs) for row in self.items or [])
		total_hemmed = sum(flt(row.a_qty) + flt(row.b_qty) for row in self.items or [])
		self.total_hemming_amount = flt(self.hemming_rate) * total_hemmed
