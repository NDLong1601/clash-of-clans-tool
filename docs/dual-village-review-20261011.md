# Review GĐ0–GĐ8 — 11/10/2026

**Cập nhật sau review:** F1–F4 đã được sửa theo yêu cầu người dùng. Xem [báo cáo sửa lỗi và test hồi quy](dual-village-review-fixes-20261011.md). Nội dung bên dưới giữ bằng chứng của bản trước sửa; script diagnostic trước sửa không thay thế các regression test mới.

## Kết luận

**Chưa đủ điều kiện chốt nghiệm thu toàn bộ GĐ0–GĐ8.** Bộ test hiện tại qua đủ 486 test, nhưng review bổ sung tái hiện được 4 lỗi chưa được bộ test này phát hiện: nhánh lập kế hoạch main thay đổi sau chuyển làng, khóa input không hợp nhất alias của cùng một máy, ưu tiên kỹ năng tướng có thể bỏ đói việc thả quân, và lịch sử điểm builder còn sót sau đổi camera.

Phạm vi: working tree hiện tại, bao gồm cả file mới chưa được Git track, đối chiếu với `dual-village-plan.md`, `dual-village-prompts.md`, baseline/progress/validation và nguồn fixture. Đây là review source, kiểm thử offline và kiểm nguồn bằng chứng; không chạy thêm trận hoặc gửi input vào game. Không sửa implementation, cấu hình cá nhân hoặc runtime của bot.

P1 = nên sửa trước khi nghiệm thu chạy hai làng; P2 = lỗi có điều kiện kích hoạt cụ thể, cần sửa và bổ sung regression test.

## F1 — [P1] Chuyển làng làm mất phương án thả quân main dù tự chỉnh camera đang tắt

- Vị trí: `cocmagic/modules/farm_module.py:235–240`; liên quan `cocmagic/village_navigator.py:142`, `cocmagic/camera_controller.py:160–162` và fallback trong `cocmagic/battle_planner.py:70–86`.
- Trigger: chạy hybrid, hoặc main-only khởi động từ builder, chuyển thành công về main. Navigation gọi `camera.reset_view()`, tăng revision của ADB dùng chung. Revision không trở về 0 khi bắt đầu một trận mới.
- `_make_battle_plan()` chỉ dùng planner main cũ khi **camera_auto_adjust=false và revision=0**. Sau chuyển làng, dù tùy chọn vẫn false, hàm đi vào planner tracked. Planner này từ chối fallback khi không có `standard_view`; trường `_standard_view` trong FarmModule hiện chỉ được gán `None`, chưa có đường gán bằng chứng hiệu chỉnh hợp lệ.
- Tái hiện: cùng ảnh `tests/fixtures/user_decorated_scenery.png`, trước reset trả `outer_perimeter` với **26 điểm**; sau một `reset_view()`, revision=1 và kết quả là **None**. Không có thao tác camera hay thay đổi ảnh trong phép thử.
- Hậu quả: `_state_loot_check()` bỏ qua đối thủ vốn được luồng main cũ chấp nhận. Nếu đã vào `_state_attacking()`, bot đi vào nhánh rút lui/chờ kết thúc khi không lập được plan. Chế độ hybrid mặc định có thể mất khả năng farm các loại cảnh này sau lần kiểm tra builder đầu tiên.
- Hướng sửa: tách revision vô hiệu tọa độ khỏi điều kiện bật/tắt chiến lược camera; sau chuyển làng phải có đường xác nhận lại view và lập plan mới cho main. Giữ phương án dò có receipt hoặc hiệu chỉnh view phù hợp khi đường đỏ chưa đủ. **Không** khắc phục bằng cách bỏ kiểm tra revision hoặc dùng lại tọa độ cũ.
- Regression cần thêm: dùng navigator/coordinator đưa builder→main, camera=false, rồi chạy loot-check trên fixture cảnh trang trí; phải lập được phương án mới có kiểm chứng. Kiểm thêm main startup từ builder và trường hợp camera thật sự đã thay đổi.

## F2 — [P1] Hai alias của một MuMu vẫn lấy quyền điều khiển đồng thời

- Vị trí: `cocmagic/hybrid_runtime.py:32–37`; nơi engine sử dụng: `cocmagic/bot_engine.py:131–136`.
- Khóa OS và tên runtime được tạo từ **chuỗi serial**, không từ danh tính thiết bị. `emulator-5556` và `127.0.0.1:16416` có hai file khóa khác nhau. Hồ sơ live của dự án xác nhận hai địa chỉ này là cùng một MuMu.
- Tái hiện offline: giữ lease của `emulator-5556`, lease thứ hai cùng serial bị chặn đúng; lease `127.0.0.1:16416` vẫn acquire thành công ngay lúc đó.
- Hậu quả: mở hai CLI, hoặc GUI và CLI, qua hai alias sẽ cho phép hai worker độc lập gửi tap/pinch vào cùng game. Khóa RLock của mỗi coordinator chỉ bảo vệ bên trong worker, không giải quyết xung đột này. Lịch/runtime cũng bị chia thành hai bản cho cùng máy.
- GUI có deduplicate bằng `boot_id` trong `device_manager.py`, nhưng engine/CLI không sử dụng danh tính đó khi acquire quyền điều khiển.
- Hướng sửa: resolve danh tính thiết bị trước khi cấp quyền input và dùng khóa chung theo danh tính, vẫn giữ serial làm địa chỉ transport. Chọn định danh runtime bền vững hoặc migration phù hợp; `boot_id` đủ phân biệt alias trong phiên boot nhưng tự nó không bền qua reboot. Nếu không xác minh được danh tính, phải có xử lý rõ ràng, không giả định hai serial là hai máy.
- Regression cần thêm: hai process, hai serial, cùng identity → chỉ một process được quyền input; hai identity thực sự khác nhau → cả hai chạy độc lập; Stop một process không release input của process còn lại.

