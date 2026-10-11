# Sửa hybrid dừng ở nhận thưởng, thu xe và chuyển làng — 11/10/2026

Tiếp nối bản `c72db1b`. Người dùng gửi log lỗi `Camera builder: error`, sau đó `Không tìm được xe ở camera hiện tại` và `Chuyển làng chưa xác nhận được đích`. Bản sửa này qua **529 test**, và một phiên live đã thu xe rồi trở về làng chính thành công.

## Nguyên nhân và thay đổi

Ảnh ADB thật khi kiểm tra cho thấy bảng **Star Bonus! / Okay** đang mở nhưng reader trả `BUILDER_HOME`. Cả ba template title/sao/nút thưởng cũ đều không khớp; HUD thợ và Attack phía sau vẫn khớp. Vùng bảng xanh chiếm 81.97% ROI kiểm tra. Reader phân loại Home chưa có cùng guard bảng xanh như camera, nên có thể đọc vắng sao qua overlay, tìm xe/thuyền trên bản đồ đang bị che rồi dừng.

- Bổ sung ba crop native của title, artwork sao và nút Okay. CLAIMABLE chỉ có khi cùng bảng xanh, title/sao và HUD làng đêm hợp lệ; thiếu nút hoặc sai/thiếu chân dung thợ không cấp quyền nhận thưởng.
- Bảng xanh chưa nhận diện cũng chặn Home. Không coi overlay là hết sao; không gửi camera hoặc tìm xe/thuyền khi bảng thưởng còn mở. Sau nhận thưởng phải đọc ảnh Home mới để xác nhận AVAILABLE hoặc COMPLETE.
- Camera builder bị timeout ổn định ảnh không còn dừng ngay ở lần đầu. Chờ tick/ảnh mới trong giới hạn số thao tác và timeout geometry đã có; không sử dụng tọa độ chưa xác nhận. Lỗi input/release vẫn dừng, giữ nguyên lý do. Stop không bị báo thành lỗi builder.
- Console báo đang kiểm tra xe, kết quả xe và đang chuyển làng. Nếu navigation vẫn thất bại, thông báo giữ nguyên nhân cụ thể từ navigator thay vì chỉ báo chưa xác nhận đích. Không giả chuyển làng thành công để tiếp tục main.

## Kiểm thử trên bản cuối

| Gate | Kết quả |
|---|---|
| Full unittest | **529 test / 368.462s / OK / exit 0**, không failure/error/skip; thời gian process 370.444s. |
| Ruff, compileall | Exit 0. |
| Import/asset và CLI help | Exit 0. |
| Evidence audit | 9 manifest, 170 file công bố, 173 nguồn/receipt/log riêng được kiểm; 0 nguồn thiếu trên máy này, 0 lỗi. |
| SHA-256 source trong sáu gate | Không có thay đổi. Sau test chỉ cập nhật Markdown ghi kết quả. |

Có **10 regression mới**: sáu ca native reward, ba ca camera và một ca nguyên nhân navigation. Ca native transaction chỉ bấm Okay một lần rồi đợi cặp Home mới; ảnh nút bị che, overlay chưa nhận diện và thiếu builder HUD không cấp quyền input. Fixture công bố loại tên, số dư và level; manifest giữ parent/hash/phép biến đổi. Transaction với transport giả được ghi là offline, không gọi là trận live.

## Phiên live

Probe dùng engine/coordinator/module/reader/ADB thật trên MuMu Android 15, English 1600×900; giữ cùng khóa production với GUI và dừng trước main farming. Không sửa settings/license hoặc đổi giờ Windows.

`diagnostics/hybrid_hang_fix_20261011/hybrid-return/receipt.json` ghi:

- `completed=true`, `cancelled=false`, `budget_exhausted=false`, `passes=1`, elapsed **72.426s**.
- Xe: `collected=true`, `returned_home=true`; counter/bar đổi và Collect disabled đã được đối soát.
- Làng thực tế `main`, `last_error=null`, `builder_incomplete=false`, không còn pending thưởng. `main_ticks=0`, không đánh trận main hoặc nâng tường trong probe.

Lúc probe bắt đầu, bảng thưởng đã đóng và Home được xác nhận hết sao. `claim-native.json` có `claims=0`; không dùng receipt đó để công bố bot đã tự bấm nhận thưởng native. Ảnh bảng thưởng thật đã tái hiện lỗi reader và xác nhận CLAIMABLE sau sửa; thao tác Okay cùng đọc lại Home đã có regression offline. Chuỗi live đánh đủ sao → bot tự nhận → thu xe → main vẫn cần nghiệm thu trong tình trạng game phù hợp.

Toàn bộ log, ảnh đầy đủ, hash source và receipt ở `diagnostics/hybrid_hang_fix_20261011/`, ngoài Git. SHA-256 bốn file cấu hình/license người dùng không đổi. Các gate/test 519 trước đó được giữ tại thư mục cũ và [báo cáo trước](dual-village-verification-20261011.md).

## Chạy lại

Đóng cửa sổ CocMagic đang chạy rồi mở lại để nạp module/template mới; chỉ Stop/Start trong process cũ chưa bảo đảm dùng code mới. Chọn Run → Làng chính + Làng đêm → Bắt đầu. Console sẽ báo rõ bước xe/chuyển làng; nếu còn lỗi, giữ log và ảnh game tại thời điểm lỗi để xác định bước không được xác nhận.
