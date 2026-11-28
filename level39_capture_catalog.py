"""Filename-clock catalog for the supplied Level 39 captures.

The records below are the notes supplied with those screenshots: filename,
the clock encoded in the filename, and the visibility note that came with
each file. They are not pixel measurements. This module does not read image
bytes, invent a UTC offset, copy annotation labels onto raw captures, merge
the two sessions, or authorize planning, taps, or purchases.
"""

_CONVEYOR_SIDES = ("bottom", "right", "top", "left")
_POPUP_KEYS = ("extra_tray", "magic_glove", "angel_slime", "dragon_roar")
_POPUP_NAMES = {
    "extra_tray": "Extra Tray",
    "magic_glove": "Magic Glove",
    "angel_slime": "Angel Slime",
    "dragon_roar": "Dragon Roar",
}

MISSING_OBSERVATIONS = (
    "image bytes and sha256 for every listed file",
    "UTC offset or EXIF OffsetTimeOriginal (filename clock only; timezone not identified)",
    "pixel colours and board grid contents",
    "shooter positions and ammunition counts on the unmarked screenshots",
    "whether the November 21 and November 27 captures are the same attempt",
    "displayed power-up prices and charges (popup images were not available to transcribe)",
    "conveyor side under the November 27 shop popups",
    "human review confirming or rejecting the red marks and top_1..top_4 labels",
)

_SAFETY = {
    "game_taps_enabled": False,
    "planning_authorized": False,
    "purchase_authorized": False,
    "conveyor_mechanics_validated": False,
    "colour_classification_validated": False,
    "solver_correctness_validated": False,
    "pixel_comparison_performed": False,
    "sessions_same_capture": False,
}


def _clock(filename, hour, minute, second):
    stamp = f"{hour:02d}{minute:02d}{second:02d}"
    if stamp not in filename:
        raise ValueError(f"Filename does not contain clock {stamp}: {filename}")
    return {
        "hour": hour,
        "minute": minute,
        "second": second,
        "text": f"{hour:02d}:{minute:02d}:{second:02d}",
        "source": "filename_clock_only",
        "utc_offset": None,
        "timezone_identified": False,
    }


def _raw(filename, year, month, day, hour, minute, second, *,
         conveyor_side, board_note, popup):
    return {
        "filename": filename,
        "role": "raw_capture",
        "calendar_date": {"year": year, "month": month, "day": day},
        "filename_clock": _clock(filename, hour, minute, second),
        "utc_offset": None,
        "timezone_identified": False,
        "conveyor_side_visible": conveyor_side,
        "board_visibility_note": board_note,
        "popup": popup,
        "ammunition": None,
        "pixel_colours": None,
        "shooter_labels": None,
        "image_sha256": None,
        "bytes_attached": False,
        "observation_basis": "supplied_note_not_pixel_extraction",
    }


def _popup(key):
    if key not in _POPUP_NAMES:
        raise ValueError(f"Unknown power-up popup: {key}")
    return {
        "kind": "shop_popup",
        "power_up_key": key,
        "display_name": _POPUP_NAMES[key],
        "displayed_price": None,
        "displayed_charge": None,
        "price_transcribed": False,
        "purchase_authorized": False,
        "game_action_performed": False,
    }


def _november_21():
    rows = (
        ("Screenshot_20261121-092542_Slime Loop.jpg", 9, 25, 42, "bottom", "not_stated"),
        ("Screenshot_20261121-092544_Slime Loop.jpg", 9, 25, 44, "right", "not_stated"),
        ("Screenshot_20261121-092548_Slime Loop.jpg", 9, 25, 48, "top", "not_stated"),
        ("Screenshot_20261121-092554_Slime Loop.jpg", 9, 25, 54, "left", "not_stated"),
    )
    return {
        "session_id": "level39-filename-20261121",
        "calendar_date": "2026-11-21",
        "timezone_identified": False,
        "utc_offset": None,
        "kept_as_one_session_because": (
            "shared filename date, filename clock order, and the supplied "
            "note that the visible board agrees"
        ),
        "pixel_identity_rechecked": False,
        "captures": [
            _raw(name, 2026, 11, 21, hour, minute, second,
                 conveyor_side=side, board_note=board, popup=None)
            for name, hour, minute, second, side, board in rows
        ],
    }


