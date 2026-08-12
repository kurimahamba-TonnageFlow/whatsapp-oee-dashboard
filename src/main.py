# TonnageFlow Pulse - Production Run Tracker

from datetime import datetime


# ==========================================================
# CONFIGURATION
# ==========================================================

UNEXPLAINED_LOSS_MINUTES_THRESHOLD = 10.0


line_technicians_by_line = {
    "Rovema": [
        "Liam",
        "Rovema Technician 2",
        "Rovema Technician 3",
        "Rovema Technician 4",
    ],
    "GIC": [
        "GIC Technician 1",
        "GIC Technician 2",
        "GIC Technician 3",
        "GIC Technician 4",
    ],
    "Guill": [
        "Guill Technician 1",
        "Guill Technician 2",
        "Guill Technician 3",
        "Guill Technician 4",
    ],
}


engineers = [
    "Aaron",
    "Yago",
    "Steve",
    "Dan",
    "Kuri",
]


planned_downtime_types = [
    "None",
    "Label Change",
    "Film Change",
    "CCP Check",
    "Changeover",
]


# ==========================================================
# DISPLAY
# ==========================================================


def welcome():
    print("===================================")
    print("       TonnageFlow Pulse")
    print("     Production Run Tracker")
    print("===================================")


def section(title):
    print()
    print(
        f"=== {title} ==="
    )


# ==========================================================
# TIMESTAMPS
# ==========================================================


def current_timestamp():
    return (
        datetime
        .now()
        .astimezone()
        .isoformat(
            timespec="seconds"
        )
    )


# ==========================================================
# INPUT VALIDATION
# ==========================================================


def get_required_text(question):
    while True:

        value = input(
            question
        ).strip()

        if value:
            return value

        print(
            "This field cannot be blank."
        )


def get_yes_no(question):
    while True:

        answer = input(
            question
        ).strip().lower()

        if answer in (
            "yes",
            "y",
        ):
            return "yes"

        if answer in (
            "no",
            "n",
        ):
            return "no"

        print(
            "Please enter Yes or No."
        )


def get_status(question):
    while True:

        status = input(
            question
        ).strip().lower()

        if status == "resolved":
            return "resolved"

        if status == "ongoing":
            return "ongoing"

        print(
            "Please enter Resolved or Ongoing."
        )


def get_int(
    question,
    minimum=None,
    maximum=None,
):
    while True:

        value = input(
            question
        ).strip()

        try:
            number = int(
                value
            )

        except ValueError:

            print(
                "Please enter a whole number."
            )

            continue

        if (
            minimum is not None
            and number < minimum
        ):

            print(
                f"Please enter a number "
                f"of at least {minimum}."
            )

            continue

        if (
            maximum is not None
            and number > maximum
        ):

            print(
                f"Please enter a number "
                f"no greater than {maximum}."
            )

            continue

        return number


def get_float(
    question,
    minimum=None,
    maximum=None,
):
    while True:

        value = input(
            question
        ).strip()

        try:
            number = float(
                value
            )

        except ValueError:

            print(
                "Please enter a valid number."
            )

            continue

        if (
            minimum is not None
            and number < minimum
        ):

            print(
                f"Please enter a number "
                f"of at least {minimum}."
            )

            continue

        if (
            maximum is not None
            and number > maximum
        ):

            print(
                f"Please enter a number "
                f"no greater than {maximum}."
            )

            continue

        return number


def choose_option(
    title,
    options,
):
    while True:

        print()
        print(
            title
        )

        for (
            number,
            option,
        ) in enumerate(
            options,
            start=1,
        ):

            print(
                f"{number} - {option}"
            )

        answer = input(
            "Select option: "
        ).strip()

        if answer.isdigit():

            selected_number = int(
                answer
            )

            if (
                1
                <= selected_number
                <= len(options)
            ):

                return options[
                    selected_number - 1
                ]

        for option in options:

            if (
                answer.lower()
                == option.lower()
            ):

                return option

        print(
            "Selection not recognised. "
            "Please try again."
        )


def get_engineering_text(
    question,
):
    """
    Engineering findings and actions
    are free text.

    If the engineer accidentally enters
    only 'Ongoing' or 'Resolved', Pulse
    warns them because those words are
    usually intended for the status field.
    """

    while True:

        value = get_required_text(
            question
        )

        if (
            value.strip().lower()
            not in (
                "ongoing",
                "resolved",
            )
        ):

            return value

        print()
        print(
            "That looks like an "
            "Engineering Status rather "
            "than technical information."
        )

        use_anyway = get_yes_no(
            "Use this text anyway? "
            "(Yes/No): "
        )

        if use_anyway == "yes":
            return value


# ==========================================================
# RUN ACTIVITY
# ==========================================================