## F3 — [P2] Kỹ năng tướng có thể chiếm mọi lượt xử lý, không thả thêm Rồng con

- Vị trí: `cocmagic/modules/builder_farm_module.py:466–479`.
- `_battle()` luôn ưu tiên kỹ năng quân rồi kỹ năng tướng; gặp tướng READY đủ khoảng cách thời gian thì `return self._ability(slot)` trước khi xử lý `available`. Kỹ năng tướng có thể lặp lại, nhưng không có giới hạn số lượt kỹ năng liên tiếp khi còn quân chưa thả.
- Trigger: các lượt xử lý bị kéo dài bởi capture/nhận diện/tải CPU hoặc pause, đến lần đọc tiếp theo tướng đã READY trở lại. Receipt CHARGING của lần dùng trước vẫn hợp lệ; đây không phải trường hợp giả sử tap thành công.
- Tái hiện điều khiển với fake clock/reader: 5 lượt cách nhau 35 giây, mỗi lượt tướng READY → bấm → xác nhận CHARGING; còn 6 ô Rồng con UNDEPLOYED. Kết quả **5 kỹ năng tướng, 0 lần gọi deploy, không báo halt**. 35 giây là điều kiện thử, không phải khẳng định thời gian hồi kỹ năng thực tế của mọi tướng.
- Hậu quả: trận có thể hết giờ trong khi còn quân chưa triển khai. Hồ sơ GĐ8 đã có phiên around thiếu quân dưới tải; phép thử này xác nhận một đường lỗi độc lập, **chưa chứng minh đây là nguyên nhân duy nhất của phiên live đó**.
- Hướng sửa: bảo đảm tiến độ thả quân bằng giới hạn số lượt kỹ năng liên tiếp hoặc xen kẽ có ngân sách thời gian. Vẫn ưu tiên kỹ năng quân sắp chết khi có bằng chứng phù hợp; không để kỹ năng tướng lặp lại chặn việc triển khai toàn bộ đội quân.
- Regression cần thêm: READY/CHARGING có receipt, độ trễ capture khác nhau, còn nhiều ô chưa thả; phải có deploy trong số lượt hữu hạn và hoàn tất trong ngân sách trận. Sau đó đo lại around trên tải mục tiêu và hai giả lập thật.

## F4 — [P2] Đổi camera chưa xóa lịch sử điểm builder theo tọa độ màn hình

- Vị trí: `cocmagic/modules/builder_farm_module.py:113–118`; nơi dùng dữ liệu còn sót: `cocmagic/builder_tactics.py:139–158`.
- `_camera_changed()` chỉ bỏ `plan`, `reference`, `confirmed_point`; vẫn giữ `tactics.accepted` và `tactics.rejected`. Hai danh sách này chứa tọa độ màn hình của view trước.
- Sau khi dựng plan mới, `point()` tiếp tục loại những tọa độ trong `rejected`, đồng thời tính góc/khoảng cách rải xung quanh dựa vào `accepted` cũ. Cùng tọa độ pixel sau pan/zoom có thể ứng với vị trí map khác.
- Tái hiện synthetic: revision tăng từ 0→1, lịch sử accepted/rejected vẫn giữ nguyên. Gán plan mới có 2 điểm mà tọa độ trùng rejected của view cũ → `point()` trả None dù đó là 2 ứng viên của plan mới. Trong module, None dẫn đến lỗi “Không còn điểm thả hợp lệ quanh biên nhìn thấy”.
- Hướng sửa: xóa lịch sử tọa độ theo view cùng lúc vô hiệu plan, hoặc lưu theo revision và chỉ dùng khi khớp. Nếu cần giữ phân bố quân đã thả, phải dùng tọa độ map đã xác minh phép biến đổi; không sử dụng nguyên pixel cũ. Giữ nguyên ledger kỹ năng đã dùng và giới hạn retry của trận để không tạo vòng lặp vô hạn.
- Regression cần thêm: deploy/reject → pan/zoom/manual camera → plan mới; không lọc nhầm điểm mới, không dùng góc cũ, không phục hồi kỹ năng một lần đã tiêu thụ.

## Đối chiếu từng giai đoạn

