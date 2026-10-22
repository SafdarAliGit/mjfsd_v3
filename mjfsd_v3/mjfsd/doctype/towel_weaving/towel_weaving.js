// Copyright (c) 2024, Tech Ventures and contributors
// For license information, please see license.txt

frappe.ui.form.on('Towel Weaving', {
    // Uncomment if needed for refreshing the form
    // refresh: function(frm) {

    // }
    width: function (frm) {
        quality_weaving(frm);
    },
    length: function (frm) {
        quality_weaving(frm);
    },
    gsm: function (frm) {
        quality_weaving(frm);
    },
    add_percentage: function (frm) {
        quality_weaving(frm);
    },
    thread_type: function (frm) {
        weft_consumption(frm);
        calculate_weft_count(frm);

    },

    weft_count: function (frm) {
        weft_consumption(frm);
        hem_consumption(frm);
    },
    pick: function (frm) {
        weft_consumption(frm);
    },
    percentage_add: function (frm) {
        weft_consumption(frm);
    },
    read: function (frm) {
        ground_consumption(frm);
    },
    cut: function (frm) {
        ground_consumption(frm);
    },
    kinar: function (frm) {
        ground_consumption(frm);
    },
    yarn: function (frm) {
        ground_consumption(frm);
        calculate_yarn_count(frm);
    },
    yarn_count: function (frm) {
        ground_consumption(frm);
    },
    add_percentage_first: function (frm) {
        ground_consumption(frm);
    },
    add_percentage_second: function (frm) {
        ground_consumption(frm);
    },
    hem_yarn_count: function (frm) {
        hem_consumption(frm);
    },
    add_percentage_third: function (frm) {
        hem_consumption(frm);
    },
    loom_with: function (frm) {
        hem_consumption(frm);
    },
    hem_pick: function (frm) {
        hem_consumption(frm);
    },
    loom_pcs: function (frm) {
        hem_consumption(frm);
    },
    weft_thread: function (frm) {
        calculate_weft_count(frm);
    },
    reduction: function (frm) {
        calculate_weft_count(frm);
        calculate_yarn_count(frm);
    },
    ground_thread_type: function (frm) {
        calculate_yarn_count(frm);
    }
});

function quality_weaving(frm) {
    let width = parseFloat(frm.doc.width) || 1;
    let height = parseFloat(frm.doc.length) || 1;
    let gsm = parseFloat(frm.doc.gsm) || 1;
    let add_percentage = parseFloat(frm.doc.add_percentage) || 0;
    const c = 10000;
    let quality_weight = (width * height * gsm) / c;
    let percentage = quality_weight * (add_percentage / 100);
    let total_quality_weight = quality_weight + percentage;
    frm.set_value("quality_weight", total_quality_weight);

}

function weft_consumption(frm) {
    let width = parseFloat(frm.doc.width) || 1;
    let height = parseFloat(frm.doc.length) || 1;
    let thread_type = frm.doc.thread_type || '';
    let weft_thread = parseFloat(frm.doc.weft_thread) || 1;
    let reduction = parseFloat(frm.doc.reduction) || 1;
    let weft_count = parseFloat(frm.doc.weft_count) || 1;
    let pick = parseFloat(frm.doc.pick) || 0;
    let percentage_add = parseFloat(frm.doc.percentage_add) || 1;
    let quality_weight = parseFloat(frm.doc.quality_weight) || 1;

    let pick_by_width = (pick * width) / 2.54;
    let pick_by_width_with_percentage = pick_by_width + (pick_by_width * (percentage_add / 100));

    let total_weft = (((((pick_by_width_with_percentage * height) / 100) / 768) / weft_count) / 2.2046) * 1000;
    let consumption_percentage = (total_weft / quality_weight) * 100;

    frm.set_value("total_weft", total_weft);
    frm.set_value("consumption_percentage", consumption_percentage);
    pile_calculations(frm);
}

function ground_consumption(frm) {
    // Parse form values and set defaults
    let width = parseFloat(frm.doc.width) || 1;
    let read = parseFloat(frm.doc.read) || 1;
    let kinar = parseFloat(frm.doc.kinar) || 0;
    let cut = parseFloat(frm.doc.cut) || 0;
    let length = parseFloat(frm.doc.length) || 1;
    let yarn_count = parseFloat(frm.doc.yarn_count) || 1;
    let thread_type = frm.doc.ground_thread_type || '';
    let add_percentage_first = parseFloat(frm.doc.add_percentage_first) || 1;
    let add_percentage_second = parseFloat(frm.doc.add_percentage_second) || 1;
    let quality_weight = parseFloat(frm.doc.quality_weight) || 1;

    // Calculate width by read with adjustments for percentage, kinar, and cut
    let width_by_read = (width / 2.54) * (read / 2);
    let width_by_read_with_percentage = width_by_read + (width_by_read * (add_percentage_first / 100));
    let width_by_read_with_kinar_and_cut = (width_by_read_with_percentage + kinar + cut) * length;
    let width_by_read_with_kinar_and_cut_with_percentage = width_by_read_with_kinar_and_cut + (width_by_read_with_kinar_and_cut * (add_percentage_second / 100));

    // Ensure yarn_count and quality_weight are non-zero to avoid division by zero
    if (yarn_count === 0) {
        yarn_count = 1;
        console.warn("yarn_count was zero, defaulted to 1 to avoid division by zero.");
    }
    if (quality_weight === 0) {
        quality_weight = 1;
        console.warn("quality_weight was zero, defaulted to 1 to avoid division by zero.");
    }

    // Calculate total ground and ground consumption percentage
    let total_ground = (((width_by_read_with_kinar_and_cut_with_percentage / 768) / yarn_count) / 2.2046) / 100;
    let ground_consumption_percentage = (total_ground / quality_weight) * 100000;

    // Set values in form
    frm.set_value("total_ground", total_ground);
    frm.set_value("ground_consumption_percentage", ground_consumption_percentage);
    pile_calculations(frm);
}

