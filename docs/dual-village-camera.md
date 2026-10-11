# Camera GĐ3 — backend, hợp đồng và bằng chứng

Ngày kiểm chứng GĐ3: 08/10/2026, UTC+7. Giữ `camera_auto_adjust=false` mặc định. Trạng thái builder/hybrid dưới đây là lịch sử GĐ3; hiện ba mode đã mở. GĐ8 bổ sung một vòng main multiplayer camera bật với pan/quân/xe/tướng/phép/result/Home sau sửa lỗi; vẫn chưa đủ mọi cảnh, pinch multiplayer và hai serial thật đồng thời. Xem [nghiệm thu GĐ8](dual-village-validation.md) để biết kết quả và giới hạn hiện tại.

## Backend được hỗ trợ

| Thao tác | Backend | Phạm vi thực tế |
|---|---|---|
| Pan | `adb -s SERIAL shell input swipe` | Một điểm, boolean kết quả command + release; CameraController xác nhận chuyển động map bằng ảnh mới. Đã thử Home và Practice. |
| Pinch | `sendevent`, protocol B, hai slot 0/1 chung `SYN_REPORT` | Đã thử MuMu Android 15, `Xiaomi Touchscreen`, raw axes 900×1600, viewport rotation=1, screenshot 1600×900. Khảo sát device path mỗi lần; không hardcode event4 cho các thiết bị khác. |
| Backend khác/resolution/rotation khác | `UNSUPPORTED` | Chưa chứng minh Android khác, raw permissions khác, portrait, nhiều màn hình hoặc DPI khác. Không scale HUD/planner theo kích thước ảnh. |
| Ctrl+wheel | Không triển khai | MuMu có shortcut này nhưng chưa có mapping cửa sổ/serial và khóa focus toàn máy đã nghiệm thu. Runtime hiện dùng input theo serial, không chiếm focus desktop. |