| Giai đoạn | Nhận xét review | Điều kiện còn lại |
|---|---|---|
| GĐ0 — baseline, khảo sát video | Có baseline 213 test và nguồn fixture được ghi rõ; không thấy vấn đề mới cần chặn | Baseline là hồ sơ lịch sử, không đại diện trạng thái mới |
| GĐ1 — config, ba tab, Run | Migration/scoped validation và tách instance có kiểm thử; không phát hiện lỗi mới trong lượt này | Giữ kiểm thử save/reopen và khóa cấu hình khi chạy |
| GĐ2 — màn hình, thưởng sao | COMPLETE có hai capture độc lập; UNKNOWN không bị coi là hết thưởng | Thiếu bằng chứng native AVAILABLE/CLAIMABLE và chuỗi claim trên profile đang hỗ trợ |
| GĐ3 — camera, tọa độ thả | Có backend/receipt/reset/revision; phát hiện F1 và F4 | Sửa invalidation và xác nhận lại view; kiểm tra trên main multiplayer và builder |
| GĐ4 — chuyển làng, thưởng, xe | Đã có bằng chứng chuyển làng và xe; gate nguồn dữ liệu qua | Chưa đủ native claim→còn thưởng→claim→COMPLETE; chưa đủ lỗi thu/đóng panel trên game thật |
| GĐ5 — builder, hai cách thả | Có module, receipt deploy/skill, khu 2; phát hiện F3 và F4 | Chốt lại around dưới tải; hero absent/upgrading/Copter cần native evidence đầy đủ |
| GĐ6 — hybrid, lịch 15:30 | Fake-clock tests bao phủ lịch và safe boundary; nhánh main sau chuyển làng bị F1 | Cần chuỗi thật còn sao→đánh đủ→nhận thưởng→thu xe→main, cùng lần kiểm tra đến hạn thực tế |
| GĐ7 — recovery, cô lập instance | Recovery/ownership có tests; phát hiện F2 ở alias | Kiểm khóa theo identity và hai giả lập thật; chưa được tính hai alias thành hai máy |
| GĐ8 — tích hợp, nghiệm thu | Gate offline qua nhưng không đủ chốt nghiệm thu | Sửa 4 lỗi và hoàn tất các ca live còn thiếu; không ghi PASS toàn bộ dựa vào số test |

Các kết quả live trong bảng được đối chiếu từ hồ sơ `dual-village-validation.md` và manifest/receipt hiện có, không phải các phiên live mới do review này thực hiện.

## Kiểm tra đã thực hiện trong lượt review

| Kiểm tra | Kết quả |
|---|---|
| `python -X utf8 -m unittest discover -s tests -q` | **486 tests, 395.146 giây, OK, exit 0**, không báo skip |
| `python -X utf8 tools/check_assets.py` | **ALL CHECKS PASSED**, exit 0 |
| `python -X utf8 tools/check_dual_village_evidence.py --output diagnostics/review_gd0_gd8_20261011/evidence-audit.json` | **9 manifest, 160 file công bố, 163 nguồn riêng, 0 lỗi**, không thiếu private parent |
| `git diff --check` | Exit 0; chỉ có cảnh báo chuẩn hóa LF/CRLF |
| Script tái hiện bổ sung | 4 điều kiện lỗi nêu trên đều xuất hiện; không kết nối ADB hoặc gửi input game |
| Đo `BuilderBattleReader.read_bar()` trên fixture native | Median khoảng **1.15–1.34 giây/lần đọc**, 3 lần/fixture, sau khi full suite kết thúc; đây chỉ là CPU perception, không phải latency trận end-to-end |

Nguồn review cục bộ (diagnostics bị gitignore):

- `diagnostics/review_gd0_gd8_20261011/unittest.log`
- `diagnostics/review_gd0_gd8_20261011/evidence-audit.json`
- `diagnostics/review_gd0_gd8_20261011/reproduce_review.py`
- `diagnostics/review_gd0_gd8_20261011/reproductions.json`
- `diagnostics/review_gd0_gd8_20261011/reader-timings.json`

Chạy lại tái hiện: `python -X utf8 diagnostics/review_gd0_gd8_20261011/reproduce_review.py`. Đây là diagnostic in trạng thái lỗi hiện tại, chưa được thêm vào bộ regression chính thức.

## Thứ tự xử lý đề xuất

1. Sửa F2 để bảo đảm một chủ điều khiển cho mỗi máy thật trước các lượt thử live tiếp theo.
2. Sửa F1, thêm regression builder→main với camera=false và cảnh thiếu đường đỏ.
3. Sửa F3 và F4; kiểm ngân sách thả quân, map revision và ledger kỹ năng độc lập với nhau.
4. Chạy các regression liên quan, sau đó full suite và hai gate asset/evidence một lần trên bản sửa cuối.
5. Hoàn tất native bonus AVAILABLE/CLAIMABLE, chuỗi hybrid đầy đủ, around dưới tải, các trạng thái tướng và hai giả lập thật. Cập nhật validation theo từng ca có receipt, giữ trạng thái “chưa kiểm chứng” cho ca chưa thực hiện.
