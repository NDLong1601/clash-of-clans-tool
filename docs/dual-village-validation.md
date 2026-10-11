# Nghiệm thu GĐ8 — CocMagic hai làng

Ngày 09/10/2026, UTC+7. Đối chiếu [kế hoạch](dual-village-plan.md), [quy tắc chung](dual-village-prompts.md), [baseline](dual-village-baseline.md) và toàn bộ [progress GĐ0–GĐ7](dual-village-progress.md).

**Cập nhật lỗi hybrid khi người dùng test:** bản mới qua **529 test/368.462s, exit 0** và lint/syntax/asset/evidence/CLI. Đã sửa bảng Star Bonus native bị nhận thành Home, chờ camera có giới hạn và thông báo navigation. Live thu xe → main có receipt thành công 72.426s. CLAIMABLE được nhận đúng trên ảnh native; chưa có receipt bot tự bấm Okay trong chuỗi live mới. Xem [báo cáo sửa hybrid](dual-village-hybrid-fix-20261011.md).

**Lượt kiểm thử trước 11/10/2026:** bản `c72db1b` qua **519 test/362.975s, exit 0**, lint/syntax/asset/evidence/CLI và checkout từ Git index đạt. Sau [sửa F1–F4](dual-village-review-fixes-20261011.md), đã sửa thêm các lỗi nhận diện/deployment tìm thấy trên game thật. Có native AVAILABLE, thu xe có tiền và khóa production chặn alias trong lúc probe chạy. Chi tiết tại [báo cáo kiểm thử](dual-village-verification-20261011.md). Các số liệu/receipt ngày 09/10 bên dưới là hồ sơ lịch sử, trừ hàng có cập nhật 11/10.

**Chưa đủ điều kiện công bố nghiệm thu toàn bộ.** Ba tab/ba mode có implementation; vẫn thiếu chuỗi AVAILABLE → nhiều trận → CLAIMABLE → còn lượt thưởng tiếp → COMPLETE → main, tướng thật vắng/nâng cấp, Copter tự động và hai game độc lập. Around đã có sửa lỗi và regression mới; log phiên cuối ghi hai khu rồi Home, nhưng thiếu receipt kết thúc nên chưa nghiệm thu around dưới tải mục tiêu. PASS offline không thay PASS live. Không tắt mode hoặc chuyển âm thầm sang main để che ca thiếu/lỗi. Camera tiếp tục mặc định false, không ghi đè lựa chọn đã lưu.

## Môi trường và cách kiểm tra

- Windows, Python 3.13.7; phiên bản chi tiết tại `diagnostics/dual_village_gd8/environment.json`. Workspace `C:\Users\PC\Documents\CocMagic`, HEAD ban đầu `3757485e4bb9e705ac8313fa86c738811430b42f`; có thay đổi GĐ1–GĐ7 và archive untracked sẵn, được giữ nguyên.
- ADB dự án `C:\Program Files\Netease\MuMuPlayer\nx_main\adb.exe`. `devices -l` hiện chỉ có **emulator-5556**, model SM_A5560/MuMu Android 15, English. Physical `wm size` 900×1600, screencap landscape **1600×900**. `127.0.0.1:16416` trong receipt cũ là cùng máy, không tính thành thiết bị thứ hai. Không tự khởi tạo giả lập/tài khoản mới.
- Live GĐ8 dùng CLI với LicenseClient/check/watchdog, BotEngine/coordinator/modules/reader/ADB thật. Harness cục bộ chỉ giới hạn thời gian, giữ tại safe Home, ghi trace/input/frame và đặt Stop; không giả screenshot, reward state, tick hay receipt thành công. Runtime và settings probe nằm riêng diagnostics. Các ảnh game đầy đủ giữ riêng, không đưa vào git.
- Fake clock/fake transport/fixture chạy qua unittest, ghi riêng với live cycle. Không đổi giờ Windows, không lấy mốc 13:00 hoặc runtime COMPLETE làm kết quả đọc sao.
- Đã đọc code thực ở config/store/GUI/CLI, engine/coordinator/runtime, camera/planner/tactics, navigator/reader/rewards, builder/module/vision, session/worker/license. Kiểm tra bytes/hash/dimensions và raw receipt của giai đoạn trước bằng `tools/check_dual_village_evidence.py`, không chỉ dựa vào progress.

