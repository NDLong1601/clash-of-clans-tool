# Hybrid GĐ6 — lịch và runtime

Hybrid dùng **BuilderFarmModule thật của GĐ5** và FarmModule hiện có. Coordinator cùng worker sở hữu input và runtime của serial; không có thread scheduler gửi input hoặc worker thứ hai sửa runtime. Main-only và builder-only tiếp tục dùng coordinator thường; builder-only không kết thúc khi thưởng COMPLETE.

## Startup và thưởng

Mỗi startup xác nhận/chuyển builder và đọc màn hình mới. Runtime COMPLETE chỉ là lịch sử. Startup trong trận main đã nhận diện phải hoàn tất giao dịch và nhường ở Home trước khi chuyển builder. Trận builder đang có được tiếp quản bằng module GĐ5, không tải tọa độ trận cũ.

- CLAIMABLE: handler GĐ4 nhận bảng, xác nhận đóng và đọc lại; không tự gán COMPLETE.
- AVAILABLE: tiếp tục nhiều trận, kể cả x=0 và mẫu số khác 7. Nhận bảng sau trận rồi đọc lại. Có sao thì không về main.
- COMPLETE: chỉ từ StarBonusReader với đúng builder/Attack và hai ảnh mới ổn định. Thu xe, đọc thưởng lại sau bảng xe; nếu có lượt mới thì tiếp tục builder. Chỉ yêu cầu về main khi chuỗi đang khả dụng đã hết.
- UNKNOWN: tối đa 3 giao dịch đọc hữu hạn, nghỉ 15 giây monotonic giữa lần đọc. Không ghi valid/daily hoặc COMPLETE. Sau đó thử thu xe và về main nếu Home được xác nhận; nếu không xác nhận được màn hình thì dừng riêng instance.

Trong hybrid, thu xe trước chuyến về main luôn áp dụng, kể cả khi `builder_collect_cart=false` (công tắc này điều khiển hậu xử lý của builder-only). Collect khóa hoặc còn phòng thủ được xử lý hữu hạn theo GĐ4; không chờ phòng thủ xong. Thu không đối soát được nhưng Home đã xác nhận có thể về main với lỗi/chưa hoàn thành; không công bố đã thu thành công.

## Quy tắc thời gian

Wall clock timezone-aware `Asia/Ho_Chi_Minh` quyết định lịch. Windows thiếu tzdata dùng `timezone(timedelta(hours=7))`; không dùng timezone hệ điều hành. Mặc định `hybrid_check_time="15:30"`, chấp nhận HH:MM hợp lệ trong settings/tab Làng đêm. Không gọi cron/automation hoặc đổi giờ Windows.

Điều kiện đến hạn: **now >= mốc hôm nay và ngày đó chưa có kiểm tra hợp lệ**. Startup hợp lệ sau mốc cũng thỏa daily; startup trước mốc không tiêu lượt. Kể cả retry buổi sáng đã cạn, mốc daily vẫn có budget mới: `last_daily_request_date` chỉ ghi đã phát yêu cầu để tránh cấp lại budget mỗi tick, tuyệt đối không thay `last_daily_check_date` hợp lệ. Trong lúc train builder qua mốc, một lần đọc hợp lệ sau mốc cũng thỏa daily ngay trong chuyến đó. Máy ngủ nhiều ngày chỉ kiểm tra ngày hiện tại; không replay ngày vắng mặt. Mốc reset 13:00 do người dùng mô tả không tự gán có/hết thưởng; quyết định vẫn theo màn hình thật.

Yêu cầu đến giữa trận/modal/wall được giữ pending. Callback trước Attack của main cũng poll lịch sau thao tác dài. Coordinator chỉ chuyển tại điểm nhường GĐ2: Home mới đã xác nhận, không modal, batch hoặc giao dịch chưa đối soát. Không bấm thuyền/back giữa trận.

Retry, cooldown và ngân sách dùng monotonic; timestamp `next_retry_at` wall clock chỉ để hiển thị. Mỗi chuỗi builder tối đa mặc định **1800 giây / 12 trận**, được chỉnh bằng `hybrid_builder_budget_seconds` (300–7200) / `hybrid_max_battles` (1–50). Tiến độ sao có OCR đứng yên qua nhiều kết quả và không có thưởng nhận thêm cũng có giới hạn. Chạm budget trong trận chỉ yêu cầu trở về sau Home; không rút lui bằng tọa độ/nút chưa xác nhận. Timeout/không tiến triển của từng trận vẫn do GĐ5 quản lý.

