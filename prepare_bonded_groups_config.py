"""Create a blank, unverified bonded-group config without inventing pairs."""
import argparse
import json
from pathlib import Path

OUTPUT_FILE = Path("data/bonded_groups_confirmed.json")


def prepare_config(output_path=OUTPUT_FILE):
    output_path = Path(output_path)
    if output_path.exists():
        return {
            "created": False,
            "preserved_existing": True,
            "output_path": str(output_path),
            "message": "Existing bonded-group configuration was preserved.",
        }

    template = {
        "verified_by_user": False,
        "bonded_groups": [],
        "template_only": True,
        "instructions": (
            "Add each bonded shooter group as a list of two or three exact "
            "visible shooter IDs from the current shooter_detection.json. "
            "Only set verified_by_user to true after visually confirming "
            "every group. Do not infer groups from colour similarity or "
            "fixed panel positions. A group may not share members with "
            "another group. Re-run the complete build after confirmation."
        ),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    temporary.write_text(json.dumps(template, indent=2), encoding="utf-8")
    temporary.replace(output_path)
    return {
        "created": True,
        "preserved_existing": False,
        "output_path": str(output_path),
        "verified_by_user": False,
        "bonded_groups": [],
    }


def main(output_path=OUTPUT_FILE):
    result = prepare_config(output_path)
    print("SLIME AI — BONDED-GROUP CONFIG PREPARATION")
    print("=" * 48)
    print("Created:", result["created"])
    print("Preserved existing:", result["preserved_existing"])
    print("User confirmation required: True")
    print("Bond groups inferred: False")
    print("Gameplay verified: False")
    print("Game taps enabled: False")
    print("Config:", result["output_path"])
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Create a blank unverified bonded-group config"
    )
    parser.add_argument("--output", default=str(OUTPUT_FILE))
    args = parser.parse_args()
    main(args.output)