## Lệnh và gate

```powershell
python -m unittest discover -s tests -q
python tools/check_assets.py
python tools/check_dual_village_evidence.py --output diagnostics/dual_village_gd8/evidence-audit.json
python -m unittest discover -s tests -p test_acceptance_main.py -q
python -m unittest discover -s tests -p test_acceptance_cli.py -q
python -m compileall -q cocmagic tools tests
git diff --check
```

Khi lưu log trên Windows dùng `PYTHONIOENCODING=utf-8` để không lỗi console. Đây là encoding IO, không sửa thuật toán test.

| Kiểm tra | Kết quả | Bằng chứng |
|---|---|---|
| Baseline GĐ0 | 213 test / 71.026s, OK; asset gate đạt | `diagnostics/dual_village_gd0/unittest.log`, baseline |
| Đầu GĐ8, đúng lệnh yêu cầu | **476 test / 319.991s, OK, exit test 0**, không skip | `diagnostics/dual_village_gd8/unittest-initial.log` |
| Wrapper đầu phiên | Test đã exit 0; wrapper in đuôi log tiếng Việt lỗi cp1252, exit wrapper 1 | Không gọi là failure unittest; bản log đầy đủ giữ nguyên |
| Main fix mới | **3 test / 0.848s OK**, hai nền native + mẫu warning-red biến đổi + builder âm | `main-surrender-tests.log` |
| CLI failure/help mới | **3 test / 0.030s OK** | `test_acceptance_cli.py`; kiểm cả 3 mode với license bật/tắt |
| Main regression liên quan | **54 test / 12.888s OK**; connection **6 test / 2.063s OK** | `farm-tests.log`, `connection-tests.log` |
| Camera regression sau sửa live | **33 test / 8.588s OK**, thêm kiểm tra HUD, receipt spell và điểm offset vào HUD | `camera-tests-final.log` |
| Spell/event liên quan | **18 test / 0.239s**, **14 test / 1.457s**, đều OK | `spell-tests-fixed.log`, `event-tests-fixed.log` |
| UI/settings sau sửa text capability cuối | **26 test / 20.095s OK**, không skip | `ui-settings-final.log`; text đổi sau full gate, không thay luồng/layout |
| Full gate trung gian | **482 test / 293.348s**, rồi **484 test / 345.248s**, OK | `unittest-final.log`, `unittest-final-camera.log`; chưa gồm hai test camera cuối |
| Full gate cuối tích hợp | **486 test / 469.922s, OK, exit 0**, không skip | `unittest-acceptance.log`; chạy đồng thời probe builder nên không dùng thời gian này làm benchmark |
| Asset gate | ALL CHECKS PASSED; đã sửa missing asset trả exit 1 | `assets.log`; giới hạn vẫn là import/10 asset main |
| Evidence gate mở rộng | **9 manifest, 160 file công bố, 163 nguồn/receipt/log riêng, 0 lỗi** | `evidence-audit.json`; nguồn riêng không bắt buộc có trên máy khác; negative probe từ chối sai bytes/dimensions/receipt thành công giả |

Không có failure baseline được phép bỏ qua. Lỗi main live dưới đây mới được phát hiện khi nghiệm thu, không có test cũ phủ đầy đủ. Không gọi test offline đạt là main live không hồi quy ở mọi nhánh. Các dòng ERROR/timeout/mua tường trong log unittest là injection có assertion, không phải thao tác game thật; kết luận theo summary OK/exit 0.

## Lỗi phát hiện và sửa trong GĐ8

