# GĐ4 evidence

`manifest.json` maps every fixture to its parent, source type, dimensions, language,
hash and expected state. Native screenshots were captured independently by ADB
on `127.0.0.1:16416`, 1600×900, game English. Full PNGs stay in ignored diagnostics;
the checked-in JPEGs are explicitly transformed native exports, not original PNGs.
Runtime assets are lossless crops with their own manifest in `assets/dual_village/`.

`live-receipt.json` records a real main→builder→main transaction with one camera
operation and one boat tap in each direction, two independent no-star captures,
and opening/closing the empty cart. The builder camera was deliberately displaced
again before navigating back. Exported capture timestamps and parent hashes bind
that receipt to independently acquired images. No native reward claim, collection
of money, defense-in-progress or builder battle was performed in this verification.

`bonus-available`, `reward`, `cart-collectable`, `cart-defending`, `button-covered`
are synthetic composites; the manifest states their construction. Star/reward art
comes from the audited Vietnamese video, English text from the bundled font or
audited old assets. These fixtures verify conservative behavior and transactions;
they do not establish native English reward/defense visual accuracy. `loading` is
a resized video cloud frame, explicitly not proof of a native loading capture.
Native `battle`/`result` come from GĐ3 main Practice, not builder battles.

Only current Android image matches authorize runtime coordinates. Never tap a
video crop coordinate, manifest crop box or saved pre-camera target. Uncalibrated
language/resolution or unsupported panels must remain UNKNOWN/MODAL, with no input.
