# Sửa vòng lặp kiểm tra builder trong hybrid — 11/10/2026

Bản sửa tiếp nối `7b74ef6`, qua **538 test / 328.984s / OK** và năm gate còn lại. Live trên bản cuối hoàn thành **3 chu kỳ main**, chỉ kiểm tra xe một lượt lúc startup, không quay lại builder sau các trận. Bot dừng tại main Home; hết pending thưởng, lịch tiếp theo **12/10/2026 15:30 UTC+7**.

## Nguyên nhân đã tái hiện

Guard gặp ảnh chưa nhận diện trong giao dịch kết thúc trận main gọi chung luồng reload. Luồng này xóa kết quả thưởng sao đã xác nhận và tạo yêu cầu builder mới. Sau khi tách phục hồi input khỏi reload, live thăm dò còn phát hiện nhánh phân loại lại main RESULT vẫn tạo yêu cầu startup builder vô điều kiện: runtime đã COMPLETE và không pending, nhưng request chuyển builder lại được tạo.

Lượt thăm dò `live-soak/receipt.json` ghi 3 trận main, 3 lần phục hồi ảnh, 4 lượt builder → main trong 671.300s; sau từng RESULT đều quay sang builder và kiểm tra xe. Đây là phiên **phát hiện lỗi, không phải PASS**. Probe trước đó dừng ngay khi về main (`main_ticks=0`) nên chưa kiểm tra được vòng lặp sau trận.

Ngoài ra, lỗi xe dù đã có Home rõ vẫn tạo retry thưởng, và xe đang mở có thể bị mở lại sau khi vừa đóng hoặc khi lần đọc thưởng sau xe trả UNKNOWN.

## Thay đổi

- Tách reset do input/ảnh chưa rõ khỏi reload game thật. Phục hồi main vẫn hủy cache/tọa độ/giao dịch cũ, giữ kết quả thưởng trong ngày và request daily đang chờ.
- Phân loại lại main RESULT/BATTLE chỉ tạo startup/recovery builder khi có đúng lý do đang chờ. Daily/retry tiếp tục qua scheduler, giữ thời gian chờ và giới hạn retry; không biến kết thúc mỗi trận thành một lần startup.
- Xe không thu được nhưng đã xác nhận Home chỉ ghi cảnh báo và tiếp tục main; không đánh dấu thưởng sao chưa hoàn thành. Nếu chưa xác nhận đóng bảng/Home, vẫn dừng thay vì chuyển làng mù.
- Giữ receipt kiểm tra xe trong chuyến builder để không mở lại sau resume hoặc UNKNOWN sau xe. Đọc lại thưởng bằng ảnh mới trước khi về main; nếu có nhiệm vụ sao tiếp thì tiếp tục builder và đặt lại quyền kiểm tra xe.
- Khi thao tác thuyền báo chưa thấy đích nhưng cặp ảnh Home mới chứng minh đã đến builder, đọc sao ở tick kế tiếp, không thu xe/về main rồi retry một chuyến thừa.
- Console ghi lý do phục hồi và chuyển làng. Bổ sung soak probe nhiều trận với frame/input guard và popup handler production, thời gian từng tick, nguồn/hash và phát hiện lượt builder thừa.

Không dùng COMPLETE lịch sử để bỏ startup; UNKNOWN vẫn không phải hết sao. Lịch mặc định 15:30 UTC+7 và camera đã lưu được giữ nguyên.

## Kiểm thử

| Kiểm tra | Kết quả |
|---|---|
| Full unittest | **538 test / 328.984s / OK**, exit 0 |
| Ruff, compileall | Exit 0 |
| Asset/import, evidence, CLI help | Exit 0; 9 manifest, 170 file công bố, 173 nguồn riêng, không lỗi |
| Source trong sáu gate và phiên live | Không đổi; hash source live khớp source đã test |
| Cấu hình/license | 4 file kiểm bằng SHA-256, không đổi |

Có 9 regression mới: 7 ca scheduler/recovery/cart/thuyền, 2 ca điều khiển probe. Ca guard → RESULT → Home lặp bốn chu kỳ, cả RESULT có/không có dấu village, phải giữ COMPLETE và chỉ một lần xe. Kiểm tra thêm request daily đã chờ, backoff/giới hạn retry, xe tùy chọn lỗi ở Home, resume xe và UNKNOWN sau xe, đến builder trễ sau tap thuyền. Hai ca probe bảo đảm tiếp tục qua nhiều Home và không công bố PASS nếu có lượt builder thừa. Các ca này dùng clock/transport giả và **không tính là live**.

## Live trên bản cuối

Lệnh dùng `tools/hybrid_probe.py --serial 127.0.0.1:16416 --seconds 1200 --main-cycles 3 --instance-settings` với output/stop-file riêng. MuMu Android 15, English 1600×900. Dùng engine/coordinator/module/reader/ADB thật, khóa input cùng production, frame/input guard và popup handler; không giả frame/tick/thưởng, không đổi giờ Windows. Probe không chạy GUI/license watchdog.

`live-final/receipt.json`, `live-final.log` và `live-audit.json` ghi:

- `completed=true`, elapsed **440.159s** (khoảng 7 phút 20 giây), 62 tick main, 3 lần về Home sau trận, 1 base bị bỏ qua.
- `passes=1`: chỉ builder → main lúc startup. Sau các trận, **0** lượt main → builder; console chỉ có **1** lượt kiểm tra xe.
- Cả ba lần guard phục hồi ảnh main xuất hiện thật; COMPLETE được giữ, không phát sinh chuyến builder.
- Quân, xe công thành, tướng và phép đã triển khai. Auto train và camera **bật** theo cấu hình instance; wall/event **tắt riêng trong probe**, không sửa cấu hình của người dùng.
- Final status: `actual_village=main`, `confirmed_screen=home`, `last_bonus_state=complete`, `pending_builder_check=false`, `last_error=null`; không hết ngân sách, không cancel.

Xe lúc startup trống/đang phòng thủ theo log và được đóng trước chuyển main. Không có lượt Collect có tiền trong phiên này; không công bố đã thu mới tài nguyên. Cache builder bị xóa khi phục hồi main nên trường `cart` cuối receipt là null; kiểm chứng số lượt/kết quả xe từ log và trace input. Probe đặt Stop trước ảnh cuối nên không có `final.png`; ảnh đọc riêng sau khi probe kết thúc ở `post-probe-home.png/.json` xác nhận MAIN_HOME, không gọi ảnh đó là frame cuối của vòng lặp.

Lượt thăm dò và lượt cuối có điểm khởi động/base khác nhau, nên thời gian tổng không phải benchmark tốc độ. Cải thiện được chứng minh là loại chuyến đi-về builder và mở xe thừa. Chưa nghiệm thu lại toàn chuỗi live AVAILABLE → nhiều trận builder → CLAIMABLE → COMPLETE trong phiên này; xem hồ sơ trước tại [báo cáo native reward](dual-village-hybrid-fix-20261011.md).

Toàn bộ ảnh đầy đủ, log, receipt, SHA và audit ở `diagnostics/hybrid_repeat_fix_20261011/`, ngoài Git. Source không đưa cấu hình/license/archive/log cá nhân vào commit.

## Chạy lại

Đóng ứng dụng CocMagic rồi mở lại để nạp module mới; Stop/Start trong process cũ không bảo đảm nạp code. Chọn Run → Làng chính + Làng đêm. Hết sao → kiểm tra xe một lượt → main; kiểm tra thưởng tiếp lúc 15:30 ngày sau. Startup buổi sáng vẫn cho phép lượt kiểm tra sau 15:30 cùng ngày.