Một chuyến lỗi được ghi chưa hoàn thành. Sau khi quay main an toàn, retry sau 300 giây monotonic, tối đa 3 chuyến lỗi trong cửa sổ startup buổi sáng hoặc cửa sổ daily từ mốc kiểm tra. Hết budget retry vẫn chạy main, giữ lỗi/pending; mốc daily mới/ngày mới được kiểm tra tiếp. Restart luôn bắt đầu một startup check mới với budget hữu hạn mới.

## Runtime và quan sát

`data/runtime/<serial-chuan-an-toan>-<sha256-prefix>.json`, schema riêng version 1, atomic tempfile → fsync → replace. Engine xác minh UUID boot của Android trước input ở cả ba mode. Khóa OS theo VM và các serial alias đã xác minh được giữ suốt phiên: worker thứ hai qua alias của cùng VM cũng bị từ chối. Chỉ thread sở hữu khóa được ghi runtime. VM khác có file/khóa riêng; tên có hash tránh va chạm sau sanitize. Close/worker exit giải phóng khóa.

Serial chuẩn ưu tiên cổng MuMu trong các transport ready cùng boot identity. Nếu chưa có file chuẩn, store đọc file alias cũ đã xác minh và lưu lần tiếp theo vào file chuẩn; không xóa file cũ. Reboot không tự mất runtime khi serial chuẩn giữ nguyên. Không xác minh được danh tính serial đã chọn thì từ chối input. Probe live cũng giữ khóa trong `data/runtime/` dùng chung với GUI/CLI, dù runtime thử riêng được ghi vào thư mục output.

Trường lưu: `last_valid_bonus_check_at`, `last_daily_check_date`, `last_daily_request_date`, `last_bonus_state`, `bonus_progress`, `pending_builder_check`, `pending_reason`, `next_retry_at`, `retry_count`, `retry_date`, `last_error`, `builder_incomplete`. Không lưu tọa độ, quân đã chọn hay cache trận. File thiếu/hỏng/sai schema log phục hồi UNKNOWN và bắt buộc đọc màn hình; không suy đã hoàn thành. Lỗi ghi/khóa không bị bỏ qua âm thầm.

Run hiển thị mode, làng đã xác nhận, lý do, trạng thái/tiến độ sao, lần đọc hợp lệ gần nhất, mốc daily tiếp theo, pending/retry và lỗi. Làng chưa xác nhận hiển thị riêng với module đang hoạt động. Lịch đến hạn đang pending có thể hiển thị mốc quá khứ cùng pending; retry có timestamp riêng.

## Kiểm chứng

`python -m unittest discover -s tests -p test_hybrid_scheduler.py -q` dùng fake wall/monotonic cho 09:00, 15:29, 15:31, giao ngày, ngủ nhiều ngày, pending trong battle/modal/wall, restart, runtime hỏng, atomic failure, hai serial, hai process tranh writer và chuỗi nhận thưởng vẫn còn sao. Fake input chỉ dùng trong test; sản phẩm đăng ký hai module thật.

Probe có kiểm soát: `python tools/hybrid_probe.py --serial 127.0.0.1:16416 --seconds 2000 --daily-pass --output diagnostics/dual_village_gd6/live-cycle`. Probe dùng engine/modules/ADB thật, tắt auto_train/wall/event main qua settings riêng để tránh sửa đội main hoặc nâng tường trong phép thử; không sửa cấu hình người dùng. Dừng sau khi xác nhận về main. `--daily-pass` tiến wall clock riêng của probe sang ngày tiếp 15:31 để kiểm tra đường scheduled trên màn hình thật; không đổi giờ Windows, không giả lập kết quả bonus. Các timer/budget vẫn monotonic thật. `--stop-file <path>` hỗ trợ dừng.

Xem [tiến độ và bằng chứng thực tế](dual-village-progress.md) để biết nhánh đã chạy trên game; test fake clock không phải bằng chứng chuỗi thưởng native.
