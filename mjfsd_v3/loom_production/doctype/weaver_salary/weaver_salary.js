// Copyright (c) 2026, Tech Ventures and contributors
// For license information, please see license.txt

frappe.ui.form.on('Weaver Salary', {
	refresh: function (frm) {
		frm.set_query('weaver', 'salary_details', function () {
			return { filters: { supplier_group: 'Weaver' } };
		});
	},
	fetch_details: function (frm) {
		if (!frm.doc.from_date || !frm.doc.to_date) {
			frappe.msgprint(__('Set From Date and To Date first.'));
			return;
		}
		frm.call({ method: 'fetch_details', doc: frm.doc, freeze: true }).then(function () {
			frm.dirty();
			frm.refresh_field('salary_details');
		});
	}
});

// Every column is recalculated whenever an input on the row changes.
const SALARY_INPUTS = [
	'working_days', 'extra_loom_count', 'holiday_ot_count', 'present_allowance',
	'present_allowance_amount', 'salary_per_day', 'unit_price', 'advance_amount'
];

const handlers = {};
SALARY_INPUTS.forEach(function (field) {
	handlers[field] = function (frm, cdt, cdn) {
		recalc_salary_row(cdt, cdn);
	};
});
frappe.ui.form.on('Weaver Salary Detail', handlers);

function recalc_salary_row(cdt, cdn) {
	const row = locals[cdt][cdn];
	const set = (field, value) => frappe.model.set_value(cdt, cdn, field, value);

	const salary_per_day = flt(row.salary_per_day);
	let allowance = 0;
	if (row.present_allowance) {
		if (!flt(row.present_allowance_amount)) {
			set('present_allowance_amount', 2000);
		}
		allowance = flt(row.present_allowance_amount) || 2000;
	} else if (flt(row.present_allowance_amount)) {
		set('present_allowance_amount', 0);
	}

	const basic = salary_per_day * flt(row.working_days);
	const extra_rate = salary_per_day / 2;
	const holiday_rate = salary_per_day / 2;
	const extra_amount = extra_rate * flt(row.extra_loom_count);
	const holiday_amount = holiday_rate * flt(row.holiday_ot_count);
	const gross = basic + extra_amount + holiday_amount + allowance;

	set('basic_salary', basic);
	set('extra_loom_rate', extra_rate);
	set('extra_loom_amount', extra_amount);
	set('holiday_rate', holiday_rate);
	set('holiday_amount', holiday_amount);
	set('gross_salary', gross);
	set('net_salary', gross + flt(row.unit_price) - flt(row.advance_amount));
}
