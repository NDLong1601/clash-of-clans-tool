# Sửa các lỗi review GĐ0–GĐ8 — 11/10/2026

Đã sửa F1–F4 trong [báo cáo review](dual-village-review-20261011.md). Phạm vi sửa là bốn lỗi code đã tái hiện; các ca nghiệm thu game thật còn thiếu của GĐ8 tiếp tục được ghi riêng trong `dual-village-validation.md`.

Đợt kiểm thử tiếp theo có thêm sửa lỗi live và **519 test đạt** trên bản cuối; xem [báo cáo kiểm thử/dọn source](dual-village-verification-20261011.md). Số liệu 503 test bên dưới thuộc lượt sửa F1–F4 này.

## Thay đổi và test hồi quy

| Lỗi | Cách sửa | Kết quả test riêng |
|---|---|---|
| F1 — main mất điểm dò sau chuyển làng khi camera=false | Tách quyền dùng chiến lược dò main khỏi revision toàn cục. Mỗi plan mới được dựng từ frame hiện tại và gắn revision hiện tại. Home main đã xác nhận mở chu kỳ geometry mới; nếu camera đã đổi trong trận thì vẫn bỏ fixed fallback và chặn điểm cũ. | Coordinator builder→main→resume→Home→loot-check trả 26 điểm, không skip. Camera đổi giữa trận vẫn chặn input cũ; UNKNOWN không mở lại fallback. Camera=true giữ planner strict. |
| F2 — hai alias cùng MuMu lấy hai khóa input | Engine xác minh UUID boot của Android trước khi acquire. Khóa theo boot identity và giữ thêm các khóa serial của tất cả alias đã xác minh, bảo vệ cả lúc reboot hoặc canonical alias thay đổi. Các alias ưu tiên cùng port MuMu cho runtime; nếu chưa có file chung thì đọc runtime alias cũ và lưu sang file chung, giữ file cũ. | Test hai process/cùng identity bị chặn; hai VM độc lập có khóa riêng. Rejected acquire trả lại mọi khóa đã lấy và không release touch của chủ cũ. Có test reboot, runtime migration, identity lỗi/đổi boot và wiring cả ba mode. |
| F3 — kỹ năng tướng bỏ đói deploy khi nhận diện chậm | Khi còn quân chưa thả, xử lý tối đa một kỹ năng rồi nhường lượt kế tiếp cho một lần deploy. Khi hết quân chưa thả, kỹ năng tiếp tục theo READY/CHARGING và receipt. | Mô phỏng 12 lượt, mỗi lượt cách 35 giây, tướng READY lại giữa các lượt: cả around và single_point đều thả đủ 6 camp, dùng 6 kỹ năng tướng có receipt, không halt và không deploy lặp camp. |
| F4 — accepted/rejected pixel còn sót khi đổi camera | `BuilderTactics.invalidate_view()` xóa plan/reference/confirmed point/accepted/rejected. Camera và popup dùng chung hàm này. Ledger kỹ năng, thời điểm deployment/hero và retry budget vẫn thuộc trận. | Sau đổi revision, điểm từng bị reject ở view cũ dùng được trong plan mới. Kỹ năng đã dùng/đã thử, hero waiting và số retry được giữ nguyên. |

Source sửa: `device_manager.py`, `hybrid_runtime.py`, `bot_engine.py`, `modules/farm_module.py`, `builder_tactics.py`, `modules/builder_farm_module.py`.

Test mới: `tests/test_dual_village_review_fixes.py` — **17 test**. Hai test construction/duplicate worker hiện có được cập nhật để cung cấp danh tính transport giả hợp lệ, thay vì gọi ADB thật trong test offline.

## Kiểm tra trên ADB hiện tại

Đã nối transport ADB nội bộ `127.0.0.1:16416` và chỉ đọc thông tin danh tính. Hai serial `127.0.0.1:16416` và `emulator-5556` được xác minh là cùng **một VM**, cùng canonical runtime `127.0.0.1:16416`. Thử lease trong thư mục tạm xác nhận alias thứ hai bị chặn.

Không gửi tap/pinch/drag hoặc thực hiện trận trong phép kiểm tra này. Đây là bằng chứng kiểm tra transport/lease trên MuMu hiện có, không phải bằng chứng chạy hai game độc lập. Runtime thử ở thư mục tạm; receipt cục bộ tại `diagnostics/dual_village_review_fixes_20261011/identity-readonly.json`.

Canonical runtime được chọn từ các alias ADB ready đã xác minh trong lần khởi động. Khi chỉ một alias hiện hữu, runtime dùng alias đó; startup vẫn đọc lại màn hình thật. Lịch sử file alias có thể được đọc khi alias đó được phát hiện cùng VM trong lần sau. Quyền input vẫn được bảo vệ theo boot identity ngay cả khi danh sách alias không đọc được; nếu danh tính của serial được chọn không xác minh được, engine từ chối input.

## Gate kiểm tra

- Focused regression: **17 test, 1.138s, OK, exit 0**.
- Asset gate: **ALL CHECKS PASSED**, exit 0.
- Evidence gate: **9 manifest, 160 file công bố, 163 private parent, 0 lỗi**, exit 0.
- Syntax/whitespace của source sửa và test mới: đạt; `git diff --check` exit 0.
- Full suite: **503 test, 309.939s, OK, exit 0**, không báo skip. Có 486 test trước review và 17 test hồi quy mới.

Log: `diagnostics/dual_village_review_fixes_20261011/{focused-review.log,unittest.log,assets.log,evidence-audit.json,identity-readonly.json}`. `unittest-intermediate.log` là lượt bị chủ động dừng để nạp bản sửa khóa alias cuối; không tính là gate thành công.

## Phạm vi còn cần nghiệm thu live

Chưa dùng kết quả sửa code để nâng các ca chưa có receipt game thật thành PASS. Chuỗi thưởng AVAILABLE/CLAIMABLE→đánh đủ→nhận thưởng→xe→main, around dưới tải mục tiêu, các trạng thái tướng và hai giả lập thật vẫn cần lượt nghiệm thu theo ma trận GĐ8. Bản sửa F3 đảm bảo fairness trong test điều khiển; latency nhận diện và deployment end-to-end trên game thật vẫn cần đo.
