# Kiểm tra video và sửa tốc độ triển khai — 04/10/2026

Video đối chiếu: `bandicam 2026-10-04 16-58-59-503.mp4`, dài khoảng 108 giây. Các ảnh thanh quân, Quản Giáo chưa được thả, bảng đổi chế độ và bảng bonus đã được lưu thành fixture trong `tests/fixtures/event_video_*.png`.

## Lỗi xác nhận trong video

- Sau lệnh thả Quản Giáo, thanh máu chưa xuất hiện. Tọa độ bấm ở đáy ô chạm nút đổi chế độ; khoảng giây 40 mở bảng **Change Troops**.
- Khoảng giây 46, bot báo không nhận diện được bonus tài nguyên rồi dừng. Bảng có một thẻ viền vàng và hai thẻ viền bạc; bộ nhận diện cũ yêu cầu ba thẻ viền bạc nên bỏ sót dầu đen bên phải.
- Luồng sự kiện chụp và nhận diện lại trước từng lần bấm, đồng thời thử nhiều điểm nhỏ, làm chậm cả quân và tướng.

## Thay đổi

- Thử điểm mới bằng một quân rồi lưu những điểm game đã chấp nhận trong trận hiện tại. Các ô quân tiếp theo dùng lại điểm đó; phần quân còn lại được gửi theo nhóm, tối đa 80 lệnh mỗi nhóm, rồi kiểm tra số lượng bằng ảnh mới.
- Trong chế độ sự kiện, nhóm nhanh chỉ dùng tọa độ ngoài vùng thẻ bonus. Sau khi bonus nuốt một phần lệnh, bot chọn tài nguyên, đọc lại số quân và tiếp tục phần còn lại. Tọa độ nằm trên vùng thẻ vẫn được kiểm tra từng thao tác.
- Gửi các cặp chọn–thả tướng trong một nhóm; bấm phần chân dung phía trên thay vì nút ở đáy ô Quản Giáo. Bot xác nhận bằng thanh máu có khung, chờ thêm ảnh nếu cập nhật chậm và chỉ thử lại tướng chưa được xác nhận. Cỏ xanh trên nền không còn được coi là thanh máu.
- Giữ danh sách kỹ năng đang làm tới khi nhóm hoàn tất. Nếu bonus ngắt nhóm, bot chọn tài nguyên rồi gửi lại nhóm kỹ năng cho các tướng đã triển khai; kỹ năng đã dùng không thể kích hoạt lần hai. Phép bị bonus ngắt cũng được thử lại trước khi chuyển mục tiêu.
- Bộ nhận diện bonus hỗ trợ cả viền vàng và bạc, vẫn chỉ chọn tài nguyên. Bảng đổi chế độ Quản Giáo không bị coi là bonus.
- Tọa độ thanh quân được dùng lại và kiểm tra trong phiên; điểm thả chỉ được dùng lại trong cùng trận. OCR số lượng và trạng thái ô được lưu theo ảnh, xóa khi ảnh đổi; hiệu chuẩn tướng dùng chung kết quả quét thanh quân. Khởi động lại game xóa cache liên quan.

## Kiểm thử

```text
python -m unittest discover -s tests
Ran 193 tests in 46.812s
OK

python tools/check_assets.py
ALL CHECKS PASSED

python -m compileall -q cocmagic tests
exit code 0
```

14 test mới trong `tests/test_video_burst_regressions.py` kiểm tra trực tiếp ảnh từ video và mô phỏng phản hồi game. Các trường hợp gồm viền vàng ở ba độ phân giải, Quản Giáo chưa được thả, thanh máu cập nhật chậm, bonus ngắt quân/tướng/kỹ năng, cache số lượng và trận kết thúc giữa nhóm kỹ năng.

Trong mô phỏng 30 quân với một điểm mới hợp lệ, bot thử một quân rồi gửi 29 quân còn lại trong một nhóm, dùng hai lần chụp ảnh xác nhận. Ô tiếp theo dùng điểm đã lưu và chỉ cần một ảnh xác nhận. Bốn tướng được chọn–thả bằng một nhóm tám lệnh khi các tọa độ nằm ngoài thẻ bonus.

Chưa chạy trận trực tiếp sau bản sửa này; kết quả trên xác nhận bằng ảnh video và mô phỏng, chưa đo tốc độ thực tế trong game. Đóng hẳn cửa sổ CocMagic rồi mở lại để nạp mã mới; Stop/Start trong cửa sổ cũ vẫn giữ các module Python đã nạp.