1. Guard GĐ7 gọi classifier main sau mỗi ảnh. Trước khi có quân được nhận, nút **Surrender** thay End Battle khiến classifier UNKNOWN và hủy deployment; main-only có thể hết timeout recovery. Đây là lỗi tích hợp mới so với baseline trước guard GĐ7, không phải lỗi baseline được bỏ qua. Hai phiên đầu `main-legacy` / `main-fixed` thất bại và được giữ log. Lượt sửa đầu dùng timer màu trực tiếp còn phụ thuộc nền bản đồ, cũng không được tính PASS. Bản cuối nhận Surrender trong ROI + tiêu đề Battle ends in theo hình chữ threshold đỏ; loại builder bằng hai anchor Defender/Attacker. Giữ đường End Battle cũ và guard UNKNOWN. Bổ sung crop timer native, hai fixture chỉ giữ ROI HUD/nền cục bộ đã loại tên/số dư/thanh quân và test mẫu âm. Không hạ ngưỡng toàn cục hoặc giả HOME.
2. CLI help còn ghi “hybrid chờ GĐ6” dù implementation đã mở. Đã bỏ thông báo cũ; cả hai nhánh license của CLI trả **exit 1 khi engine trả False**, thay vì process thành công giả. Config/license từ chối vẫn exit 2; không thay cơ chế license.
3. `check_assets.py` trước đây in thiếu file nhưng exit 0 (baseline đã chỉ ra). Đã trả exit 1 cho thiếu asset; thêm evidence gate riêng để kiểm hash/dimensions/provenance/raw receipt. Gate này không chứng minh nhãn thị giác hoặc game live.
4. Phiên `main-camera` đã pan thật và thả Rage, nhưng nhóm kỹ năng HUD quan sát chuyển động nền và vô hiệu tactics trong lúc đối soát Freeze đã nhận; `_record_spell_use` dereference None. Nhóm chỉ bấm HUD nay không tự coi animation là đổi geometry; nhóm có điểm map vẫn kiểm revision. Receipt phép ghi mục tiêu đã gửi, an toàn khi geometry bị hủy sau input; không dùng receipt đó để cho phép input map cũ. Có test riêng cho cả nhánh event nhanh/guarded và accepted receipt sau invalidation.
5. Phiên `main-camera-fixed` sau đó bị guard chặn điểm thả vào HUD. Mask đã lọc đường đỏ, nhưng offset 35px từ đường ra ngoài có thể đi vào Next/End Battle. Planner tracked nay kiểm **điểm cuối** bằng ScreenSpace; fallback được hiệu chỉnh cũng lọc HUD. Test đường đỏ tổng hợp tái hiện điểm `(1299,542)` trước sửa. Nhánh planner khi camera tắt giữ nguyên.

## Đối chiếu yêu cầu và ma trận mục 5

Quy ước: **PASS/offline** = unit/integration với fake clock/ADB hoặc fixture; **PASS/live GĐx** = có input, ảnh và receipt native của phiên đó, đã kiểm lại nguồn ở GĐ8; **CHƯA KIỂM CHỨNG** = chưa có live phù hợp. Các receipt lỗi chỉ là bằng chứng FAIL tại thời điểm thử, không cộng vào số vòng thành công.