def get_run_activity():

    activity = choose_option(
        "=== Production Run Activity ===",
        [
            "Machine Down",
            "Hourly Update",
            "Show Open Faults",
        ],
    )

    if (
        activity
        == "Machine Down"
    ):

        return "machine_down"

    if (
        activity
        == "Hourly Update"
    ):

        return "hourly_update"

    return "show_faults"


# ==========================================================
# EVENT SYSTEM
# ==========================================================


def record_event(
    run,
    event_type,
    reason,
    reported_by,
    **extra_data,
):

    event = {
        "timestamp":
            current_timestamp(),

        "event_type":
            event_type,

        "reason":
            reason,

        "reported_by":
            reported_by,
    }

    event.update(
        extra_data
    )

    run[
        "events"
    ].append(
        event
    )

    return event


# ==========================================================
# PRODUCTION RUN SETUP
# ==========================================================


def collect_run_setup():

    section(
        "Start Production Run"
    )

    production_line = (
        choose_option(
            "Select Production Line",
            list(
                line_technicians_by_line.keys()
            ),
        )
    )

    line_technician = (
        choose_option(
            "Select Line Technician",
            line_technicians_by_line[
                production_line
            ],
        )
    )

    shift = get_required_text(
        "Shift: "
    )

    customer = get_required_text(
        "Customer: "
    )

    # Product remains free text for MVP.
    # The confirmation screen below protects
    # against accidental shifted entries.
    product = get_required_text(
        "Product: "
    )

    pack_weight = get_required_text(
        "Pack Weight "
        "(example 1kg): "
    )

    packs_per_case = get_int(
        "Packs per Case "
        "(example 8): ",
        minimum=1,
    )

    pack_type = get_required_text(
        "Pack Type "
        "(example Pillow Pack): "
    )

    target_speed_ppm = get_float(
        "Target Speed - "
        "Packs per Minute: ",
        minimum=0.01,
    )

    cases_per_pallet = get_int(
        "Cases per Pallet: ",
        minimum=1,
    )

    pallets_remaining = get_int(
        "Pallets Remaining on Job: ",
        minimum=0,
    )

    previous_run_completed = get_int(
        "Previous Run "
        "Pallets Completed: ",
        minimum=0,
    )

    return {
        "production_line":
            production_line,

        "line_technician":
            line_technician,

        "shift":
            shift,

        "customer":
            customer,

        "product":
            product,

        "pack_weight":
            pack_weight,

        "packs_per_case":
            packs_per_case,

        "pack_type":
            pack_type,

        "target_speed_ppm":
            target_speed_ppm,

        "cases_per_pallet":
            cases_per_pallet,

        "pallets_remaining":
            pallets_remaining,

        "previous_run_completed":
            previous_run_completed,
    }


def display_run_setup_summary(
    setup,
):

    section(
        "Confirm Production Run"
    )

    print(
        f"Production Line: "
        f"{setup['production_line']}"
    )

    print(
        f"Line Technician: "
        f"{setup['line_technician']}"
    )

    print(
        f"Shift: "
        f"{setup['shift']}"
    )

    print(
        f"Customer: "
        f"{setup['customer']}"
    )

    print(
        f"Product: "
        f"{setup['product']}"
    )

    print(
        f"Pack Weight: "
        f"{setup['pack_weight']}"
    )

    print(
        f"Packs per Case: "
        f"{setup['packs_per_case']}"
    )

    print(
        f"Pack Type: "
        f"{setup['pack_type']}"
    )

    print(
        f"Target Speed: "
        f"{setup['target_speed_ppm']} ppm"
    )

    print(
        f"Cases per Pallet: "
        f"{setup['cases_per_pallet']}"
    )

    print(
        f"Pallets Remaining: "
        f"{setup['pallets_remaining']}"
    )

    print(
        f"Previous Run Pallets Completed: "
        f"{setup['previous_run_completed']}"
    )


def start_production_run(
    carried_faults=None,
):

    while True:

        setup = (
            collect_run_setup()
        )

        display_run_setup_summary(
            setup
        )

        confirmed = get_yes_no(
            "Is this Production Run "
            "setup correct? "
            "(Yes/No): "
        )

        if confirmed == "yes":
            break

        print()
        print(
            "Production Run setup cancelled."
        )

        print(
            "Please re-enter the details."
        )


    if carried_faults is None:
        carried_faults = []


    next_fault_id = 1

    if carried_faults:

        next_fault_id = (
            max(
                fault[
                    "fault_id"
                ]
                for fault
                in carried_faults
            )
            + 1
        )


    run = {
        **setup,

        "run_started_at":
            current_timestamp(),

        "total_pallets_completed":
            0,

        "potential_overrun_pallets":
            0,

        "confirmed_overrun_pallets":
            0,

        "open_faults":
            carried_faults,

        "next_fault_id":
            next_fault_id,

        "events":
            [],
    }

    return run


# ==========================================================
# PRODUCTION CALCULATIONS
# ==========================================================