def _november_27():
    rows = (
        ("Screenshot_20261127-173951_Slime Loop.jpg", 17, 39, 51, None, "not_stated", "extra_tray"),
        ("Screenshot_20261127-173959_Slime Loop.jpg", 17, 39, 59, None, "not_stated", "magic_glove"),
        ("Screenshot_20261127-174012_Slime Loop.jpg", 17, 40, 12, None, "not_stated", "angel_slime"),
        ("Screenshot_20261127-174020_Slime Loop.jpg", 17, 40, 20, None, "not_stated", "dragon_roar"),
        ("Screenshot_20261127-174041_Slime Loop.jpg", 17, 40, 41, "top", "clear_board", None),
    )
    return {
        "session_id": "level39-filename-20261127",
        "calendar_date": "2026-11-27",
        "timezone_identified": False,
        "utc_offset": None,
        "separate_from_session_id": "level39-filename-20261121",
        "captures": [
            _raw(name, 2026, 11, 27, hour, minute, second,
                 conveyor_side=side, board_note=board,
                 popup=None if popup_key is None else _popup(popup_key))
            for name, hour, minute, second, side, board, popup_key in rows
        ],
    }


def _annotated_reference():
    return {
        "filename": "shooter_positions_marked.jpg",
        "role": "annotated_reference",
        "untouched_original": False,
        "annotation_marks": ("red_marks", "top_1", "top_2", "top_3", "top_4"),
        "labels_are_annotations": True,
        "filename_clock": None,
        "timezone_identified": False,
        "utc_offset": None,
        "image_sha256": None,
        "bytes_attached": False,
        "copy_labels_onto_raw_captures": False,
    }


def level39_capture_catalog():
    """Return a fresh catalog. Callers may inspect it; they cannot change the source."""
    return {
        "version": 1,
        "evidence_kind": "filename_clock_and_supplied_visibility_notes",
        "level_claim": (
            "Supplied as Level 39. This catalog does not re-identify the level from pixels."
        ),
        "november_21": _november_21(),
        "november_27": _november_27(),
        "annotated_reference": _annotated_reference(),
        "session_relationship": {
            "status": "unestablished",
            "established_by": None,
        },
        "rotation_model": None,
        "missing_observations": MISSING_OBSERVATIONS,
        "safety": dict(_SAFETY),
        "private_level39_fixtures_replaced": False,
    }


def _clock_tuple(capture):
    clock = capture.get("filename_clock") or {}
    return (clock.get("hour"), clock.get("minute"), clock.get("second"))


def _expect(errors, condition, message):
    if not condition:
        errors.append(message)


def validate_level39_catalog(catalog):
    """Return error strings. An empty list means the catalog kept the fail-closed contract."""
    errors = []
    if not isinstance(catalog, dict):
        return ["Catalog must be a dict"]

    safety = catalog.get("safety")
    if not isinstance(safety, dict):
        errors.append("Missing safety flags")
    else:
        for key, expected in _SAFETY.items():
            _expect(errors, safety.get(key) is expected, f"Safety flag {key} must be {expected}")

    _expect(errors, catalog.get("rotation_model") is None,
            "Conveyor rotation must not be inferred from side notes")
    _expect(errors, catalog.get("private_level39_fixtures_replaced") is False,
            "This catalog must not stand in for private Level 39 fixtures")
    relationship = catalog.get("session_relationship") or {}
    _expect(errors, relationship.get("status") == "unestablished",
            "Session relationship must stay unestablished in this catalog")
    _expect(errors, relationship.get("established_by") is None,
            "No check has established that the two sessions are the same capture")
    _expect(errors, catalog.get("missing_observations") == MISSING_OBSERVATIONS,
            "Missing-observation list must stay explicit")

    nov21 = catalog.get("november_21")
    nov27 = catalog.get("november_27")
    if not isinstance(nov21, dict) or not isinstance(nov27, dict):
        errors.append("Both sessions are required")
        return errors

    _expect(errors, nov21.get("session_id") == "level39-filename-20261121",
            "November 21 session id changed")
    _expect(errors, nov27.get("session_id") == "level39-filename-20261127",
            "November 27 session id changed")
    _expect(errors, nov21.get("session_id") != nov27.get("session_id"),
            "Sessions must not share an id")
    _expect(errors, nov27.get("separate_from_session_id") == nov21.get("session_id"),
            "November 27 must stay separate from November 21")
    _expect(errors, nov21.get("pixel_identity_rechecked") is False,
            "This catalog did not recheck that the November 21 boards match")
    _expect(errors, nov21.get("timezone_identified") is False and nov21.get("utc_offset") is None,
            "November 21 timezone was not identified")
    _expect(errors, nov27.get("timezone_identified") is False and nov27.get("utc_offset") is None,
            "November 27 timezone was not identified")

    captures21 = nov21.get("captures")
    captures27 = nov27.get("captures")
    _expect(errors, isinstance(captures21, list) and len(captures21) == 4,
            "November 21 session must contain the four supplied captures")
    _expect(errors, isinstance(captures27, list) and len(captures27) == 5,
            "November 27 session must contain the five supplied captures")
    if not isinstance(captures21, list) or not isinstance(captures27, list):
        return errors

    _validate_session_clocks(errors, captures21, year=2026, month=11, day=21)
    _validate_session_clocks(errors, captures27, year=2026, month=11, day=27)
    _validate_conveyor_notes(errors, captures21)
    _validate_november_27_notes(errors, captures27)

    annotated = catalog.get("annotated_reference")
    if not isinstance(annotated, dict):
        errors.append("Annotated reference is required")
    else:
        _validate_annotated(errors, annotated, captures21 + captures27)

    return errors


