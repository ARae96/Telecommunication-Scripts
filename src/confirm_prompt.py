# =============================================================================
# Shared Confirm Prompt - macOS Dialog With a Typed Fallback
# =============================================================================
# A small, shared helper that asks the person running a script to confirm an
# action before it changes anything. It is used by the Genesys Cloud scripts in
# this folder that used to rely on a DRY_RUN flag. Instead of flipping a flag,
# each script reads first, builds a short plain-language summary of what it
# would change, shows that summary here, and only makes changes if you confirm.
#
# How the confirm works:
#   - On a Mac it shows a dialog box with Cancel and Apply buttons. The dialog
#     pops up outside the terminal, so it is easy to read, and Apply is the
#     default button so pressing Return confirms.
#   - If the dialog cannot be shown (for example on Databricks or Linux, or when
#     the osascript tool is missing), it falls back to a typed prompt in the
#     terminal and only continues when you type "yes".
# Either way, anything other than a clear yes means no, so nothing is changed by
# accident.
#
# How to use it in a script:
#   from confirm_prompt import ask_to_confirm
#   message = "A plain summary of what will change..."
#   if not ask_to_confirm(message, "My Script Title"):
#       raise SystemExit("Stopped at your request. Nothing was changed.")
#
# This module knows nothing about roles, queues, flows, or users, so it can be
# reused by any script that needs a simple confirm step.
# =============================================================================

# --- Imports -----------------------------------------------------------------

import subprocess


# --- Confirm prompt ----------------------------------------------------------

def ask_to_confirm(question, dialog_title):
    """Ask the person to confirm an action and return True only if they agree.

    Tries to show a macOS dialog box first, because it is easy to read and pops
    up outside the terminal. The dialog has a Cancel button and an Apply button,
    and we return True only when Apply is clicked.

    If the dialog cannot be shown (for example on Databricks or Linux, or when
    AppleScript is missing), we fall back to a typed prompt in the terminal and
    return True only when you type "yes". Either way, anything other than a
    clear yes means no, so we never change anything by accident.
    """
    answer = ask_with_macos_dialog(question, dialog_title)
    if answer is not None:
        return answer

    # The dialog was not available, so fall back to a typed prompt.
    typed = input("\n%s\nType 'yes' to continue: " % question).strip().lower()
    return typed == 'yes'


def ask_with_macos_dialog(question, dialog_title):
    """Show a macOS confirm dialog and return True, False, or None.

    Returns True if Apply was clicked, False if Cancel was clicked, and None
    when the dialog could not be shown at all (not a Mac, or the osascript tool
    is missing). Returning None lets the caller fall back to a typed prompt.

    We run AppleScript with the "osascript" command. The script asks osascript
    to print the button name, so we can tell Apply from Cancel. We treat a
    Cancel click (osascript exits with a non-zero code) as a plain False, not an
    error, because clicking Cancel is a normal answer and not a failure.
    """
    # Build the AppleScript. buttons lists Cancel then Apply, and we mark Apply
    # as the default button so pressing Return confirms.
    applescript = (
        'display dialog %s with title %s '
        'buttons {"Cancel", "Apply"} default button "Apply"'
        % (applescript_quote(question), applescript_quote(dialog_title))
    )

    try:
        result = subprocess.run(
            ["osascript", "-e", applescript],
            capture_output=True,
            text=True,
        )
    except (OSError, FileNotFoundError):
        # osascript is not here (we are not on a Mac, or it is missing). Let the
        # caller fall back to the typed prompt.
        return None

    # osascript prints the clicked button name, like "button returned:Apply".
    # It returns a non-zero exit code when Cancel is clicked, which is a normal
    # "no" and not an error, so we check the text for the Apply button.
    return "Apply" in result.stdout


def applescript_quote(text):
    """Turn Python text into a safe AppleScript string, keeping line breaks.

    AppleScript strings use double quotes, so any double quote or backslash in
    the text has to be escaped with a backslash first. This keeps names and
    messages from breaking the script or being used to inject other commands.

    AppleScript does not read "\\n" as a new line inside a quoted string. To show
    real line breaks (so a list reads top to bottom in the dialog), we split the
    text on new lines and join the pieces back together with AppleScript's own
    "return" character, like "line one" & return & "line two". A message with no
    new lines just comes back as one quoted string.
    """
    lines = text.split('\n')
    quoted_lines = []
    for line in lines:
        escaped = line.replace('\\', '\\\\').replace('"', '\\"')
        quoted_lines.append('"%s"' % escaped)
    return ' & return & '.join(quoted_lines)
