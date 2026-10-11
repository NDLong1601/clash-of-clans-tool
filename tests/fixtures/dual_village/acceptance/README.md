# Bằng chứng GĐ8

Lượt sửa hybrid sau phản hồi người dùng bổ sung `builder-star-reward-native.png`: giữ bảng thưởng và HUD làng, loại tên/số dư/level, không resize. Dùng kiểm CLAIMABLE, modal chặn Home và input Okay có receipt trong transport giả. Ảnh này không chứng minh một chuỗi nhận thưởng live; xem [sửa hybrid](../../../../docs/dual-village-hybrid-fix-20261011.md).

Hai PNG GĐ8 ban đầu là **transformed_test từ ADB native**: giữ nguyên kích thước 1600×900, chỉ giữ ROI timer và Surrender cùng nền nhỏ bên trong ROI; các pixel còn lại được tô đen. Loại tên người chơi, số dư tài nguyên và thanh quân. Dùng để kiểm guard main trước quân đầu tiên, không phải ảnh đầy đủ chứng minh một trận.

Ngày 11/10 bổ sung bốn ảnh regression: Home main với artwork Attack mới, Home builder còn sao native `0/8`, tướng đang nạp với cạnh thanh máu ngắn và camp thứ năm đang chọn. Chỉ giữ các ROI HUD/map cần thiết, loại tên/số dư, không resize. Parent/phép biến đổi riêng của từng ảnh ở manifest; ảnh Home builder giữ texture bản đồ vô danh để kiểm độ ổn định. Xem [báo cáo kiểm thử](../../../../docs/dual-village-verification-20261011.md) để phân biệt kết quả test với các bước game thật đã quan sát.

`manifest.json` ghi nguồn/hash/phép biến đổi và hash receipt. `live-receipt.json` chỉ giữ kết quả/metrics/phạm vi của các phiên thật, gồm cả FAIL trước sửa; loại settings, raw input và ảnh riêng. Counter có thể gồm result kế thừa: xem scope từng phiên, không quy counter thành số trận mới. Tắt tướng trong settings không chứng minh tướng thật vắng/nâng cấp.

Nguồn riêng nằm trong `diagnostics/dual_village_gd8/`, không đưa vào git. `python tools/check_dual_village_evidence.py` kiểm hash/dimensions và đối chiếu raw receipt/log nếu có. Nguồn riêng thiếu trên máy khác được báo riêng, không coi byte check là PASS thị giác/game. Kết luận và giới hạn: [validation](../../../../docs/dual-village-validation.md).
