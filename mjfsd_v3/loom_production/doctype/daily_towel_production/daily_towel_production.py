# Copyright (c) 2026, Tech Ventures and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import flt

from mjfsd_v3.loom_production.events.create_stock_entry_from_daily_towel_production import (
	create_stock_entries,
	cancel_linked_stock_entries,
)


class DailyTowelProduction(Document):
	def validate(self):
		# Total Finish Qty is a read-only auto-sum of the child rows - not
		# explicitly specified as auto vs manual, but "Total Finish Qty" next
		# to a child table that already carries Finish Qty per row reads as a
		# rollup. Recalculated server-side (in addition to the client-side
		# total in daily_towel_production.js) so it can't be edited around.
		self.total_finish_qty = sum(flt(row.finish_qty) for row in self.items)

	def on_submit(self):
		# One Manufacture Stock Entry per child row, per spec ("Each Daily
		# Towel Production will contain multiple entries so multiple
		# manufacture entries will be created.").
		create_stock_entries(self)

	def on_cancel(self):
		cancel_linked_stock_entries(self)
