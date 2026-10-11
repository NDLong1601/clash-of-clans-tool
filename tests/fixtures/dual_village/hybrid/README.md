# GĐ6 hybrid evidence

`main-home-level71.png` is a **transformed test** derived from a native English
1600×900 ADB screenshot. All pixels except five HUD regions are blacked out to
remove the account name, resources and base. `manifest.json` records the source
hash, retained rectangles and output hash. This is not a native full screenshot.

It covers the current main Attack variant and a changed account level. Home
still requires a village portrait, Attack and common HUD; Attack alone, missing
portrait and modal negatives are tested. Native anchor crops and source hashes
are in `assets/dual_village/manifest.json`.

`live-receipt.json` summarizes two real passes on 127.0.0.1:16416: startup and a
scheduled check using an advanced **probe-only wall clock**, with real screen
observations, cart transactions and boat navigation. Both observed COMPLETE;
no new battle or native AVAILABLE/CLAIMABLE sequence is claimed. Full logs,
images, runtime and raw receipts stay in ignored diagnostics. The first failed
probe is preserved there and is not counted as success.
