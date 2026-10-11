# GĐ4 — nhận diện, chuyển làng và hậu xử lý

Ngày 08/10/2026, giờ Việt Nam (UTC+7). Phụ thuộc camera GĐ3 và contract/coordinator GĐ2. Không có vòng train builder hoặc lịch hybrid trong giai đoạn này.

## Hợp đồng mã

- `builder_screen_reader.py`: `BuilderScreenReader`, `Capture`, `ScreenObservation`, `StarBonusObservation`, `StarBonusReader`, `BonusProgressOCR`. Phân loại hai Home, menu tấn công, battle, result, modal, loading, unknown. Reader không gửi input.
- Home cần profile/chat/settings, biểu tượng Attack riêng và chân dung thợ riêng. Main/builder không được suy từ màu bản đồ hoặc một nút chung. Modal có ưu tiên trước Home; bảng không biết chỉ chặn, không cấp tọa độ để bấm.
- `VillageNavigator.navigate(target, source=...)` trả `NavigationResult`. `switch_village(source, target)` là callback boolean cho `RunCoordinator` GĐ6; True chỉ sau xác nhận đích. GĐ4 cung cấp handler chạy riêng, chưa nối engine main vào callback có hai module hoặc mở availability builder/hybrid.
- Camera dùng `CameraController` và `SerialGestureBackend` của GĐ3. Guard Home kiểm tra lại cả trong vòng ổn định camera. Pan/zoom tối đa 6 bước tìm kiếm mặc định, tap thuyền tối đa 2; timeout monotonic 45 giây. Mỗi thao tác camera và chuyển scene bỏ tọa độ/cache cũ. Sau camera, luôn định vị lại thuyền/xe trên ảnh mới. Retry tap chỉ khi nguồn vẫn là Home ổn định; battle/result/menu/modal không cho camera/thuyền.
- `BuilderRewards.claim_star_bonus()` trả `RewardResult`, `collect_cart()` trả `CartResult`; cùng `adb.input_lock`, đồng bộ, không thread input nền. Stop chặn input tiếp, chờ có thể ngắt. Budget mặc định 35 giây, tối đa 3 bảng thưởng; cleanup xe có tối đa 5 giây riêng khi budget thao tác đã hết. Timeout ADB đang thực thi vẫn có thể làm tổng thời gian vượt deadline.

## Bằng chứng sao và đối soát

Vùng sao builder là `(20,690,175,70)` trên HUD native 1600×900, phía trên Attack; tọa độ này được hiệu chỉnh cho profile tiếng Anh ở thiết bị đã thử. AVAILABLE và COMPLETE đều cần hai capture mới, sequence tăng, cách ít nhất 150ms, cùng camera revision, map ổn định theo GĐ3 và ROI sai khác trung bình ≤5. COMPLETE cần thêm template toàn nút không sao, không dấu hiệu che, sáng bay hoặc OCR mâu thuẫn. Cùng object/capture id, None, loading, camera đổi, thiếu anchor, nút/vùng sao che đều UNKNOWN; không lưu kết quả UNKNOWN thành hoàn thành lịch.

OCR tách glyph bằng font Supercell, chỉ chấp nhận toàn chuỗi x/y rõ; thất bại trả None. OCR không xác nhận vắng sao. Có sao và `0/7`, `4/8`, `0/13` đều AVAILABLE; không cố định mẫu số. Sao main/menu/result và sao bay không phải tiến độ builder Home. `progress_ocr` có thể tiêm callback khác mà không thay hợp đồng trạng thái.

CLAIMABLE cần title thưởng, artwork sao lớn, bảng xanh, nút đúng và HUD builder. Tap một lần rồi đợi Home; bảng còn mở không replay. Đóng xong reader bắt đầu cặp ảnh mới: còn sao trả AVAILABLE. Một bảng tiếp theo chỉ được nhận sau khi đã nhìn thấy Home xác nhận bảng trước đóng; hết budget báo chưa đối soát, không COMPLETE.

Xe được tìm theo ảnh camera hiện tại, gồm mẫu empty native và biến thể cũ đã xem hình. Chỉ bảng có title `Elixir Cart` và nút đóng mới được xử lý. Nút Collect còn phải đúng màu enabled/disabled; hình chữ giống nhau không đủ. Empty/defending ổn định với nút disabled đóng ngay. Khi Collect enabled, tap một lần, cần counter/bar đổi và nút disabled qua ảnh ổn định để ghi collected. Không đổi hoặc nhận diện không rõ: đóng bảng đã biết, báo lỗi đối soát, không thu lặp. Nút đóng cũng đọc lại từ ảnh mới và xác nhận builder Home. Stop/disconnect hoặc bảng khác có thể khiến không xác nhận được Home; `returned_home=false` nêu rõ giới hạn này.