def _validate_session_clocks(errors, captures, *, year, month, day):
    previous = None
    filenames = []
    for capture in captures:
        if not isinstance(capture, dict):
            errors.append("Capture must be a dict")
            continue
        filenames.append(capture.get("filename"))
        date = capture.get("calendar_date") or {}
        _expect(
            errors,
            (date.get("year"), date.get("month"), date.get("day")) == (year, month, day),
            f"Unexpected calendar date on {capture.get('filename')}",
        )
        _expect(errors, capture.get("role") == "raw_capture",
                f"{capture.get('filename')} is not a raw capture")
        _expect(errors, capture.get("utc_offset") is None, "UTC offset must stay unset")
        _expect(errors, capture.get("timezone_identified") is False,
                "Timezone must stay unidentified")
        _expect(errors, capture.get("ammunition") is None, "Ammunition was not observed")
        _expect(errors, capture.get("pixel_colours") is None, "Pixel colours were not extracted")
        _expect(errors, capture.get("shooter_labels") is None,
                "Shooter labels must not be copied onto a raw capture")
        _expect(errors, capture.get("image_sha256") is None and capture.get("bytes_attached") is False,
                "Image bytes are not attached")
        _expect(errors, capture.get("observation_basis") == "supplied_note_not_pixel_extraction",
                "Visibility notes must not be presented as pixel extraction")
        clock = capture.get("filename_clock") or {}
        _expect(errors, clock.get("source") == "filename_clock_only",
                "Clock source must be the filename only")
        _expect(errors, clock.get("utc_offset") is None and clock.get("timezone_identified") is False,
                "Filename clock must not gain a timezone")
        stamp = _clock_tuple(capture)
        _expect(errors, all(isinstance(part, int) for part in stamp), "Clock parts must be integers")
        if previous is not None:
            _expect(errors, stamp > previous, "Filename clocks must stay in ascending order")
        previous = stamp
        filename = capture.get("filename")
        if isinstance(filename, str) and all(isinstance(part, int) for part in stamp):
            encoded = f"{stamp[0]:02d}{stamp[1]:02d}{stamp[2]:02d}"
            _expect(errors, encoded in filename, "Stored clock does not match the filename")
            prefix = f"Screenshot_{year}{month:02d}{day:02d}-{encoded}_Slime Loop.jpg"
            _expect(errors, filename == prefix, f"Unexpected filename: {filename}")
    _expect(errors, len(filenames) == len(set(filenames)), "Duplicate capture filename")


def _validate_conveyor_notes(errors, captures):
    sides = [capture.get("conveyor_side_visible") for capture in captures if isinstance(capture, dict)]
    _expect(errors, tuple(sides) == _CONVEYOR_SIDES,
            "November 21 conveyor notes must stay bottom, right, top, left")
    for capture in captures:
        if isinstance(capture, dict):
            _expect(errors, capture.get("popup") is None,
                    "November 21 captures are not shop popups")