def calculate_expected_output(
    run,
):

    expected_packs_per_hour = (
        run[
            "target_speed_ppm"
        ]
        * 60
    )

    expected_cases_per_hour = (
        expected_packs_per_hour
        / run[
            "packs_per_case"
        ]
    )

    expected_pallets_per_hour = (
        expected_cases_per_hour
        / run[
            "cases_per_pallet"
        ]
    )

    return (
        expected_packs_per_hour,
        expected_cases_per_hour,
        expected_pallets_per_hour,
    )


def calculate_hour_performance(
    run,
    hourly_update,
):

    (
        expected_packs,
        expected_cases,
        expected_pallets,
    ) = calculate_expected_output(
        run
    )

    actual_pallets = hourly_update[
        "pallets_completed_this_hour"
    ]

    actual_cases = (
        actual_pallets
        * run[
            "cases_per_pallet"
        ]
    )

    actual_packs = (
        actual_cases
        * run[
            "packs_per_case"
        ]
    )

    lost_packs = max(
        0,
        expected_packs
        - actual_packs,
    )

    estimated_lost_minutes = (
        lost_packs
        / run[
            "target_speed_ppm"
        ]
    )

    return {
        "expected_packs":
            expected_packs,

        "expected_cases":
            expected_cases,

        "expected_pallets":
            expected_pallets,

        "actual_packs":
            actual_packs,

        "actual_cases":
            actual_cases,

        "actual_pallets":
            actual_pallets,

        "lost_packs":
            lost_packs,

        "estimated_lost_minutes":
            estimated_lost_minutes,
    }


# ==========================================================
# FAULT CREATION
# ==========================================================


def create_fault(
    run,
    machine,
    reason,
    retrospective=False,
):

    fault_id = run[
        "next_fault_id"
    ]

    run[
        "next_fault_id"
    ] += 1


    fault = {
        "fault_id":
            fault_id,

        "machine":
            machine,

        "reason":
            reason,

        "reported_by":
            run[
                "line_technician"
            ],

        "reported_at":
            current_timestamp(),

        "engineer_called":
            "no",

        "production_status":
            "Ongoing",

        "engineering_status":
            "Not Started",

        "engineer":
            None,

        "retrospective":
            retrospective,
    }


    run[
        "open_faults"
    ].append(
        fault
    )

    return fault


# ==========================================================
# OPEN FAULT DISPLAY
# ==========================================================


def display_open_faults(
    run,
):

    section(
        "Open Faults"
    )

    if not run[
        "open_faults"
    ]:

        print(
            "No open faults."
        )

        return


    for fault in run[
        "open_faults"
    ]:

        print()

        print(
            f"Fault #{fault['fault_id']}"
        )

        print(
            f"Machine: "
            f"{fault['machine']}"
        )

        print(
            f"Reason: "
            f"{fault['reason']}"
        )

        print(
            f"Reported At: "
            f"{fault['reported_at']}"
        )

        print(
            f"Production Status: "
            f"{fault['production_status']}"
        )

        print(
            f"Engineering Status: "
            f"{fault['engineering_status']}"
        )

        print(
            f"Engineer Called: "
            f"{fault['engineer_called'].title()}"
        )

        if (
            fault[
                "engineer"
            ]
            is not None
        ):

            print(
                f"Engineer: "
                f"{fault['engineer']}"
            )


# ==========================================================
# ENGINEERING WORKFLOW
# ==========================================================


def capture_engineering_update(
    run,
    fault,
    event_type,
    finding_prompt,
    action_prompt,
):

    section(
        event_type
    )

    print(
        f"Fault #{fault['fault_id']}"
    )

    print(
        f"{fault['machine']} - "
        f"{fault['reason']}"
    )


    engineer = choose_option(
        "Select Engineer",
        engineers,
    )


    finding = get_engineering_text(
        finding_prompt
    )


    action = get_engineering_text(
        action_prompt
    )


    status = get_status(
        "Engineering Status "
        "(Resolved/Ongoing): "
    )


    fault[
        "engineer"
    ] = engineer

    fault[
        "engineering_status"
    ] = status.title()


    record_event(
        run,
        event_type,
        finding,
        engineer,

        fault_id=fault[
            "fault_id"
        ],

        machine=fault[
            "machine"
        ],

        fault=fault[
            "reason"
        ],

        action=action,

        status=status.title(),
    )


    print()
    print(
        "Engineering update recorded."
    )

    print(
        f"Fault #{fault['fault_id']}"
    )

    print(
        f"Engineer: {engineer}"
    )

    print(
        f"Finding / Update: "
        f"{finding}"
    )

    print(
        f"Action: {action}"
    )

    print(
        f"Engineering Status: "
        f"{status.title()}"
    )

    return status


def engineering_initial_response(
    run,
    fault,
):

    return (
        capture_engineering_update(
            run=run,

            fault=fault,

            event_type=
                "Engineering Investigation",

            finding_prompt=
                "Initial Finding: ",

            action_prompt=
                "Action / Investigation: ",
        )
    )


