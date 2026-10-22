import frappe
from frappe import _
from frappe.model.document import Document

from mjfsd_v3.loom_production.events.stitching_and_finishing import (
	cancel_stock_entries,
	check_not_already_used,
	create_stock_entries,
	create_waste_receipt_entry,
	fetch_trims_from_tcs,
	fill_from_long_hemming,
	recalculate,
)


class StitchingandFinishing(Document):
	def validate(self):
		check_not_already_used(self)
		problems = recalculate(self)
		if problems and self.docstatus == 1:
			frappe.throw(
				_("Cannot calculate Trims Qty Required until these are filled in:") + "<br>" + "<br>".join(problems)
			)

	def on_submit(self):
		create_stock_entries(self)
		create_waste_receipt_entry(self)

	def on_cancel(self):
		cancel_stock_entries(self)

	@frappe.whitelist()
	def get_items_from_long_hemming(self, long_hemming):
		lh = frappe.get_doc("Long Hemming", long_hemming)
		if lh.docstatus != 1:
			frappe.throw(_("Long Hemming must be submitted first."))
		fill_from_long_hemming(self, lh)

	@frappe.whitelist()
	def refresh_trims_from_tcs(self):
		fetch_trims_from_tcs(self)
		recalculate(self)