def _validate_november_27_notes(errors, captures):
    if len(captures) != 5:
        return
    expected = (
        ("extra_tray", None, "not_stated"),
        ("magic_glove", None, "not_stated"),
        ("angel_slime", None, "not_stated"),
        ("dragon_roar", None, "not_stated"),
        (None, "top", "clear_board"),
    )
    for capture, (key, side, board) in zip(captures, expected):
        if not isinstance(capture, dict):
            continue
        _expect(errors, capture.get("conveyor_side_visible") == side,
                f"Unexpected conveyor note on {capture.get('filename')}")
        _expect(errors, capture.get("board_visibility_note") == board,
                f"Unexpected board note on {capture.get('filename')}")
        popup = capture.get("popup")
        if key is None:
            _expect(errors, popup is None, "Clear-board capture is not a shop popup")
            continue
        if not isinstance(popup, dict):
            errors.append(f"Missing shop popup on {capture.get('filename')}")
            continue
        _expect(errors, popup.get("kind") == "shop_popup", "Popup kind must stay shop_popup")
        _expect(errors, popup.get("power_up_key") == key, "Unexpected power-up key")
        _expect(errors, popup.get("display_name") == _POPUP_NAMES[key], "Unexpected power-up name")
        _expect(errors, popup.get("displayed_price") is None, "Popup price was not transcribed")
        _expect(errors, popup.get("displayed_charge") is None, "Popup charge was not transcribed")
        _expect(errors, popup.get("price_transcribed") is False, "Price must stay untranscribed")
        _expect(errors, popup.get("purchase_authorized") is False, "Popup does not authorize purchase")
        _expect(errors, popup.get("game_action_performed") is False, "Popup does not perform a game action")
        _expect(errors, key in _POPUP_KEYS, "Unknown power-up key")


def _validate_annotated(errors, annotated, raw_captures):
    filename = annotated.get("filename")
    _expect(errors, filename == "shooter_positions_marked.jpg",
            "Annotated reference filename changed")
    _expect(errors, annotated.get("role") == "annotated_reference",
            "Annotated file must not be treated as a raw capture")
    _expect(errors, annotated.get("untouched_original") is False,
            "shooter_positions_marked.jpg is not an untouched original")
    _expect(errors, annotated.get("labels_are_annotations") is True,
            "top_1..top_4 labels are annotations")
    _expect(errors, annotated.get("copy_labels_onto_raw_captures") is False,
            "Annotation labels must not be copied onto unmarked screenshots")
    _expect(errors, annotated.get("filename_clock") is None, "Annotated file has no filename clock")
    _expect(errors, annotated.get("utc_offset") is None and annotated.get("timezone_identified") is False,
            "Annotated file timezone was not identified")
    _expect(errors, annotated.get("bytes_attached") is False and annotated.get("image_sha256") is None,
            "Annotated image bytes are not attached")
    _expect(
        errors,
        tuple(annotated.get("annotation_marks") or ()) == ("red_marks", "top_1", "top_2", "top_3", "top_4"),
        "Annotation marks must stay limited to the supplied red marks and top labels",
    )
    raw_names = {capture.get("filename") for capture in raw_captures if isinstance(capture, dict)}
    _expect(errors, filename not in raw_names, "Annotated reference was merged into a raw session")


def link_sessions(_proof=None):
    """Refuse to merge the November sessions.

    A later pixel or provenance check might relate them. This catalog does not
    perform that check and does not accept a caller-supplied link in its place.
    """
    return {
        "linked": False,
        "reason": "NOT_ESTABLISHED_BY_THIS_CATALOG",
        "session_relationship": "unestablished",
        "planning_authorized": False,
        "purchase_authorized": False,
        "game_taps_enabled": False,
    }


def transfer_annotation_labels(raw_filename, labels):
    """Refuse to paint annotated labels onto an unmarked screenshot."""
    return {
        "applied": False,
        "reason": "ANNOTATED_LABELS_ARE_NOT_RAW_OBSERVATIONS",
        "raw_filename": raw_filename,
        "labels_not_copied": list(labels) if labels is not None else [],
        "planning_authorized": False,
        "game_taps_enabled": False,
    }


def catalog_is_planning_eligible(catalog=None):
    """Planning stays closed. Catalog validity is not gameplay eligibility."""
    del catalog
    return False