| Nhóm / ca bắt buộc | Code + kiểm tra offline | Kết quả live / mức nghiệm thu |
|---|---|---|
| Config: file cũ, thiếu key, key chưa biết, migration idempotent, giữ camera saved | `config.migrate_settings`, `InstanceStore`; `test_dual_village_settings.MigrationTests` PASS/offline | GĐ1 save/reopen thật UI với file tạm; hash data GĐ8 kiểm riêng |
| Ba tab, ba radio mode loại trừ nhau, Run/status/log/start/stop | `gui.InstanceTab`, `format_run_details`; settings/UI tests PASS/offline | PASS/UI GĐ7, receipt/window screenshot; dữ liệu phiên mô phỏng, không hai game |
| Validation scoped main/builder/hybrid; save giữ cả ba tab; khóa phiên, vẫn xem/cuộn/copy | `validate_settings`, GUI lifecycle/focus tests PASS/offline | PASS/UI GĐ1/GĐ7 980×840 và 880×680 |
| CLI/engine khả dụng đúng mode, không fake main, báo thất bại | `AVAILABLE_RUN_MODES`, `main`, engine construction + acceptance CLI tests PASS/offline | Live GĐ8 dùng production CLI/license; không mọi mode CLI đã đánh trọn trận |
| Hai serial settings/runtime/cache/status/camera riêng | deep-copy/session, `HybridRuntimeStore`, listeners; multi-instance/recovery/hybrid tests PASS/offline | **CHƯA KIỂM CHỨNG hai game độc lập**; hai process với transport giả không đủ |
| Một writer/input owner, không tick hai module đồng thời, pending safe boundary | `RunCoordinator`, OS lease, callback trước Attack; coordinator/recovery tests PASS/offline | Navigation/hybrid một serial có receipt; duplicate/alias CLI không phải hai thiết bị được thử |
| Sao 0/y, x/y, mẫu số đổi, OCR chỉ bổ trợ | `BuilderScreenReader`, StarBonusObservation; screen-reader tests PASS/offline với video/composite và native crop | Cập nhật 11/10: native `0/8` AVAILABLE được xác nhận trên English 1600×900; vẫn thiếu chuỗi CLAIMABLE/lượt tiếp/COMPLETE |
| COMPLETE hai ảnh mới, rõ Home/nút/vùng sao, không dùng cache lặp | screen reader tests độc lập capture/sequence/time PASS/offline | PASS/live GĐ4–GĐ7 và GĐ8 `hybrid-complete` captures 32/33 |
| None/loading/animation/che nút/che vùng sao/main/result/modal âm | screen-reader tests, capture guard PASS/offline | Một số nền/modal native được audit; **chưa đủ live từng loại che/animation** |
| CLAIMABLE, claim xong còn sao, nhiều bảng cần Home proof | `BuilderRewards.claim_star_bonus`; navigation/reward tests PASS/offline | **CHƯA KIỂM CHỨNG native claim/claim còn lượt tiếp**; video Việt không thay automation native |
| Claim xong hết sao, nhiều trận mới đủ thưởng, hoàn tất cả chuỗi | rewards + `HybridCoordinator._observe_bonus/_builder_home`; hybrid tests PASS/offline | **CHƯA KIỂM CHỨNG chuỗi live**; không quay main sau chỉ một trận |
| Xe có tiền, trống, đang phòng thủ, Collect khóa còn tiền | `collect_cart`, receipts/tests PASS/offline | PASS/live GĐ5 thu/disabled/defending, raw source khớp; native GĐ8 ghi riêng |
| Xe failed close/no change/partial collect còn enabled | navigation/reward tests PASS/offline cho failure; không replay | Failed-close có injection; **thu một phần còn enabled chưa kiểm chứng live** |
| Startup mỗi làng, thuyền ngoài màn/zoom khác, xác nhận đích | `VillageNavigator.confirmed_home/locate/navigate`; navigation tests PASS/offline | PASS/live GĐ4–GĐ7 main→builder→main với pan/offset; GĐ8 `main-restore` main-only từ builder về main đã xác nhận |
| Pan/pinch, zoom limit suppress, release, đúng serial | camera backend/controller tests PASS/offline | PASS/live Home/Practice GĐ3; Stop pan/pinch GĐ7; backend khác chưa hỗ trợ |
| Cạnh dưới che HUD; bỏ geometry cũ, không dịch HUD, probe trước batch | planner/tactics/farm revision guards; camera tests PASS/offline | PASS/live Practice GĐ3 (10→9→7 tại cạnh dưới); không suy toàn cạnh đáy hoặc mọi multiplayer |
| Drag khi đã chọn quân | selection guard/tests PASS/offline, runtime từ chối selected/unknown | GĐ3 một Practice 5→5, damage 0%; **chưa mọi quân/scene**, không mở từ mẫu đơn |
| Camera bật/tắt main sau lọc loot, không zoom đối thủ bị skip | `FarmModule._prepare_battle_camera`, acceptance main + 33 camera tests PASS/offline | GĐ8 main camera tắt PASS vòng mới; camera bật ghi riêng dưới, các phiên lỗi không tính PASS |
| Rồng con/Starting + Reinforcements, số ô khác/khóa/quân sai | builder vision/setup + 65 builder tests PASS/offline | PASS/live GĐ5 6 chính+1 tiếp viện, sửa Bomber; GĐ8 single_point có 5 ô quân nhìn thấy và dùng đủ. **Camp 8 chưa live**, không suy cấp tài khoản từ số ô quan sát |
| Tướng Machine ready/charge/skill | builder portrait/health/ability receipt ledger tests PASS/offline | PASS/live GĐ5 Machine triển khai/4 skill around |
| Tướng thật không có/nâng cấp/UNKNOWN, không làm lệch camp | absent/gray/shifted/unknown tests PASS/offline | **CHƯA KIỂM CHỨNG tướng thật vắng/nâng cấp**; tắt hero single_point không tương đương |
| Copter skill tự động | reader/charge/cooldown tests PASS/offline | Native portrait có; **chưa receipt kỹ năng Copter tự động** |
| Around khác single_point, điểm đầu bị từ chối cần receipt | `BuilderTactics`; distribution/rejection/revision tests PASS/offline | PASS/live GĐ5 around-14 + single-8-timer; single-6 reject phục hồi nhưng phiên đó cart lỗi. GĐ8 around dưới tải cao không triển khai đủ quân, ghi FAIL cho yêu cầu đó của phiên |
| Một khu result, 100% chuyển khu chưa result | native classification + module stage tests PASS/offline | PASS/live GĐ5 around khu một và single_point hai khu |
| Khu hai scan survivors/reinforcement/hero/skill, giữ used ledger, bỏ map | builder `_new_stage`, vision/tactics tests PASS/offline | PASS/live GĐ5 10 deploy/7 skill, điểm mới khu hai; không gọi mọi tướng đạt |
| Builder COMPLETE vẫn train tiếp, reward/cart rồi HOME; Stop/reload không reuse | builder tests PASS/offline | PASS/live GĐ5 around lặp 2 Find mới dù COMPLETE; Stop-select/setup có receipt |
| Hybrid startup còn sao/hết sao; sau cart lại AVAILABLE | real builder module + fake coordinator tests PASS/offline | COMPLETE live GĐ6/GĐ7; **AVAILABLE/post-cart thêm thưởng chưa live** |
| Hybrid thu xe trước main, main resume không lặp Quick Train | `_cart_before_main`, coordinator/main contract tests PASS/offline | PASS/live GĐ6 và GĐ8 COMPLETE+cart+main; không trận main mới trong phiên hybrid GĐ8 |
| 09:00/15:29/15:31, startup qua mốc, >=15:30, ZoneInfo fallback UTC+7 | fake clock `test_hybrid_scheduler` PASS/offline | GĐ6 daily pass dùng clock probe; **không gọi là chờ giờ thật** |
| Pending giữa trận/modal/wall/tick dài, hoàn tất rồi nhường | callback trước Attack/safe HOME; coordinator/hybrid tests PASS/offline | GĐ6 pending tại COLLECT live; giữa trận đang đánh mới **chưa live** |
| Ngủ nhiều ngày/restart/qua ngày/COMPLETE persisted vẫn startup | fake wall/monotonic/runtime tests PASS/offline | **Chưa ngủ máy thật qua giờ/restart giữa hybrid battle** |
| UNKNOWN/retry/no progress/budget; fallback có lý do, chưa hoàn thành | hybrid/runtime/recovery injection PASS/offline | GĐ6 thất bại startup giữ UNKNOWN, không fake COMPLETE; chưa full chuỗi lỗi live |
| Reconnect main/builder/khu2/reward/cart/thuyền, classify lại | engine frame guard/unwind/generation; recovery tests PASS/offline | Native inactivity GĐ5/GĐ7; **mất mạng thật từng màn và reconnect một bên trong hai game chưa live** |
| Stop gesture/batch/chờ/reward/skill; input mới bị chặn/cleanup có hạn | ADB/remote UUID job/stop Event + recovery tests PASS/offline | PASS/live GĐ7 Stop pan/pinch, GĐ5 Stop-select/setup; modal/batch/skill còn injection |
| Chạy tất cả/Dừng tất cả; scan lỗi/mất serial; license/watchdog | GUI/session/worker/license tests PASS/offline | PASS/UI mô phỏng GĐ1/GĐ7; live GĐ8 license startup thật; **expiry live và hai game chưa thử** |
| Main train đầu, lọc OR gold/elixir + dark, wall/event, troop/siege/hero/spell | main/farm/event/wall/loot/spell/burst tests PASS/offline | GĐ8 train + troop/xe/2 hero/6 spell/result/Home có thật; GĐ1 `live-stopped.json` log xác nhận loot 161529/265129/2682 và Next skip #1 với ngưỡng 1 nghìn tỷ, Stop ok/exit 0; **wall/event mới live chưa thử** |