def engineering_follow_up(
    run,
    fault,
):

    return (
        capture_engineering_update(
            run=run,

            fault=fault,

            event_type=
                "Engineering Update",

            finding_prompt=
                "Why is the fault "
                "still ongoing? ",

            action_prompt=
                "What is being done? ",
        )
    )


# ==========================================================
# ENGINEER CALLED
# ==========================================================


def ensure_engineer_called(
    run,
    fault,
):

    if (
        fault[
            "engineer_called"
        ]
        == "yes"
    ):

        return False


    print()
    print(
        f"Fault #{fault['fault_id']} "
        "does not yet have an "
        "engineer called."
    )


    engineer_called = get_yes_no(
        "Has an Engineer now been "
        "called? "
        "(Yes/No): "
    )


    fault[
        "engineer_called"
    ] = engineer_called


    if engineer_called == "no":
        return False


    record_event(
        run,
        "Engineering",
        "Engineer Called",
        run[
            "line_technician"
        ],

        fault_id=fault[
            "fault_id"
        ],

        machine=fault[
            "machine"
        ],

        fault=fault[
            "reason"
        ],
    )


    engineering_initial_response(
        run,
        fault,
    )


    # Important:
    # True means the initial response
    # has already happened during this
    # verification cycle.
    return True


# ==========================================================
# LIVE MACHINE DOWN EVENT
# ==========================================================


def report_machine_down(
    run,
):

    section(
        "MACHINE DOWN"
    )


    machine = get_required_text(
        "Machine / Area: "
    )


    reason = get_required_text(
        "Reason: "
    )


    technician = run[
        "line_technician"
    ]


    fault = create_fault(
        run,
        machine,
        reason,
    )


    record_event(
        run,
        "Machine Down",
        reason,
        technician,

        fault_id=fault[
            "fault_id"
        ],

        machine=machine,

        status="Ongoing",
    )


    print()
    print(
        f"Fault #{fault['fault_id']} "
        "opened."
    )


    engineer_called = get_yes_no(
        "Has an Engineer Been Called? "
        "(Yes/No): "
    )


    fault[
        "engineer_called"
    ] = engineer_called


    if engineer_called == "yes":

        record_event(
            run,
            "Engineering",
            "Engineer Called",
            technician,

            fault_id=fault[
                "fault_id"
            ],

            machine=machine,

            fault=reason,
        )


        engineering_initial_response(
            run,
            fault,
        )


    else:

        print()
        print(
            f"Fault #{fault['fault_id']} "
            "remains open without "
            "engineering response."
        )


# ==========================================================
# OPEN FAULT VERIFICATION
# ==========================================================


def verify_open_faults(
    run,
):

    summary = {
        "verified_faults":
            0,

        "resolved_faults":
            0,

        "ongoing_faults":
            0,
    }


    if not run[
        "open_faults"
    ]:

        return summary


    section(
        "Open Fault Verification"
    )


    resolved_faults = []


    # Work on a copy so resolved
    # faults can safely be removed later.
    for fault in list(
        run[
            "open_faults"
        ]
    ):

        print()

        print(
            f"Fault #{fault['fault_id']}"
        )

        print(
            f"Machine: "
            f"{fault['machine']}"
        )

        print(
            f"Reason: "
            f"{fault['reason']}"
        )

        print(
            f"Engineering Status: "
            f"{fault['engineering_status']}"
        )


        fault_status = get_status(
            "Line Technician Fault Status "
            "(Resolved/Ongoing): "
        )


        summary[
            "verified_faults"
        ] += 1


        record_event(
            run,
            "Fault Verification",
            fault[
                "reason"
            ],
            run[
                "line_technician"
            ],

            fault_id=fault[
                "fault_id"
            ],

            machine=fault[
                "machine"
            ],

            status=
                fault_status.title(),
        )


        # --------------------------------------------------
        # RESOLVED BY LINE TECHNICIAN
        # --------------------------------------------------

        if (
            fault_status
            == "resolved"
        ):

            fault[
                "production_status"
            ] = "Resolved"


            summary[
                "resolved_faults"
            ] += 1


            record_event(
                run,
                "Machine Status",
                "Production Fault Resolved",
                run[
                    "line_technician"
                ],

                fault_id=fault[
                    "fault_id"
                ],

                machine=fault[
                    "machine"
                ],

                fault=fault[
                    "reason"
                ],

                status="Resolved",
            )


            resolved_faults.append(
                fault
            )


            print()
            print(
                f"Fault #{fault['fault_id']} "
                "confirmed resolved by "
                "Line Technician."
            )


            continue


        # --------------------------------------------------
        # STILL ONGOING
        # --------------------------------------------------

        fault[
            "production_status"
        ] = "Ongoing"


        summary[
            "ongoing_faults"
        ] += 1


        record_event(
            run,
            "Machine Status",
            "Production Fault Ongoing",
            run[
                "line_technician"
            ],

            fault_id=fault[
                "fault_id"
            ],

            machine=fault[
                "machine"
            ],

            fault=fault[
                "reason"
            ],

            status="Ongoing",
        )


        print()
        print(
            f"Fault #{fault['fault_id']} "
            "is still ongoing."
        )


        newly_called = (
            ensure_engineer_called(
                run,
                fault,
            )
        )


        # The initial response has just
        # happened, so don't immediately
        # ask for a second response.
        if newly_called:
            continue


        # Engineer was already involved.
        # An ongoing production fault now
        # requires another engineer update.
        if (
            fault[
                "engineer_called"
            ]
            == "yes"
        ):

            engineering_follow_up(
                run,
                fault,
            )


    # Remove resolved faults only once
    # verification is complete.
    for fault in resolved_faults:

        run[
            "open_faults"
        ].remove(
            fault
        )


    return summary


