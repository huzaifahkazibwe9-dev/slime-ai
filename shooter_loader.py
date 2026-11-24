import json
from pathlib import Path

from game_state import Shooter
from geometry_adapter import apply_geometry

DETECTION_FILE = Path("data/shooter_detection.json")


def load_shooters(path=DETECTION_FILE, geometry_observations=None):
    data = json.loads(Path(path).read_text())
    if not isinstance(data, dict):
        raise ValueError("Shooter detection must be a JSON object")
    detected = data.get("visible_shooters")
    groups = data.get("bonded_groups", [])
    if not isinstance(detected, list):
        raise ValueError("visible_shooters must be a list")
    if not isinstance(groups, list):
        raise ValueError("bonded_groups must be a list")
    if any(not isinstance(group, list) for group in groups):
        raise ValueError("Each bonded group must be a list")

    # Validate identifiers before filtering weak samples. Otherwise malformed
    # IDs on discarded records can raise TypeError or disappear from validation.
    all_ids = []
    for index, item in enumerate(detected):
        if not isinstance(item, dict):
            raise ValueError(f"Shooter entry {index} must be an object")
        shooter_id = item.get("id")
        if not isinstance(shooter_id, str) or not shooter_id:
            raise ValueError(f"Shooter entry {index} has an invalid id")
        all_ids.append(shooter_id)
    if len(all_ids) != len(set(all_ids)):
        raise ValueError("Shooter IDs must be unique")

    # Validate bonded references before confidence filtering so a weak sample
    # cannot hide malformed group metadata.
    for group_index, group in enumerate(groups):
        if any(not isinstance(member, str) or not member for member in group):
            raise ValueError(
                f"Bonded group {group_index} contains an invalid shooter ID"
            )

    # New detector records include a sample-quality assessment. A weak sample
    # must not be converted into a Shooter colour. Older diagnostic files
    # without this optional field retain their legacy loading behaviour.
    eligible = []
    low_confidence_ids = set()
    for index, item in enumerate(detected):
        quality = item.get("sample_quality")
        if quality is not None:
            if not isinstance(quality, dict):
                raise ValueError(f"Shooter entry {index} has invalid sample quality")
            status = quality.get("status")
            if (not isinstance(status, str)
                    or status not in ("DISTINCT_SAMPLE", "LOW_CONFIDENCE_SAMPLE")):
                raise ValueError(
                    f"Shooter entry {index} has invalid sample quality status"
                )
            if status == "LOW_CONFIDENCE_SAMPLE":
                low_confidence_ids.add(item["id"])
                continue
        eligible.append(item)
    # If a member of a confirmed bond has an unreliable visual sample, do not
    # load the remaining members as an incomplete bonded group. Preserve
    # malformed/unknown group references so the normal validator rejects them.
    groups = [
        group for group in groups
        if not any(member in low_confidence_ids for member in group)
    ]
    detected = eligible
    for index, item in enumerate(detected):
        if not isinstance(item, dict):
            raise ValueError(f"Shooter entry {index} must be an object")
        if not isinstance(item.get("id"), str) or not item["id"]:
            raise ValueError(f"Shooter entry {index} has an invalid id")
        color = item.get("color")
        if (not isinstance(color, dict)
                or not isinstance(color.get("name"), str)
                or not color["name"]):
            raise ValueError(f"Shooter entry {index} has an invalid colour")
    shooter_ids = [item["id"] for item in detected]
    if len(shooter_ids) != len(set(shooter_ids)):
        raise ValueError("Shooter IDs must be unique")
    known_ids = set(shooter_ids)
    grouped_ids = set()
    for group_index, group in enumerate(groups):
        if any(not isinstance(member, str) or not member for member in group):
            raise ValueError(f"Bonded group {group_index} contains an invalid shooter ID")
        if len(group) < 2:
            raise ValueError(
                f"Bonded group {group_index} must contain at least 2 shooters"
            )
        if len(group) > 3:
            raise ValueError(f"Bonded group {group_index} exceeds the maximum size of 3")
        if len(group) != len(set(group)):
            raise ValueError(f"Bonded group {group_index} contains duplicate shooter IDs")
        unknown = set(group) - known_ids
        if unknown:
            raise ValueError(
                f"Bonded group {group_index} references unknown shooters: "
                + ", ".join(sorted(unknown))
            )
        overlap = grouped_ids.intersection(group)
        if overlap:
            raise ValueError(
                "A shooter cannot belong to multiple bonded groups: "
                + ", ".join(sorted(overlap))
            )
        grouped_ids.update(group)

    # Optional observations must come from separately verified
    # conveyor screenshots, never from the shooter panel image.
    if geometry_observations is None:
        geometry_observations = {}
    elif not isinstance(geometry_observations, dict):
        raise ValueError("geometry_observations must be an object")

    group_lookup = {}
    bonded_lookup = {}

    for index, group in enumerate(groups, start=1):
        group_id = f"bond_{index}"
        for shooter_id in group:
            group_lookup[shooter_id] = group_id
            bonded_lookup[shooter_id] = [
                member for member in group if member != shooter_id
            ]

    shooters = {}

    for item in detected:
        shooter_id = item["id"]
        color_data = item["color"]
        center = item.get("screen_center")
        box = item.get("screen_box")

        shooter = Shooter(
            id=shooter_id,
            color=color_data["name"],
            ammo=item["ammo"],
            accessible=False,
            # Derive bonds from the validated group list, not duplicated JSON fields.
            bonded_ids=bonded_lookup.get(shooter_id, []),
            group_id=group_lookup.get(shooter_id),
            # Detection coordinates belong to the selection panel.
            panel_center=tuple(center) if center else None,
            panel_box=tuple(box) if box else None,
            # Conveyor coordinates are assigned separately.
            screen_center=None,
            screen_box=None,
            screen_center_verified=False,
        )

        observation = geometry_observations.get(shooter_id)

        if isinstance(observation, dict):
            if observation.get("verified") is True:
                required = ("center", "segment", "image_size")

                if all(key in observation for key in required):
                    result = apply_geometry(
                        shooter=shooter,
                        screen_center=observation["center"],
                        segment=observation["segment"],
                        image_size=observation["image_size"],
                        position_verified=True,
                    )
                    print(
                        f"Geometry assigned: {shooter_id} "
                        f"origin={result['origin']} "
                        f"direction={result['direction']}"
                    )

        # Never unlock a shooter through geometry assignment.
        shooter.accessible = False
        shooters[shooter_id] = shooter

    return shooters


