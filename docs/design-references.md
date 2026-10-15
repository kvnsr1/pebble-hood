# Design references — reviewed 2026-10-15

The repository was empty (no repository instructions). Read the README, manifest and build files of [pebble-flight](https://github.com/kvnsr1/pebble-flight), [pebble-transit](https://github.com/kvnsr1/pebble-transit) and [pebble-calendar](https://github.com/kvnsr1/pebble-calendar). All use C/PebbleKit JS and target Time 2. Calendar's isolated SDK scripts and Core permission packaging informed this project; no other repository was changed.

Every link in the [Core Devices Developer Resources section](https://allthingspebble.saltedlolly.com/core-devices.html#core-devices-developer-resources) was opened:

| Resource | Finding / application |
| --- | --- |
| [Developer website](https://developer.repebble.com/) | Current SDK, C APIs and guides; source also reviewed in coredevices/sdk-docs. |
| [Web emulator](https://ericmigi.github.io/pebble-qemu-wasm/) and [source](https://github.com/ericmigi/pebble-qemu-wasm) | Real PebbleOS in WebAssembly, PBW upload. This project's screenshots use desktop SDK QEMU instead. |
| [Appstore API](https://appstore-api.repebble.com/) | Platform filters and version-2 Internet permission metadata reviewed. No listing created. |
| [Developer dashboard](https://appstore-api.repebble.com/dashboard) | Browser retrieval failed; no authenticated dashboard session tested. |
| [CloudPebble](https://developer.repebble.com/sdk/cloud/) | Current service is cloudpebble.repebble.com, browser IDE with C/GitHub import/build/emulators. Old service assumptions are not used. |
| [Alloy](https://developer.repebble.com/guides/alloy/) | Currently Emery/Gabbro only. C chosen to support Flint monochrome and match existing projects. |
| [Pebble examples](https://github.com/pebble-examples) | Reviewed organization and [UI patterns](https://github.com/pebble-examples/ui-patterns), [cards](https://github.com/pebble-examples/cards-example). Native menus and shallow cards applied. |
| [Community libraries](https://developer.repebble.com/community/libraries/) | Message queue and UI libraries considered; a small bounded ACK/retry queue avoids extra dependencies. |
| [Inspiration](https://developer.repebble.com/inspiration/) | Redirects to community; no standalone current inspiration collection. |
| [Moddable examples](https://github.com/Moddable-OpenSource/pebble-examples) | Reviewed Alloy UI, networking and button examples; not used because of Flint. |

## Applied guidance

Read [Design and Interaction](https://developer.repebble.com/guides/design-and-interaction/), [recommended patterns](https://developer.repebble.com/guides/design-and-interaction/recommended/), [core experience](https://developer.repebble.com/guides/design-and-interaction/core-experience/) and [implementations](https://developer.repebble.com/guides/design-and-interaction/implementation/), including their screenshots. Use large bold value, 18px body, signs plus restrained gain/loss color, Select action menu, native holdings menu and detail scrolling. Back follows the window stack. Up/Down changes the two overview cards; in lists/details it navigates/scrolls. Immediate refresh feedback; no idle animation or repeated vibration. Age and distinct errors remain visible. Secondary timestamps use 14px to fit the 144px screen; primary financial text is 18–28px.

Read [hardware specifications](https://developer.repebble.com/guides/tools-and-resources/hardware-information/) and checked SDK 4.33.1 platform directories: Flint = Pebble 2 Duo, 144×168 monochrome, 64KiB app RAM; Emery = Time 2, 200×228 color, 128KiB. Only these targets are declared. No round-device support claim.

Read [App Assets](https://developer.repebble.com/guides/app-resources/app-assets/), [images / launcher dimensions](https://developer.repebble.com/guides/app-resources/images/), [configuration](https://developer.repebble.com/guides/user-interfaces/app-configuration/) and its manual-hosting guide. Current guides provide sample assets/UI patterns rather than a separately linked downloadable design kit. Hosted configuration is necessary for private pairing/account discovery. No third-party scripts or analytics.

## Icons and licenses

Read [iconography README/gallery](https://github.com/pebble-dev/iconography), [STYLE-GUIDE](https://github.com/pebble-dev/iconography/blob/master/STYLE-GUIDE.md), its four linked angle/grid/size/shape PNGs, [pdc_tool CLI](https://github.com/HBehrens/pdc_tool), [web renderer](https://pdc-tool.heikobehrens.com/) and [Inkscape exporter](https://github.com/hellcp/inkscape-pdc-exporter). Images were inspected, not just their filenames.

Reused PebbleOS's Stocks icon under Apache-2.0; license and attribution are in `docs/licenses/` and `resources/images/NOTICE.md`. Rendered the SVG at 25×25, the actual SDK launcher limit, and inspected the PNG at native size. No new notification/timeline assets: their 25/50/80 sizes and 2/3/4px outlines are therefore not misapplied to action bars. No custom action-bar icon needed. Future custom icons must use axis/1:1/2:1/3:1 angles, aligned pixels and closed filled focal shapes.

The style guide's [2015 design talk](https://www.youtube.com/watch?v=LuiK8ZiPXr4) and [archived Storytelling in Pixels](https://web.archive.org/web/20250323041252/https://old.heydays.no/project/pebble/) were inaccessible. Linked [Apple HIG](https://developer.apple.com/design/human-interface-guidelines/) and [Material](https://m3.material.io/) returned JavaScript shells only. No claim to have watched/read those unavailable contents. The Rebble core-experience reference was reviewed through the current RePebble mirror. Direct HTTP requests to developer.repebble.com returned 403 in this environment; browser retrieval and its public source repository worked.