# ==========================================================
# RETROSPECTIVE DOWNTIME
# ==========================================================


def capture_retrospective_downtime(
    run,
):

    unreported_downtime = get_yes_no(
        "Any other unreported "
        "unplanned downtime this hour? "
        "(Yes/No): "
    )


    if (
        unreported_downtime
        == "no"
    ):

        return {
            "reported":
                False,

            "fault_id":
                None,

            "machine":
                None,

            "reason":
                None,
        }


    machine = get_required_text(
        "Machine / Area: "
    )


    reason = get_required_text(
        "Unplanned Downtime Reason: "
    )


    fault = create_fault(
        run,
        machine,
        reason,
        retrospective=True,
    )


    record_event(
        run,
        "Unplanned Downtime",
        reason,
        run[
            "line_technician"
        ],

        fault_id=fault[
            "fault_id"
        ],

        machine=machine,

        status="Retrospective",
    )


    already_resolved = get_yes_no(
        "Is this retrospective fault "
        "already resolved? "
        "(Yes/No): "
    )


    if (
        already_resolved
        == "yes"
    ):

        fault[
            "production_status"
        ] = "Resolved"


        record_event(
            run,
            "Machine Status",
            "Retrospective Production "
            "Fault Resolved",
            run[
                "line_technician"
            ],

            fault_id=fault[
                "fault_id"
            ],

            machine=machine,

            fault=reason,

            status="Resolved",
        )


        run[
            "open_faults"
        ].remove(
            fault
        )


    return {
        "reported":
            True,

        "fault_id":
            fault[
                "fault_id"
            ],

        "machine":
            machine,

        "reason":
            reason,
    }


# ==========================================================
# HOURLY UPDATE
# ==========================================================


def collect_hourly_update(
    run,
):

    section(
        "Hourly Production Update"
    )


    oee = get_float(
        "OEE (%): ",
        minimum=0,
        maximum=100,
    )


    pallets_completed_this_hour = (
        get_int(
            "Pallets Completed "
            "This Hour: ",
            minimum=0,
        )
    )


    planned_downtime = (
        choose_option(
            "Planned Downtime",
            planned_downtime_types,
        )
    )


    fault_summary = {
        "verified_faults":
            0,

        "resolved_faults":
            0,

        "ongoing_faults":
            0,
    }


    if run[
        "open_faults"
    ]:

        fault_summary = (
            verify_open_faults(
                run
            )
        )


    # Always check whether something
    # else happened, even if known
    # faults already existed.
    retrospective_downtime = (
        capture_retrospective_downtime(
            run
        )
    )


    return {
        "oee":
            oee,

        "pallets_completed_this_hour":
            pallets_completed_this_hour,

        "planned_downtime":
            planned_downtime,

        "verified_faults":
            fault_summary[
                "verified_faults"
            ],

        "resolved_faults":
            fault_summary[
                "resolved_faults"
            ],

        "ongoing_faults":
            fault_summary[
                "ongoing_faults"
            ],

        "retrospective_downtime":
            retrospective_downtime,

        "unexplained_loss":
            False,

        "unexplained_loss_reason":
            None,
    }


# ==========================================================
# UNEXPLAINED PRODUCTION LOSS
# ==========================================================


