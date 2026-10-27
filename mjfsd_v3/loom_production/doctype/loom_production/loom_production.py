# Copyright (c) 2023, Tech Ventures and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class LoomProduction(Document):
    def validate(self):
        for item in self.loom_production_items:
            if not item.constant:
                item.constant = 25.4

    def before_save(self):
        try:
            shift_hours = float(self.shift_working_hours)
        except (TypeError, ValueError):
            shift_hours = 0
        total_meters = 0
        total_unit_per_rpm = 0
        total_efficiency = 0
        total_pick = 0
        for row in self.loom_production_items:
            try:
                rpm = float(row.rpm or 0)
                constant = float(row.constant or 0)
                pick = float(row.pick or 1)  # prevent division by zero
                panna = float(row.panna or 0)
                actual_reading = float(row.actual_reading or 0)

                # unit_per_rpm calculation
                unit_per_rpm = round((rpm * (0.72 / 12)) * shift_hours)
                row.unit_per_rpm = unit_per_rpm

                # efficiency calculation
                if unit_per_rpm > 0:
                    row.effeciency = round((actual_reading / unit_per_rpm) * 100, 0)
                else:
                    row.effeciency = 0

                # meters calculation
                row.meters = ((actual_reading * constant) / pick) * panna
                # master calculations
                total_meters += row.meters
                total_unit_per_rpm += row.unit_per_rpm
                total_efficiency += row.effeciency
                total_pick += row.pick
            except (TypeError, ValueError):
                row.unit_per_rpm = 0
                row.effeciency = 0
                row.meters = 0
        self.total_meters = total_meters
        self.total_unit_per_rpm = total_unit_per_rpm
        self.average_efficiency = total_efficiency / len(self.loom_production_items)
        
        running_items = [row for row in self.loom_production_items if (row.effeciency or 0) > 0]

        self.running_average_efficiency = (
            round(total_efficiency / len(running_items), 2) if running_items else 0
        )
        self.avg_pick = total_pick / len(self.loom_production_items)




		