## Thiết bị thật và dữ liệu

MuMu `127.0.0.1:16416`, screenshot **1600×900**, game **tiếng Anh** đã quan sát trực tiếp. ADB còn có alias `emulator-5556`; chỉ gửi input vào serial 16416, không coi đây là hai game độc lập và không scan/connect thêm. Giữ settings/license/instances và các thay đổi GĐ1–GĐ3 có sẵn.

Vòng cuối bằng `live_roundtrip.py` (diagnostics, không mock ADB/reader/navigator/camera/rewards): main lệch, thuyền ngoài vùng an toàn → pan → tìm lại → tap → builder; đọc COMPLETE bằng hai capture; pan tìm xe → mở đúng bảng empty → đóng → Home; cố ý pan builder để thuyền bị HUD che → navigator pan tìm lại → tap → main. Hai chiều đều một camera operation và một tap, xác nhận đích độc lập. Kết thúc probe `inspect` xác nhận main Home. Không mở tìm trận, không thả quân hoặc đổi đội trong vòng nghiệm thu này. Các bước khảo sát trước đó có mở/đóng menu Attack ở hai làng nhưng không bấm Find a Match/Find Now.

Nguồn/log/native PNG nằm trong `diagnostics/dual_village_gd4/`, gitignored; receipt `live-roundtrip.json`, `live-cart-and-return.json`, `live-attempt-2.json`, `final-device-state.json`. Các lần hiệu chỉnh trước vòng cuối đã phát hiện guard camera quá chặt, modal nhầm terrain và console encoding; không gọi các lần lỗi là PASS. Camera lần khảo sát đầu đã gửi input thành công trước khi print lỗi encoding; ghi nhận ảnh `main-pan.png` sau đó.

`assets/dual_village/manifest.json` giữ crop/hashes/dimensions/language và loại nguồn cho từng anchor. `tests/fixtures/dual_village/navigation/manifest.json` phân biệt native crop, JPEG xuất từ native, video artwork và composite/generated. Không dùng tọa độ video làm tap Android. `Night_Village.png` (4320×6000) là poster; `night.png` (134×70) chỉ hai rìu; `claimreward.png` là nút reward khác. Không dùng các tên này làm bằng chứng đúng Home hoặc bảng thưởng. `collectnight.png`, `okaystar.png`, `claim_elixir_n1/n4/n8.png` đã xem nội dung/kích thước; nguồn tái dùng được ghi riêng, không tự gọi là mới nghiệm thu live.

## Phần còn thiếu

- Native English có sao `0/y`/mẫu số khác, cả chuỗi AVAILABLE→CLAIMABLE→AVAILABLE→COMPLETE và bảng thưởng lặp. Tài khoản thử đang hết sao, menu báo cooldown; không bắt đầu train builder để tạo trạng thái ngoài phạm vi. Title thưởng/defense English render bằng font và artwork từ video chỉ có test composite, **chưa nghiệm thu nhận thưởng thật**.
- Native xe có tiền, đang phòng thủ và storage đầy. Empty đã PASS thật; ca enabled/defending/tap không đổi dùng composite và input giả, **chưa nghiệm thu thu tiền thật**. Receipt hiện cần Collect disabled; trường hợp thu một phần mà nút vẫn enabled cần thêm native counter/receipt handler để xác nhận an toàn.
- Native builder battle/result/stage2, ngôn ngữ khác, resolution khác và modal chuyên biệt khác (upgrade/shop/purchase/inactivity). Mẫu battle/result native GĐ3 là main Practice; loader có video transform. Trạng thái lạ phải UNKNOWN/MODAL không có nút, không tự BACK/Okay.
- GĐ5/GĐ6/GĐ7: train, hậu xử lý theo module, lịch/runtime, engine navigation/reconnect và multi-instance thật. Main engine chưa thay đường chạy; builder/hybrid vẫn bị chặn theo GĐ1.

## Probe riêng

```powershell
python tools/dual_village_probe.py --serial 127.0.0.1:16416 --action inspect
python tools/dual_village_probe.py --serial 127.0.0.1:16416 --action navigate --target builder
python tools/dual_village_probe.py --serial 127.0.0.1:16416 --action bonus
python tools/dual_village_probe.py --serial 127.0.0.1:16416 --action claim
python tools/dual_village_probe.py --serial 127.0.0.1:16416 --action cart
python tools/dual_village_probe.py --serial 127.0.0.1:16416 --action navigate --target main
```

Các action ngoài inspect/bonus có thể gửi input khi đúng màn hình. Probe yêu cầu serial rõ; `--output diagnostics/...json` lưu receipt. Không bật bot farming từ probe.
