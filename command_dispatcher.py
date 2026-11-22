import subprocess
from datetime import datetime

ACTION = "com.slimeai.TEST"

ALLOWED_COMMANDS = {
    "PING",
    "STATUS",
    "PAUSE",
    "RESUME",
}

# Game interaction is deliberately disabled.
TAP_ENABLED = False


def send_command(command):
    command = command.strip().upper()

    if command == "TAP" and not TAP_ENABLED:
        print("BLOCKED: Game tapping is not enabled.")
        return False

    if command not in ALLOWED_COMMANDS:
        print("REJECTED: Unknown command:", command)
        return False

    result = subprocess.run(
        [
            "am",
            "broadcast",
            "-a", ACTION,
            "--es", "command", command
        ],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        print("Communication error:", result.stderr)
        return False

    print("Command sent:", command)
    return True


def system_status():
    print("\nSLIME AI SYSTEM STATUS")
    print("======================")
    print("Time:", datetime.now().isoformat(timespec="seconds"))
    print("MacroDroid bridge: available for testing")
    print("Game tapping:", "ENABLED" if TAP_ENABLED else "DISABLED")
    print("Solver: under development")


if __name__ == "__main__":
    print("SLIME AI COMMAND DISPATCHER")
    print("===========================")

    system_status()

    send_command("PING")