ADB không tạo pinch bằng hai swipe riêng. Protocol B dùng slot/tracking ID và release `TRACKING_ID=-1`; tham chiếu [Linux multi-touch protocol](https://kernel.org/doc/html/latest/input/multi-touch-protocol.html). ADB swipe là một chuỗi DOWN/MOVE/UP một điểm: [Android InputShellCommand](https://android.googlesource.com/platform/frameworks/base/+/80c54abf5a10/services/core/java/com/android/server/input/InputShellCommand.java). Shortcut desktop mới chỉ là thông tin khảo sát từ [MuMu shortcuts](https://www.mumuplayer.com/help/win/emulator-function-shortcuts.html), không phải backend đã bật.

MuMuManager `info -v all` xác định instance 1, `Android Device-1`, Android 15.0 đang chạy, `adb_host_ip=127.0.0.1`, `adb_port=16416`. ADB ban đầu chưa đăng ký serial; đã connect đúng endpoint manager cung cấp, không scan port khác hoặc khởi động emulator. `wm size`: physical 900×1600; screencap landscape 1600×900; model SM-A5560. `getevent -lp` và `dumpsys input` xác nhận protocol B/viewport; shell thuộc group input và `sendevent SYN_REPORT` thành công. Không root/chmod/cài helper hoặc thư viện mới.

## Hợp đồng camera và tọa độ

- `CameraStatus`: SUCCESS khi có biến đổi map đúng loại/hướng và ảnh sau ổn định; UNCHANGED khi biến đổi gần identity; ERROR khi input/release/ảnh/đối soát lỗi; UNSUPPORTED khi backend/viewport/context/selection không an toàn; STOPPED khi Stop. Command exit 0 tự nó không đủ để SUCCESS.
- ORB/RANSAC đo similarity của đặc trưng **map**, yêu cầu ít nhất 18 inlier, tỷ lệ >=55%, độ phủ >=140 px hai trục và góc quay nhỏ. Kết quả là bằng chứng; không dùng ma trận để dịch mục tiêu cũ. HUD được loại khỏi matcher và candidate mask.
- Ảnh ổn định: hai cặp ảnh mới liên tiếp gần identity, mặc định tối đa 8 capture trong ngân sách 3 giây; screenshot timeout của ADB vẫn áp dụng riêng, nên một call đang capture có thể kết thúc sau deadline. Blank/không đủ feature/đổi resolution/modal đã biết không được xem là ổn định.
- Pan kiểm tra toàn đường drag không chạm HUD; zoom dùng tâm map (800,410), hệ số .55–1.65. Khi đã xác nhận giới hạn cùng hướng, gọi tiếp trả UNCHANGED với `attempts=0`, không gửi input. Đổi scene/reload/reset_view xóa giới hạn.
- `normalize()` thử zoom-out tối đa 3 lần mặc định (cap 4), ngân sách bắt đầu 20 giây; đạt limit trả UNCHANGED. Đây là khung nhìn rộng đã đo, **không phải chứng nhận hình thoi cố định/đã căn giữa**. Nếu hết lượt vẫn đang thay đổi, trả ERROR và ảnh cuối để caller quyết định bằng hình học mới.
- Mỗi gesture đã gửi, kể cả lỗi/limit, tăng `ADBController.camera_revision` trước input và invalidates cache. Đây là epoch bảo thủ: UNCHANGED vẫn loại tọa độ cũ vì input vừa được đối soát. Unsupported/Stop trước input không tăng revision. Screenshot/frame-match cache bị xóa trước và sau gesture; match-position hints cũng xóa khi camera attempt.
- Callback FarmModule bỏ plan/tactics, điểm confirmed/electro/verified, hero entry, hotspots/rage entries/spell targets nằm trong tactics, reference viewport và ảnh vision. Combo/card coordinates, UI button coordinates và deployed hero portrait slots giữ nguyên; không dịch HUD theo map. Giữ consumption/cast index và hero ability state. Camera đổi giữa cast chưa đối soát làm halt; không replay spell theo ảnh mốc cũ.
- BattlePlan/AttackTactics mang revision. Mọi map input kiểm tra revision và HUD ngay trước gửi; targets từ epoch cũ bị chặn ngay cả khi camera_auto_adjust tắt. HUD selection/ability/speed button dùng không gian riêng.
- Trong camera mode, FarmModule đối chiếu ảnh mới với reference lập plan trước input để bắt cả pan/zoom bên ngoài controller. Biến đổi map hoặc mất khả năng đối chiếu tăng epoch và chặn batch cũ; trước deployment có thể rebuild, đang deployment thì dừng để đối soát. Nhánh camera tắt/revision=0 giữ đường đọc ảnh và chiến thuật cũ.

## Release, Stop và sở hữu input

Camera chạy đồng bộ trong tick dưới coordinator GĐ2; dùng thêm `ADBController.input_lock` cho camera, không tạo thread input nền. Mỗi worker sở hữu một serial. Không có desktop focus lock hoặc phím Ctrl đang giữ vì không dùng fallback cửa sổ.

Pinch là một shell script: hai contact có tracking ID riêng, cập nhật cả hai rồi SYN_REPORT mỗi bước. Script có trap exit/signal release hai slot; host `finally` kill job theo pidfile UUID nếu còn tồn tại và thử release tất cả slot, kiểm tra exit code cleanup. PID file nằm tạm trong `/data/local/tmp`, được xóa. ADB swipe có `finally` gửi CANCEL, kể cả khi stop/error; cleanup bypass stop guard. Camera tiếp tục invalidate ảnh trong finally, cả khi cleanup báo lỗi.

Stop được kiểm tra trước probe, sau probe, trước submission và sau command. Gesture đang gửi không bị cắt tức thì: script có tối đa 10 bước/700 ms sleep budget, subprocess timeout 5s, raw cleanup timeout 3s và CANCEL timeout 3s. Timeout/disconnect có thể khiến release không xác nhận được; ERROR/STOPPED và cache invalidation không được trình bày như release chắc chắn thành công. Runtime không gửi gesture tiếp sau Stop.

## Tích hợp planner/farm

Luồng camera bật: loot đạt ngưỡng → xác nhận scout/quân chưa chọn → tìm hình học → tối đa 3 zoom-out khi chưa có geometry → tối đa 2 pan lên nếu cạnh dưới bị che → ảnh mới và plan mới → chọn quân → thử một điểm → xác nhận số quân giảm → batch. Ngân sách chuẩn bị 22s, kiểm tra trước từng operation; operation đã bắt đầu vẫn chịu các timeout riêng. Không chỉnh camera cho từng đối thủ bị skip; không chỉnh giữa các nhóm quân hoặc sau selection. Nếu scout hết thời gian, modal xuất hiện hoặc mất ảnh thì fail closed/recovery, không suy HOME hay bấm Next trên màn không xác định.

Tracked planner đọc đường biên từ **ảnh hiện tại**, kể cả biên native H=13..18. Hull bị crop không được biến thành cạnh thả giả: mỗi cạnh sinh candidate phải có >=35% hỗ trợ đỏ. Sau pan-limit có thể dùng các **đoạn cạnh dưới còn nhìn thấy** và lọc HUD; không bắt buộc thấy toàn bộ đỉnh đáy. Các điểm này vẫn phải được game nhận qua số quân giảm trước batch. Không thể đưa toàn bộ đỉnh đáy ra ngoài HUD ở một số camera limits đã thấy; không tiếp tục drag vô hạn để đạt điều không thể.

Fallback hình thoi cũ chỉ giữ trong nhánh tương thích **camera tắt, revision=0**, như yêu cầu bảo toàn main. Camera bật, hoặc đã có gesture/revision mới, không tự dùng fallback đó. Một reference cho fallback tracked phải cùng revision, match ảnh hiện tại gần identity và tự được xác nhận lại bằng geometry quan sát khớp footprint; bộ dữ liệu hiện tại chưa cung cấp calibration này. Geometry không xác định → bỏ đối thủ/rút lui an toàn. Không phóng hình thoi theo resolution hoặc chỉ nhân tọa độ cũ với zoom factor.

## Bằng chứng thực tế

Ảnh/log gốc ở `diagnostics/dual_village_gd3/` (gitignored); chúng là native ADB, không phải crop video. Toàn bộ input có serial `127.0.0.1:16416`.

| Ca | Kết quả/ảnh |
|---|---|
| Home pan | `home-gestures.json`, `home-pan-up-before/after.png`: scale 1.00005, dy -57.64, 1011 inlier. Một lần pan đầu khác cũng gửi trước khi harness vướng console encoding; không coi đó là lần không có input. |
| Home pinch | `home-zoom-out-before/after.png`: scale .86303, 525 inlier. Raw rotation conversion đã đo bằng kết quả ảnh. |
| Zoom limit | `home-limit.json`, `home-limit-0-before/after.png`: identity; lần lặp `attempts=0`, không gửi thêm. |
| Practice pinch | Flying Circus `battle-zoom-out-before/after.png`: scale .66741, 407 inlier; số quân không giảm. Frame `battle-unselected.png` còn mây/selection cũ, không dùng làm proof unselected; controller đợi ảnh ổn định và kiểm tra selection lại. |
| Practice pan/cạnh dưới | `battle-pan-up-before/after.png`: dy -165.90, 1001 inlier; HUD tại chỗ, lower candidates quét lại. Pan tiếp và zoom tiếp tại limit trả UNCHANGED (`bottom-reveal-*`, `bottom-wide-*`). |
| Drop tại cạnh dưới | `bottom-deployment.json`, `bottom-probe-before/after.png`, `bottom-bulk-after.png`: target (952,644), 10→9 rồi batch 2 quân, 9→7. Point được planner từ ảnh mới khi thử; hull/Hough có thể sinh candidate khác ở ảnh tiếp do animation. Result ghi đúng x3 quân đã dùng (`practice-result.png`), 5% damage, đã Return Home (`device-return-home.png`). Đây là thử Practice, không phải vòng bot multiplayer tự động. |
| Drag đã chọn quân | Bowling with Witches `selected-before/after-drag.png`: quân đầu 5→5, damage 0%, map dy -211.02. Một tình huống, không suy mọi card/scene an toàn. Runtime vẫn chặn selection=true/unknown và kiểm tra khung trắng native. |
| Stop/release cuối | `stop-live.json`: STOPPED, raw/cooked pointerCount=0, tổng 7.24s gồm probe/capture/cleanup. **Ảnh trước đã có Connection lost/thiết bị khác**: chỉ chứng minh submission/cleanup raw backend, không chứng minh camera game chuyển động khi Stop. Đã bổ sung guard modal và test; không reload để tranh quyền phiên với thiết bị kia. |

Video camera nguồn đã hash lại, giải mã tuần tự 635 frame tới EOF, xem lại 4/13/20s cùng sheet các mốc: map đổi zoom/pan và HUD đứng yên; không có trace chứng minh input video. `video-review.json`, `video-camera-review-*.png`. Không lấy tọa độ viền video 1064×640 để bấm Android 1600×900.

Fixture gọn trong `tests/fixtures/dual_village/camera/manifest.json`: 4 frame map (hai cặp trước/sau) JPEG chất lượng 94 che resource HUD; 5 bar PNG crop lossless; crop modal native. Có parent hash, transform, dimensions, serial/backend. Tất cả mang nhãn `transformed_test`, không giả làm native nguyên bản. Synthetic test chỉ đổi HUD bằng noise seed 42; không gọi đó là gesture game.

Nghiệm thu mã cuối: **298 test, 94.049s, OK** (29 camera mới + baseline 269), log `diagnostics/dual_village_gd3/regression-tests-final-verified.log`; asset checks, compileall và whitespace check đạt. Đây là regression offline, không thay các nhánh live còn mở dưới đây.

## Phần chưa nghiệm thu

- Main multiplayer qua full engine/coordinator: lọc loot → camera → toàn bộ combo/spell/hero → result, nhiều đối thủ liên tiếp, reconnect trong gesture. Hiện mới kiểm chứng CameraController/planner/input thật trong Practice và regression offline.
- Hai serial thật đồng thời, máy không có quyền raw input, rotation/resolution khác và các kiểu HUD/card khác. Không bật camera mặc định hay builder/hybrid dựa trên một thiết bị.
- Drag mọi loại quân/spell/hero đang chọn; runtime chặn thay vì suy từ một mẫu Practice.
- Chứng minh Stop giữa camera đang chuyển động trong game không modal; native release đã quan sát nhưng mẫu Stop cuối bị thiết bị khác kết nối. Giữ popup hiện tại, không có bot/QA worker tiếp tục input.
- Home boat navigation, builder camera/planner/geometry stage2 là đầu vào GĐ4/GĐ5, chưa có logic điều hướng/train builder.