## Phiên live GĐ8 và dữ liệu cá nhân

Nguồn đầy đủ ở `diagnostics/dual_village_gd8/`; file log tương ứng nằm ngay thư mục này. Các cấu hình probe lưu riêng; không ghi settings/instances/license người dùng. Hash toàn bộ data ngoài runtime trước phiên ở `data-before.json`; kết quả so sánh cuối ở `handoff.json`. Không lưu key/tài khoản trong mẫu công bố.

| Phiên | Thiết lập thử và kết quả |
|---|---|
| `main-legacy` | File JSON cũ bỏ toàn bộ key dual-village, auto_train=true; tắt wall/event; ngưỡng loot=0 để đánh trận, giữ các trường main còn lại. **FAIL**, 211.313s: TRAIN thành công nhưng Surrender UNKNOWN, hết recovery, CLI exit 1. |
| `main-fixed` | Sửa timer màu ban đầu. **FAIL**, nền map khác làm match timer .806 dưới .90, hủy deployment. Giữ lỗi để truy nguyên, không tính là vòng đạt. |
| `main-fixed-2` | Bản cuối threshold chữ timer; **PASS/live**, goal=true/error=null, 145.873s, safe Home. Tổng counter 2 gồm 1 result khôi phục từ lần trước + **1 trận mới**. Quick Train đúng một lần; 2 ô quân, siege, Warden/Prince có receipt, Rage 5 + Freeze 1, hero abilities, timeout 60s → Okay → result → Home. Không gọi counter 2 là hai trận mới. Inspector độc lập xác nhận main_home. |
| `main-camera` | **FAIL**, pan thật rev1/2, troop/siege/hero/Rage có receipt nhưng lỗi NoneType khi đối soát Freeze. Không tính PASS dù game đã nhận phép. |
| `main-camera-fixed` | **FAIL**, đã sửa HUD/receipt nhưng planner còn chọn điểm offset vào HUD; guard chặn input và trả lỗi rõ. Không fallback mode. |
| `main-camera-final` | **PASS/live**, goal=true/error=null, 187.601s. Counter 2 = 1 result kế thừa + **1 trận mới**. Bỏ qua 4 đối thủ vì frame chưa ổn định; sau đó hai pan rev1/2 được xác nhận, 8 điểm mới; 2 ô quân, siege, Warden/Prince + skills, 5 Rage + 1 Freeze, timeout/Okay/result/Home. Ảnh `state-011.png` xác nhận quân/phép x0, hero deployed và damage 32%; không gọi mọi cảnh/zoom đều đạt. |
| `hybrid-complete` | **PASS/live cho startup hết sao → kiểm xe → main**, goal=true/error=null, 151.665s. Main→builder, COMPLETE từ captures 32/33 mới, cart success/unavailable/collected=false/returned_home=true, xác nhận main. Không claim hoặc đánh builder; không tính xe đã thu tiền. Thời điểm 10:01:54+07, daily chưa dùng, next check 15:30 ngày hiện tại; không gọi đây là scheduled live 15:30. |
| `builder-around` | Goal=true/error=null, 1 Find mới từ COMPLETE, 1 result khu một, hậu xử lý và Home. **PASS/live cho tiếp tục khi hết sao + một khu + Machine có kỹ năng; FAIL/live cho triển khai đủ đội hình trong phiên này**: metrics 4 deployment, 1 troop skill, 1 hero skill; còn quân khi hết giờ. Full unittest đang chạy đồng thời gây tải cao; không suy nguyên nhân chắc chắn hoặc gọi toàn builder đạt từ goal harness. |
| `builder-single` | **PASS/live giới hạn một khu, single_point, hero setting off**, goal=true/error=null, 278.538s; 1 Find mới, 5 ô Rồng con triển khai + 5 kỹ năng, 5 map tap đều `(1277,536)`, 1 result rồi Home. Cart collection trước trận metrics=1, sau trận xe đã trống/unavailable/defending. Không có tướng input; không gọi đây là tướng thật vắng/nâng cấp. Phiên chạy riêng sau full gate; không có khu hai trong trận này. |
| `builder-around-solo` | **CHƯA KIỂM CHỨNG vòng hoàn tất**: log có Find mới, 5 deployment, 3 troop skill, 1 Machine skill và đang transition khi phiên công cụ bị ngắt (không còn process, không receipt finally). Ảnh ADB kiểm lại sau tiếp tục có battle 100%, chưa dùng để suy toàn vòng hoặc hai khu đạt. Không công bố goal=true hoặc PASS từ log giữa trận. |
| `builder-resume` | **PASS/live hậu xử lý result kế thừa sau ngắt process**: 0 Find mới, 0 deployment, 1 result kế thừa → reward COMPLETE/thu xe → Home. Không tính là trận mới hoặc receipt phục hồi khu hai. |
| `main-restore` | **PASS/live main-only startup từ builder → main Home**, goal=true/error=null, 28.884s, attack/skip/wall=0, initial_trained=false. Camera/auto_train/wall/event=false trong probe, không mở trận mới. Ảnh ADB độc lập cuối phiên `final-main-home.png/json` xác nhận main_home English 1600×900. |