def check_unexplained_production_loss(
    run,
    hourly_update,
    performance,
):

    lost_minutes = performance[
        "estimated_lost_minutes"
    ]


    # Ignore normal small variation.
    if (
        lost_minutes
        < UNEXPLAINED_LOSS_MINUTES_THRESHOLD
    ):

        return


    planned_downtime_recorded = (
        hourly_update[
            "planned_downtime"
        ]
        != "None"
    )


    known_fault_recorded = (
        hourly_update[
            "verified_faults"
        ]
        > 0
    )


    retrospective_recorded = (
        hourly_update[
            "retrospective_downtime"
        ][
            "reported"
        ]
    )


    loss_has_explanation = (
        planned_downtime_recorded
        or known_fault_recorded
        or retrospective_recorded
    )


    if loss_has_explanation:
        return


    print()
    print(
        "==================================="
    )

    print(
        "  UNEXPLAINED PRODUCTION LOSS"
    )

    print(
        "==================================="
    )


    print(
        f"OEE: "
        f"{hourly_update['oee']}%"
    )


    print(
        f"Expected Pallets: "
        f"{performance['expected_pallets']:.2f}"
    )


    print(
        f"Actual Pallets: "
        f"{performance['actual_pallets']}"
    )


    print(
        f"Estimated Lost Production Time: "
        f"{lost_minutes:.1f} minutes"
    )


    print()
    print(
        "No planned downtime, known fault "
        "or retrospective downtime explains "
        "this production loss."
    )


    reason = get_required_text(
        "Reason for production loss "
        "(or enter Unknown): "
    )


    hourly_update[
        "unexplained_loss"
    ] = True


    hourly_update[
        "unexplained_loss_reason"
    ] = reason


    record_event(
        run,
        "Unexplained Production Loss",
        reason,
        run[
            "line_technician"
        ],

        oee=hourly_update[
            "oee"
        ],

        expected_pallets=round(
            performance[
                "expected_pallets"
            ],
            2,
        ),

        actual_pallets=
            performance[
                "actual_pallets"
            ],

        lost_packs=round(
            performance[
                "lost_packs"
            ]
        ),

        estimated_lost_minutes=round(
            lost_minutes,
            1,
        ),

        status=
            "Needs Investigation",
    )


# ==========================================================
# PRODUCTION RUN PROGRESS
# ==========================================================


def update_run_progress(
    run,
    hourly_update,
):

    pallets_completed = hourly_update[
        "pallets_completed_this_hour"
    ]


    if (
        run[
            "pallets_remaining"
        ]
        <= 0
    ):

        run[
            "potential_overrun_pallets"
        ] += pallets_completed

        return


    planned_pallets = min(
        pallets_completed,
        run[
            "pallets_remaining"
        ],
    )


    potential_overrun = (
        pallets_completed
        - planned_pallets
    )


    run[
        "total_pallets_completed"
    ] += planned_pallets


    run[
        "pallets_remaining"
    ] -= planned_pallets


    run[
        "potential_overrun_pallets"
    ] += potential_overrun


# ==========================================================
# HOURLY REPORT
# ==========================================================


def display_hourly_report(
    run,
    hourly_update,
    performance,
):

    section(
        "TonnageFlow Pulse"
    )


    print(
        f"Production Line: "
        f"{run['production_line']}"
    )

    print(
        f"Customer: "
        f"{run['customer']}"
    )

    print(
        f"Product: "
        f"{run['product']}"
    )

    print(
        f"Format: "
        f"{run['pack_weight']} x "
        f"{run['packs_per_case']}"
    )

    print(
        f"OEE: "
        f"{hourly_update['oee']}%"
    )

    print(
        f"Pallets Completed This Hour: "
        f"{hourly_update['pallets_completed_this_hour']}"
    )

    print(
        f"Planned Pallets Completed "
        f"This Run: "
        f"{run['total_pallets_completed']}"
    )

    print(
        f"Pallets Remaining: "
        f"{run['pallets_remaining']}"
    )

    print(
        f"Potential Overrun Pallets: "
        f"{run['potential_overrun_pallets']}"
    )


    print()
    print(
        "--- Expected vs Actual ---"
    )


    print(
        f"Expected Packs This Hour: "
        f"{performance['expected_packs']:.0f}"
    )

    print(
        f"Actual Packs This Hour: "
        f"{performance['actual_packs']}"
    )

    print(
        f"Expected Pallets This Hour: "
        f"{performance['expected_pallets']:.2f}"
    )

    print(
        f"Actual Pallets This Hour: "
        f"{performance['actual_pallets']}"
    )

    print(
        f"Estimated Lost Packs: "
        f"{performance['lost_packs']:.0f}"
    )

    print(
        f"Estimated Lost Production Time: "
        f"{performance['estimated_lost_minutes']:.1f} "
        f"minutes"
    )


    print()

    print(
        f"Planned Downtime: "
        f"{hourly_update['planned_downtime']}"
    )

    print(
        f"Faults Verified This Hour: "
        f"{hourly_update['verified_faults']}"
    )

    print(
        f"Faults Resolved This Hour: "
        f"{hourly_update['resolved_faults']}"
    )

    print(
        f"Faults Still Ongoing: "
        f"{hourly_update['ongoing_faults']}"
    )

    print(
        f"Open Faults After Update: "
        f"{len(run['open_faults'])}"
    )


    if hourly_update[
        "unexplained_loss"
    ]:

        print()
        print(
            "WARNING: Unexplained "
            "Production Loss"
        )

        print(
            f"Reason: "
            f"{hourly_update['unexplained_loss_reason']}"
        )


