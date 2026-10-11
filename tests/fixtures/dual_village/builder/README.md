GĐ5 fixtures are selected native ADB captures from MuMu Android 15, English,
1600×900, serial 127.0.0.1:16416. Account names are masked; hero state fixtures
also mask the map. They are `transformed_test`, not new native/live receipts.

`manifest.json` records the parent path, parent SHA-256, transformation and output
SHA-256. Full originals and live input/capture traces stay in ignored diagnostics.
Additional transformations performed inside tests (absent/grayscale hero,
shifted bar, covered button, blank scene) are offline negative/contract tests.

Runtime asset crops are separately recorded in assets/dual_village/builder.

`timer-waiting` and `timer-ending` are lossless crops from the same native
two-stage battle. The army/damage were unchanged while the battle countdown
kept running; they cover the false-watchdog regression with an unused hero.

`live-receipt.json` summarizes the reviewed native probe receipts and includes
source hashes, metrics, deployment points by stage and independent setup/Stop
verification. Cancelled or failed sessions keep those outcomes; an inherited
result is not counted as a fresh complete battle.