Các phiên main/builder dùng tìm đối thủ, Quick Train, đánh trận và thu xe thật nên thay đổi trạng thái game/tài nguyên như thao tác thông thường được yêu cầu kiểm chứng. Không đổi đội hình Saved Recipes, không nâng tường/mua vật phẩm, không đổi key hoặc tài khoản. Config probe đã ghi ở bảng từng phiên; camera bật/tắt và hero off chỉ ở file probe. Kiểm cuối **4 file data trước phiên, 0 thay đổi** (`data-final-check.json`), gồm settings/instances/license config/key; không cần ghi lại cấu hình để khôi phục. Đã đưa game về main Home và đóng mọi probe; kiểm cuối tại `handoff.json`.

## Bàn giao và phần còn lại

| File GĐ8 | Thay đổi |
|---|---|
| [main.py](../cocmagic/main.py) | Help ba mode hiện tại, exit 1 khi engine thất bại |
| [gui.py](../cocmagic/gui.py) | Bỏ câu hybrid chờ GĐ6 ở nhánh capability không khả dụng; giữ khóa/start theo implementation |
| [farm_module.py](../cocmagic/modules/farm_module.py) | Guard Surrender/timer; phân biệt HUD/map; receipt spell chịu được invalidation |
| [battle_planner.py](../cocmagic/battle_planner.py) | Lọc điểm cuối sau offset bằng map mask trong nhánh tracked |
| [acceptance main](../tests/test_acceptance_main.py), [acceptance CLI](../tests/test_acceptance_cli.py), [camera tests](../tests/test_camera_controller.py) | Thêm 10 test so với đầu GĐ8, gồm nhánh âm và giữ guard map |
| [check_assets.py](../tools/check_assets.py), [evidence gate](../tools/check_dual_village_evidence.py) | Missing asset exit 1; kiểm hash/dimensions/raw receipt/log, không giả live proof |
| [asset manifest](../assets/dual_village/manifest.json), [acceptance fixtures](../tests/fixtures/dual_village/acceptance/README.md) | Crop timer, hai PNG đã che dữ liệu, provenance và receipt công bố chọn lọc |
| [README](../README.md), [progress](dual-village-progress.md), validation này, [camera](dual-village-camera.md), [builder](dual-village-builder.md), [settings example](dual-village-settings.example.json) | Hướng dẫn, capability/giới hạn và kết quả đúng mức bằng chứng |

