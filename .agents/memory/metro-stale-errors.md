---
name: Metro stale errors after multi-step edits
description: Why Expo/Metro shows a SyntaxError + "Invalid hook call" that no longer matches the file, and how to clear it.
---

When editing a JSX file in several sequential `edit` calls (e.g. wrapping a tree in a
new parent component), one intermediate save can be momentarily unbalanced. Metro's
React Refresh tries to hot-reload that broken intermediate and logs a `SyntaxError`
plus a misleading `Invalid hook call` for the affected component. These persist in the
logs even after the final, valid edit.

**How to apply:** If tsc passes and the JSX is balanced but the logs still show a
SyntaxError / Invalid hook call, it's stale. Confirm by loading a screen that statically
imports the file (if it renders, the full bundle compiled). Restart the expo workflow to
clear Metro's cached broken state — no code change is needed.

**Why:** A statically-imported module with a real syntax error would break the entire
bundle (home screen wouldn't load at all), so a working home screen proves the current
code compiles.
