import json
from pathlib import Path

from game_state import Shooter
from geometry_adapter import apply_geometry

DETECTION_FILE = Path("data/shooter_detection.json")


def load_shooters(path=DETECTION_FILE, geometry_observations=None):
    data = json.loads(Path(path).read_text())
    detected = data["visible_shooters"]
    groups = data.get("bonded_groups", [])

    # Optional observations must come from separately verified
    # conveyor screenshots, never from the shooter panel image.
    geometry_observations = geometry_observations or {}

    group_lookup = {}

    for index, group in enumerate(groups, start=1):
        group_id = f"bond_{index}"
        for shooter_id in group:
            group_lookup[shooter_id] = group_id

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
            bonded_ids=item.get("bonded_ids", []),
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
