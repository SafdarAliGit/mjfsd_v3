import frappe
from frappe import _
from frappe.model.document import Document
from frappe.model.naming import  make_autoname
from mjfsd_v3.loom_production.events.utils import get_doctypes_by_field

class SizingProgram(Document):
	def on_submit(self):
		if self.stock_return_item and len(self.stock_return_item) > 0:
			self.make_stock_entry_for_stock_return_item()

	def make_stock_entry_for_stock_return_item(self):
		try:
			se = frappe.new_doc("Stock Entry")
			se.stock_entry_type = "Material Transfer"
			se.purpose = "Material Transfer"
			se.set_posting_time = 1
			se.posting_date = self.date
			se.sizing_program = self.name

			for row in self.stock_return_item:
				se.append("items", {
					"item_code": row.yarn_item,
					"qty": row.qty_lbs,
					"uom": "Lbs",
					"s_warehouse": self.source_warehouse,
					"t_warehouse": row.target_warehouse,
					"conversion_factor": 1,
					"stock_uom": "Lbs"
				})

			se.save()
			se.submit()

		except Exception as e:
			frappe.log_error(frappe.get_traceback(), "Error in make_stock_entry_for_stock_return_item")
			frappe.throw(_("Failed to create Stock Entry. Error: {0}").format(str(e)))

	def on_cancel(self):
		entries = get_doctypes_by_field('Stock Entry', 'sizing_program', self.name)
		

		for entry in entries:
			doc = frappe.get_doc('Stock Entry', entry.name)

			if doc.docstatus != 2:  # docstatus 2 = Cancelled
				doc.cancel()
			else:
				frappe.throw(f"Document {doc.name} is not in the 'Submitted' state.")

			# Construct new autoname if needed
			if doc.amended_from:
				new_suffix = int(doc.name.split("-")[-1]) + 1
			else:
				new_suffix = 1

			new_name = f"{doc.name}-{new_suffix}"
			make_autoname(new_name, 'Stock Entry')

		# Commit once, after processing all
		frappe.db.commit()
