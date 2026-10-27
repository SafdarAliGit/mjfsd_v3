# Copyright (c) 2026, Tech Ventures and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, date_diff, flt, getdate

HOLIDAY_LIST = "Standard Holiday List"
DEFAULT_PRESENT_ALLOWANCE = 2000


def calculate_row(row):
	"""All salary columns of one Weaver Salary Detail row."""
	salary_per_day = flt(row.salary_per_day)
	row.basic_salary = salary_per_day * flt(row.working_days)
	row.extra_loom_rate = salary_per_day / 2
	row.extra_loom_amount = flt(row.extra_loom_rate) * flt(row.extra_loom_count)
	row.holiday_rate = salary_per_day / 2
	row.holiday_amount = flt(row.holiday_rate) * flt(row.holiday_ot_count)
	if row.present_allowance:
		if not flt(row.present_allowance_amount):
			row.present_allowance_amount = DEFAULT_PRESENT_ALLOWANCE
		allowance = flt(row.present_allowance_amount)
	else:
		row.present_allowance_amount = 0
		allowance = 0
	row.gross_salary = flt(row.basic_salary) + flt(row.extra_loom_amount) + flt(row.holiday_amount) + allowance
	row.net_salary = flt(row.gross_salary) + flt(row.unit_price) - flt(row.advance_amount)


class WeaverSalary(Document):
	def validate(self):
		if self.from_date and self.to_date and getdate(self.from_date) > getdate(self.to_date):
			frappe.throw(_("From Date cannot be after To Date."))
		for row in self.salary_details or []:
			if row.weaver:
				group = frappe.db.get_value("Supplier", row.weaver, "supplier_group")
				if group != "Weaver":
					frappe.throw(_("Row {0}: {1} is not in the Supplier Group 'Weaver'.").format(row.idx, row.weaver))
				row.salary_per_day = flt(frappe.db.get_value("Supplier", row.weaver, "custom_salary_per_day"))
			calculate_row(row)

	@frappe.whitelist()
	def fetch_details(self):
		"""Fill Salary Details from the submitted Daily Loom Production entries
		between From Date and To Date, one row per weaver.

		Working Days    = days the weaver has an entry
		Extra Loom      = on each day, looms worked beyond 2 (3 looms = 1 extra)
		Holiday/OT      = worked days that are in the Standard Holiday List
		Present Allowance = worked every non-holiday day of the range
		Unit Price      = sum of Unit Price on the weaver's rows"""
		if not (self.from_date and self.to_date):
			frappe.throw(_("Set From Date and To Date first."))
		from_date, to_date = getdate(self.from_date), getdate(self.to_date)
		if from_date > to_date:
			frappe.throw(_("From Date cannot be after To Date."))
		if not frappe.db.exists("Holiday List", HOLIDAY_LIST):
			frappe.throw(_("Holiday List {0} was not found.").format(HOLIDAY_LIST))

		holidays = {
			getdate(d)
			for d in frappe.get_all(
				"Holiday",
				filters={"parent": HOLIDAY_LIST, "holiday_date": ["between", [from_date, to_date]]},
				pluck="holiday_date",
			)
		}
		working_dates = {
			add_days(from_date, i) for i in range(date_diff(to_date, from_date) + 1)
		} - holidays

		entries = frappe.db.sql(
			"""
			select p.date, i.weaver, i.loom, i.unit_price
			from `tabDaily Loom Production Item` i
			inner join `tabDaily Loom Production` p
				on p.name = i.parent and i.parenttype = 'Daily Loom Production'
			where p.docstatus = 1 and p.date between %s and %s and ifnull(i.weaver, '') != ''
			""",
			(from_date, to_date),
			as_dict=True,
		)

		weavers = {}
		for e in entries:
			data = weavers.setdefault(e.weaver, {"days": {}, "unit_price": 0.0})
			looms = data["days"].setdefault(getdate(e.date), set())
			if e.loom:
				looms.add(e.loom)
			data["unit_price"] += flt(e.unit_price)

		self.set("salary_details", [])
		for weaver in sorted(weavers):
			data = weavers[weaver]
			days = data["days"]
			row = self.append("salary_details", {})
			row.weaver = weaver
			row.weaver_name = frappe.db.get_value("Supplier", weaver, "supplier_name")
			row.salary_per_day = flt(frappe.db.get_value("Supplier", weaver, "custom_salary_per_day"))
			row.working_days = len(days)
			row.extra_loom_count = sum(max(0, len(looms) - 2) for looms in days.values())
			row.holiday_ot_count = sum(1 for day in days if day in holidays)
			row.present_allowance = 1 if working_dates and working_dates <= set(days) else 0
			row.unit_price = data["unit_price"]
			calculate_row(row)

		if not self.salary_details:
			frappe.msgprint(_("No submitted Daily Loom Production entries with a Weaver were found in this period."))
