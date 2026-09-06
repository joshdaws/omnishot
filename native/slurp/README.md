# OmniShot live selector

Vendored from https://github.com/emersion/slurp at commit
a3998d3ec79fbd85b81911f43010466b032ed0d9 (1.5.0), MIT licensed.
The original license is preserved in LICENSE; protocol licenses are embedded
in the XML files. This copy is private to OmniShot and does not replace slurp
on the system.

Modification: `%M` in the output format reports modifiers held at successful
selection completion (Shift bit 1, Ctrl bit 4). State is captured from the
selection's Wayland seat before focus returns. Geometry, pointer/touch
selection and cancellation remain upstream behavior. Absolute Wayland socket
paths are hashed when naming the session lock, so they cannot create invalid
lockfile paths. Relative display names keep the upstream lock name.