def load_panel_slots(path=DETECTION_FILE):
    """Load validated multi-row panel inventory without inventing shooter data.

    Slot inventory is metadata only. Unrevealed or occluded slots never become
    Shooter objects or selectable candidates through this function.
    """
    data = json.loads(Path(path).read_text())
    if not isinstance(data, dict):
        raise ValueError("Shooter detection must be a JSON object")

    layout = data.get("panel_layout")
    slots = data.get("panel_slots")
    if not isinstance(layout, dict):
        raise ValueError("panel_layout must be an object")
    rows = layout.get("rows")
    columns = layout.get("columns")
    count = layout.get("slot_count")
    if any(type(value) is not int or value < 1
           for value in (rows, columns, count)):
        raise ValueError("Panel layout dimensions and slot count must be positive integers")
    if rows * columns != count:
        raise ValueError("Panel layout slot count does not match its dimensions")
    if not isinstance(slots, list) or len(slots) != count:
        raise ValueError("panel_slots must match the declared slot count")

    image_dimensions = data.get("image_dimensions")
    if image_dimensions is not None:
        if (not isinstance(image_dimensions, list) or len(image_dimensions) != 2
                or any(type(value) is not int or value < 1
                       for value in image_dimensions)):
            raise ValueError("image_dimensions must contain positive integer width and height")
        image_width, image_height = image_dimensions
    else:
        image_width = image_height = None

    seen_ids = set()
    seen_positions = set()
    allowed_statuses = {"readable", "unrevealed", "partially_occluded"}
    for index, slot in enumerate(slots):
        if not isinstance(slot, dict):
            raise ValueError(f"Panel slot {index} must be an object")
        slot_id = slot.get("id")
        row = slot.get("row")
        column = slot.get("column")
        center = slot.get("center")
        status = slot.get("status")
        selectable = slot.get("selectable_candidate")
        if not isinstance(slot_id, str) or not slot_id:
            raise ValueError(f"Panel slot {index} has an invalid id")
        if slot_id in seen_ids:
            raise ValueError(f"Duplicate panel slot id: {slot_id}")
        if type(row) is not int or not 1 <= row <= rows:
            raise ValueError(f"Panel slot {slot_id} has an invalid row")
        if type(column) is not int or not 1 <= column <= columns:
            raise ValueError(f"Panel slot {slot_id} has an invalid column")
        position = (row, column)
        if position in seen_positions:
            raise ValueError(f"Duplicate panel slot position: {position}")
        if (not isinstance(center, list) or len(center) != 2
                or any(type(value) is not int or value < 0 for value in center)):
            raise ValueError(f"Panel slot {slot_id} has an invalid center")
        if not isinstance(status, str) or status not in allowed_statuses:
            raise ValueError(f"Panel slot {slot_id} has an invalid status")
        if image_width is not None and not (
                center[0] < image_width and center[1] < image_height):
            raise ValueError(f"Panel slot {slot_id} center is outside image dimensions")
        if type(selectable) is not bool:
            raise ValueError(f"Panel slot {slot_id} has an invalid selectable flag")
        if status != "readable" and selectable:
            raise ValueError(
                f"Unrevealed or occluded panel slot {slot_id} cannot be selectable"
            )
        seen_ids.add(slot_id)
        seen_positions.add(position)

    expected_positions = {
        (row, column)
        for row in range(1, rows + 1)
        for column in range(1, columns + 1)
    }
    if seen_positions != expected_positions:
        raise ValueError("Panel inventory does not cover every declared slot position")
    return slots