# ==========================================================
# RUN CLOSE VALIDATION
# ==========================================================


def confirm_run_close(
    run,
):

    if not run[
        "open_faults"
    ]:

        return True


    print()
    print(
        "WARNING: Open faults remain."
    )


    display_open_faults(
        run
    )


    close_anyway = get_yes_no(
        "Close Production Run with "
        "these faults still open? "
        "(Yes/No): "
    )


    if (
        close_anyway
        == "no"
    ):

        print()
        print(
            "Production Run remains active."
        )

        return False


    record_event(
        run,
        "Production Run",
        "Run Closed With Open Faults",
        run[
            "line_technician"
        ],

        open_fault_count=len(
            run[
                "open_faults"
            ]
        ),
    )


    return True


# ==========================================================
# CARRY OPEN FAULTS FORWARD
# ==========================================================


def copy_faults_for_next_run(
    run,
):

    carried_faults = []


    for fault in run[
        "open_faults"
    ]:

        copied_fault = (
            fault.copy()
        )

        carried_faults.append(
            copied_fault
        )


    return carried_faults


# ==========================================================
# CHANGEOVER
# ==========================================================


def handle_run_completion(
    run,
):

    section(
        "Production Run Completion"
    )


    changeover_type = (
        choose_option(
            "Select Changeover Type",
            [
                "Product Changeover",
                "Customer Changeover",
            ],
        )
    )


    if (
        changeover_type
        == "Product Changeover"
    ):

        run[
            "confirmed_overrun_pallets"
        ] = run[
            "potential_overrun_pallets"
        ]


        record_event(
            run,
            "Changeover",
            "Product Changeover",
            run[
                "line_technician"
            ],
        )


        print()
        print(
            "Product Changeover"
        )

        print(
            f"Confirmed Overrun: "
            f"{run['confirmed_overrun_pallets']} "
            f"Pallets"
        )

        return


    run[
        "confirmed_overrun_pallets"
    ] = 0


    record_event(
        run,
        "Changeover",
        "Customer Changeover",
        run[
            "line_technician"
        ],
    )


    print()
    print(
        "Customer Changeover"
    )

    print(
        "Same product continues."
    )

    print(
        "No product overrun confirmed."
    )


# ==========================================================
# EVENT HISTORY
# ==========================================================


event_field_labels = {
    "timestamp":
        "Timestamp",

    "fault_id":
        "Fault ID",

    "machine":
        "Machine",

    "fault":
        "Fault",

    "action":
        "Action",

    "status":
        "Status",

    "oee":
        "OEE",

    "pallets_completed":
        "Pallets Completed",

    "open_fault_count":
        "Open Fault Count",

    "previous_run_completed":
        "Previous Run Completed",

    "expected_pallets":
        "Expected Pallets",

    "actual_pallets":
        "Actual Pallets",

    "lost_packs":
        "Lost Packs",

    "estimated_lost_minutes":
        "Estimated Lost Minutes",
}


def display_run_events(
    run,
):

    section(
        "Production Run Events"
    )


    core_fields = {
        "event_type",
        "reason",
        "reported_by",
    }


    for event in run[
        "events"
    ]:

        print()

        print(
            f"{event['event_type']} | "
            f"{event['reason']} | "
            f"Reported by: "
            f"{event['reported_by']}"
        )


        for (
            key,
            value,
        ) in event.items():


            if key in core_fields:
                continue


            label = (
                event_field_labels.get(
                    key,
                    key
                    .replace(
                        "_",
                        " ",
                    )
                    .title(),
                )
            )


            if key == "fault_id":
                value = f"#{value}"


            if key == "oee":
                value = f"{value}%"


            print(
                f"{label}: {value}"
            )


# ==========================================================
# PRODUCTION MODEL DISPLAY
# ==========================================================


def display_production_model(
    run,
):

    (
        expected_packs,
        expected_cases,
        expected_pallets,
    ) = calculate_expected_output(
        run
    )


    section(
        "Production Model"
    )


    print(
        f"Previous Run Completed: "
        f"{run['previous_run_completed']} "
        f"Pallets"
    )


    print(
        f"Expected Packs per Hour: "
        f"{expected_packs:.0f}"
    )


    print(
        f"Expected Cases per Hour: "
        f"{expected_cases:.0f}"
    )


    print(
        f"Expected Pallets per Hour: "
        f"{expected_pallets:.2f}"
    )


    print(
        f"Starting Pallets Remaining: "
        f"{run['pallets_remaining']}"
    )


# ==========================================================
# MAIN SESSION
# ==========================================================