- Sửa GĐ8: `cocmagic/main.py`, `cocmagic/gui.py`, `cocmagic/modules/farm_module.py`, `cocmagic/battle_planner.py`, `tools/check_assets.py`; thêm `tools/check_dual_village_evidence.py`, hai test acceptance và mở rộng camera tests, crop/manifest/fixture HUD chọn lọc. README, progress, tài liệu camera/builder và mẫu config cập nhật đúng implementation. Sửa text UI dùng skill ui-ux-pro-max, không thay layout.
- Bằng chứng cũ công bố: `tests/fixtures/dual_village/{camera,navigation,builder,hybrid,recovery}/`; evidence mới ở `acceptance/`. Hash nguồn giữ provenance; ảnh biến đổi luôn được ghi là transformed_test.
- Còn chặn nghiệm thu đầy đủ: thưởng native AVAILABLE/CLAIMABLE/lượt tiếp/nhiều trận tới COMPLETE; tướng thật thiếu/nâng cấp/Copter skill; hai thiết bị độc lập khác mode + reconnect một bên + all-run/all-stop; main wall/event live và các nhánh camera/recovery chưa phủ nêu ở bảng. Cần tình trạng game/thiết bị phù hợp, không thể thay bằng fixture và gọi PASS thật.
- Around dưới tải cao còn FAIL triển khai đủ trước hết giờ. Lượt riêng chưa có receipt hoàn tất do gián đoạn; phiên resume chỉ hậu xử lý result kế thừa. Cần đo và kiểm lại deployment dưới tải mục tiêu, không bỏ guard ảnh/receipt để tăng tốc hoặc xóa phiên lỗi khỏi bằng chứng.
- Kiểm bàn giao: compileall và diff whitespace đạt; 61 link local hợp lệ; không có mã harness/serial thử hardcode mới trong production, không có diagnostics/data/runtime mới ở git status. Toàn bộ 12 phiên công bố chọn lọc tại [live receipt](../tests/fixtures/dual_village/acceptance/live-receipt.json), gồm phiên lỗi/gián đoạn; 9 manifest/160 file/163 nguồn riêng đối chiếu đạt.
- Để chẩn đoán: dừng phiên, chọn `run_mode=main`, `camera_auto_adjust=false`; giữ file cấu hình cũ để quay lại. Xem [README](../README.md), [mẫu settings](dual-village-settings.example.json). Đây không phải cách biến nhánh lỗi thành nghiệm thu thành công.
- Không commit/push/deploy; không thêm runtime, video hoặc log/ảnh riêng tư vào git. Archive `CocMagic_Release.zip` có sẵn không phải đầu ra GĐ8.
