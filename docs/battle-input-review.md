# Kiểm tra thao tác train và sự kiện — 04/10/2026

Đây là báo cáo trước khi đối chiếu video. Bản sửa tiếp theo và kết quả 193 test nằm trong [video-burst-review.md](video-burst-review.md).

Đã sửa các lỗi tái hiện được từ ảnh và luồng thao tác trong dự án:

- Ảnh base có cây/trang trí trước đây chỉ nhận được hai ô gần cuối thanh quân. Nay nhận đủ chín ô, tách đúng lính, xe công thành, bốn hero và hai phép. Chân dung hero xám vẫn giữ vị trí riêng; tọa độ hero được đưa về tâm ô để kiểm tra máu Warden đúng hàng.
- Số `x10` có thể mất chữ số đầu rồi bị đọc thành `x0`. Bộ đọc mới kiểm tra cả dãy chữ số, tách được trường hợp `x` chạm số và trả về chưa rõ khi chữ số đầu bị thiếu. Các ảnh thật đọc được balloon x10, rage x3, totem x1 và lightning x10.
- Luồng lính thường bị giới hạn ở bốn nhóm năm quân. Nay tiếp tục theo số còn lại; các mô phỏng đọc chữ số từ ảnh đã xác nhận thả hết 30 và 65 quân. Điểm mới được thử riêng; chỉ điểm đã làm giảm quân mới được dùng trong nhóm lệnh và cho hero đi theo.
- So sánh vùng số thô có thể nhận nhầm thay đổi màu/khung chọn là quân đã dùng. Nay lấy ảnh sau khi chọn ô, kiểm tra số giảm trên tối đa ba ảnh mới; khi OCR chưa rõ thì so hình chữ số tách khỏi nền. Ô đã x0 được bỏ qua cả khi chưa chuyển xám.
- Khi bonus xuất hiện, luồng chờ giao diện ổn định, chọn tài nguyên, chờ hai ảnh liên tiếp đã đóng bảng rồi chọn lại ô đang dùng. Ba khung bonus chưa hiện tiêu đề cũng chặn thao tác thả. Khi thấy kết quả hoặc về làng, bot hủy phần còn lại của chuỗi bấm, kể cả sau bonus 100% và giữa nhóm kỹ năng hero.

Kiểm thử hoàn tất:

```text
python -m unittest discover -s tests
Ran 179 tests in 62.790s
OK

python tools/check_assets.py
ALL CHECKS PASSED

python -m compileall -q cocmagic tests
exit code 0
```

Đã bổ sung 22 test so với bộ 157 test trước, gồm nhận dạng trực tiếp ảnh thanh quân, phản hồi quân giảm/chậm/không giảm, vùng thả bị từ chối, chữ số bị thiếu, bonus đang chuyển động, trận kết thúc giữa chuỗi bấm và xử lý lỗi khi đã sang kết quả. Test toàn chuỗi nhận dạng–chọn ô–thả quân–hero–phép dùng ảnh thật và mô phỏng phản hồi game, chạy cả chế độ thường lẫn sự kiện với ba bảng bonus.

Đã chụp ảnh trực tiếp qua ADB ở hai địa chỉ 127.0.0.1:16416 và 127.0.0.1:7555. Cả hai kết nối trả về ảnh 1600 × 900 và được nhận đúng là màn hình làng. Không gửi lệnh thả quân vào game trong lần kiểm tra này; trận đánh trực tiếp chưa được xác nhận.

Đóng hẳn giao diện CocMagic và mở lại để nạp mã mới cùng bộ nhớ nhận dạng combo mới. Dừng rồi bắt đầu bot trong cửa sổ cũ vẫn giữ các module Python đã nạp.

Các test chuyên biệt nằm trong `tests/test_battle_input_review.py`, `tests/test_spell_regressions.py`, `tests/test_event_rewards.py` và `tests/test_deployment_perimeter.py`.