def run_session():

    welcome()


    tracking_finished = False


    # Open faults can survive a
    # Production Run change.
    carried_faults = []


    while not tracking_finished:


        production_run = (
            start_production_run(
                carried_faults=
                    carried_faults
            )
        )


        carried_faults = []


        record_event(
            production_run,
            "Production Run",
            "Production Run Started",
            production_run[
                "line_technician"
            ],

            previous_run_completed=
                production_run[
                    "previous_run_completed"
                ],
        )


        if production_run[
            "open_faults"
        ]:

            record_event(
                production_run,
                "Production Run",
                "Outstanding Faults "
                "Carried Forward",
                production_run[
                    "line_technician"
                ],

                open_fault_count=len(
                    production_run[
                        "open_faults"
                    ]
                ),
            )


        display_production_model(
            production_run
        )


        if production_run[
            "open_faults"
        ]:

            print()
            print(
                "Outstanding faults have "
                "been carried into this "
                "Production Run."
            )

            display_open_faults(
                production_run
            )


        run_finished = False


        # ==================================================
        # PRODUCTION RUN ACTIVITY LOOP
        # ==================================================


        while not run_finished:


            activity = (
                get_run_activity()
            )


            # ----------------------------------------------
            # MACHINE DOWN
            # ----------------------------------------------

            if (
                activity
                == "machine_down"
            ):

                report_machine_down(
                    production_run
                )

                continue


            # ----------------------------------------------
            # SHOW OPEN FAULTS
            # ----------------------------------------------

            if (
                activity
                == "show_faults"
            ):

                display_open_faults(
                    production_run
                )

                continue


            # ----------------------------------------------
            # HOURLY UPDATE
            # ----------------------------------------------

            hourly_update = (
                collect_hourly_update(
                    production_run
                )
            )


            record_event(
                production_run,
                "Hourly Update",
                "Hourly Update Received",
                production_run[
                    "line_technician"
                ],

                oee=hourly_update[
                    "oee"
                ],

                pallets_completed=
                    hourly_update[
                        "pallets_completed_this_hour"
                    ],
            )


            if (
                hourly_update[
                    "planned_downtime"
                ]
                != "None"
            ):

                record_event(
                    production_run,
                    "Planned Downtime",
                    hourly_update[
                        "planned_downtime"
                    ],
                    production_run[
                        "line_technician"
                    ],
                )


            hour_performance = (
                calculate_hour_performance(
                    production_run,
                    hourly_update,
                )
            )


            # SNAG 011 FIX:
            # Do not silently accept
            # significant unexplained loss.
            check_unexplained_production_loss(
                production_run,
                hourly_update,
                hour_performance,
            )


            update_run_progress(
                production_run,
                hourly_update,
            )


            display_hourly_report(
                production_run,
                hourly_update,
                hour_performance,
            )


            # ----------------------------------------------
            # RUN STILL ACTIVE
            # ----------------------------------------------

            if (
                production_run[
                    "pallets_remaining"
                ]
                > 0
            ):

                print()
                print(
                    "Production run continues."
                )

                continue


            # ----------------------------------------------
            # PLANNED QUANTITY COMPLETE
            # ----------------------------------------------

            print()
            print(
                "Planned quantity complete."
            )


            print(
                f"Potential Overrun Pallets: "
                f"{production_run['potential_overrun_pallets']}"
            )


            run_confirmation = (
                get_yes_no(
                    "Is the Production Run "
                    "finished? "
                    "(Yes/No): "
                )
            )


            if (
                run_confirmation
                == "no"
            ):

                print()
                print(
                    "Production Run "
                    "remains active."
                )

                print(
                    "Additional pallets will "
                    "continue to be recorded "
                    "as potential overrun."
                )

                continue


            can_close = (
                confirm_run_close(
                    production_run
                )
            )


            if not can_close:
                continue


            record_event(
                production_run,
                "Production Run",
                "Production Run Finished",
                production_run[
                    "line_technician"
                ],
            )


            run_finished = True


        # ==================================================
        # RUN COMPLETE
        # ==================================================


        handle_run_completion(
            production_run
        )


        section(
            "Production Run Closed"
        )


        print(
            f"Planned Pallets Completed: "
            f"{production_run['total_pallets_completed']}"
        )


        print(
            f"Potential Overrun Pallets: "
            f"{production_run['potential_overrun_pallets']}"
        )


        print(
            f"Confirmed Overrun Pallets: "
            f"{production_run['confirmed_overrun_pallets']}"
        )


        print(
            f"Open Faults at Run Close: "
            f"{len(production_run['open_faults'])}"
        )


        display_run_events(
            production_run
        )


        # Any unresolved fault is retained
        # if the next Production Run starts.
        carried_faults = (
            copy_faults_for_next_run(
                production_run
            )
        )


        next_run = get_yes_no(
            "Start another Production Run? "
            "(Yes/No): "
        )


        if (
            next_run
            == "yes"
        ):

            print()
            print(
                "Preparing next "
                "Production Run..."
            )

            continue


        tracking_finished = True


    print()
    print(
        "=== TonnageFlow Pulse "
        "Session Closed ==="
    )


# ==========================================================
# PROGRAM START
# ==========================================================


if __name__ == "__main__":

    run_session()