function hem_consumption(frm) {
    // Parse input values from the form and set defaults
    let hem_yarn_count = parseFloat(frm.doc.hem_yarn_count) || 0;
    let loom_width = parseFloat(frm.doc.loom_width) || 0;
    let hem_pick = parseFloat(frm.doc.hem_pick) || 0;
    let loom_pcs = parseFloat(frm.doc.loom_pcs) || 0;
    let add_percentage_third = parseFloat(frm.doc.add_percentage_third) || 1;
    let quality_weight = parseFloat(frm.doc.quality_weight) || 1;

    // Ensure quality_weight is not zero to avoid division by zero
    if (quality_weight === 0) {
        console.warn("quality_weight was zero, defaulted to 1 to avoid division by zero.");
        quality_weight = 1; // Default to 1 if zero
    }

    // Calculate hem pick based on loom width
    let hem_pic_by_loom_width = hem_pick * loom_width;

    // Calculate added hem pick based on additional percentage
    let added_hem_pic_by_loom_width = hem_pic_by_loom_width + (hem_pic_by_loom_width * (add_percentage_third / 100));

    // Calculate total hem consumption
    if (hem_yarn_count > 0 && loom_pcs > 0) {
        let total_hem = (((added_hem_pic_by_loom_width / 768.1) / hem_yarn_count) / 2.2046) / loom_pcs;

        // Calculate hem consumption percentage
        let hem_consumption_percentage = (total_hem / quality_weight) * 100000;

        // Set values in the form
        frm.set_value("total_hem", total_hem);
        frm.set_value("hem_consumption_percentage", hem_consumption_percentage);
    } else {
        // If yarn count or loom pieces are invalid, set outputs to zero
        frm.set_value("total_hem", 0);
        frm.set_value("hem_consumption_percentage", 0);
        frm.set_value("add_percentage_third", 0);
    }

    // Call additional calculations if needed
    pile_calculations(frm);
}


function pile_calculations(frm) {
    let cp = parseFloat(frm.doc.consumption_percentage) || 0;
    let gcp = parseFloat(frm.doc.ground_consumption_percentage) || 0;
    let hcp = parseFloat(frm.doc.hem_consumption_percentage) || 0;
    let pile = 100 - (cp + gcp + hcp);
    frm.set_value("pile", pile);
}


function calculate_weft_count(frm) {
    // Get the values of weft_thread, reduction, and thread_type
    const weft_thread = frm.doc.weft_thread || 0; // Default to 0 if not set
    const reduction = frm.doc.reduction || 0;    // Default to 0 if not set
    const thread_type = frm.doc.thread_type;      // Can be "Single" or "Double"

    let weft_count = 0;

    // Perform calculation based on thread_type
    if (thread_type == "SINGLE") {
        weft_count = weft_thread - reduction;
    } else if (thread_type == "DOUBLE") {
        weft_count = (weft_thread / 2) - reduction;
    }

    // Set the calculated value in the weft_count field
    frm.set_value('weft_count', weft_count);
}

function calculate_yarn_count(frm) {
    // Get the values of weft_thread, reduction, and thread_type
    const yarn = frm.doc.yarn || 0; // Default to 0 if not set
    const reduction = frm.doc.reduction || 0;    // Default to 0 if not set
    const thread_type = frm.doc.thread_type;      // Can be "Single" or "Double"

    let yarn_count = 0;

    // Perform calculation based on thread_type
    if (thread_type == "SINGLE") {
        yarn_count = yarn - reduction;
    } else if (thread_type == "DOUBLE") {
        yarn_count = (yarn / 2) - reduction;
    }

    // Set the calculated value in the weft_count field
    frm.set_value('yarn_count', yarn_count);
}

function calculate_yarn_count(frm) {
    // Get the values of yarn, reduction, and thread_type
    const yarn = frm.doc.yarn || 0; // Default to 0 if not set
    const reduction = frm.doc.ground_reduction || 0; // Default to 0 if not set
    const thread_type = frm.doc.ground_thread_type || ""; // Default to empty string if not set

    let yarn_count = 0;

    // Perform calculation based on thread_type
    if (thread_type.toUpperCase() === "SINGLE") {
        yarn_count = yarn - reduction;
    } else if (thread_type.toUpperCase() === "DOUBLE") {
        yarn_count = (yarn / 2) - reduction;
    }

    // Set the calculated value in the yarn_count field
    frm.set_value('yarn_count', yarn_count);
}

