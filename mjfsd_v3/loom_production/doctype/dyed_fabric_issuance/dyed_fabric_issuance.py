from frappe.model.document import Document
from frappe.utils import flt

from mjfsd_v3.loom_production.events.create_stock_entry_from_dyed_fabric_issuance import (
	cancel_linked_stock_entry,
	create_transfer_stock_entry,
)


class DyedFabricIssuance(Document):
	def validate(self):
		self.recalculate_totals()

	def on_submit(self):
		create_transfer_stock_entry(self)

	def on_cancel(self):
		cancel_linked_stock_entry(self)

	def recalculate_totals(self):
		self.total_fabric_issued = sum(flt(row.pcs) for row in self.items or [])
