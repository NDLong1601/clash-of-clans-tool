# Sửa Rage còn sót khi train — 07/10/2026

Video `bandicam 2026-10-07 09-30-42-474.mp4` cho thấy game dùng hai Rage, thanh phép còn x3, nhưng bot báo chưa xác nhận số giảm rồi bỏ ô Rage và chuyển sang chờ trận.

## Thay đổi

- Sau ba ảnh xác nhận chưa thành công, đọc thêm tối đa ba ảnh mới. Hai số liên tiếp giống nhau được dùng để đối soát: giảm thì ghi nhận phép đã dùng; giữ nguyên thì chọn lại phép và thử tiếp, tối đa ba lần trong một lượt.
- Nếu số vẫn chưa rõ hoặc tăng bất thường, giữ ảnh trước lần thả để đối soát sau; không gửi thêm một lần thả khi chưa giải quyết được lần trước. So sánh hình chữ số/trạng thái cạn vẫn hỗ trợ khi OCR số chưa rõ.
- Giữ chỉ số mục tiêu và phép chưa hoàn tất qua `BATTLE_WAIT`, chờ hai giây giữa các lượt phục hồi. Tối đa ba lượt liên tiếp không tiến triển; số lượt được đặt lại khi xác nhận đã dùng phép.
- Phục hồi trước khi rút theo số sao; giới hạn thời gian trận vẫn được ưu tiên. Khi phục hồi, dùng lại cơ chế chặn input và chọn lại ô phép sau bonus của trạng thái tấn công. Kết quả, về làng hoặc reload hủy các phép đang chờ.
- Log lần xác nhận thất bại ghi số trước/sau và ảnh ô phép trong `diagnostics/spell_failures/`.

## Kiểm tra

- Toàn bộ bộ kiểm thử: 206 test đạt trong 49,205 giây.
- Sau đó bổ sung thêm trường hợp nhiều lần phục hồi có tiến triển liên tiếp: cả 18 test trong `test_spell_regressions.py` đạt, gồm test mới này.
- `python tools/check_assets.py`: đạt.
- `python -m compileall -q cocmagic tests`: đạt.

Các trường hợp mới bao gồm ảnh video thật x5/x4/x3, ba ảnh không đọc được sau Rage thứ hai, lần thả bị từ chối, ba Rage còn lại phục hồi khi chờ trận, Freeze được thả trong lúc Rage còn chờ, OCR luôn không rõ, số tăng hoặc nhấp nháy, giới hạn thử lại, bonus giữa lúc phục hồi, mất kết nối, trận kết thúc và timeout.

Chưa chạy trận thật sau bản sửa. Đóng hẳn CocMagic rồi mở lại để nạp mã mới; Stop/Start trong cửa sổ cũ vẫn giữ module Python đã nạp.

## Bổ sung sau log chạy thật 09:54–09:56

Log mới ghi các lần xác nhận `[4, None, None, None]`, `[3, None, None, None]` và `[5, None, None, None]`. Ảnh ADB trong `diagnostics/spell_failures/` xác nhận game đã giảm số phép thành x3, x2 hoặc x4.

Nguyên nhân OCR đã xác định: sau khi bộ đọc xóa các cột viền trắng cao của ô đang chọn, góc cong của viền còn thành một mảnh trắng nhỏ ở bên phải số. Bộ đọc coi mảnh này là chữ số bị thiếu và trả về `None`, dù chữ số thật đã được nhận dạng đúng.

Đã sửa `_count_glyphs()` trong `cocmagic/troop_vision.py`: ghi nhớ vị trí các cột viền và chỉ bỏ mảnh nhỏ sát mép trên, tiếp giáp ngay với viền dọc đã xác định. Chữ số bị thiếu không có bằng chứng thuộc viền vẫn làm kết quả không chắc chắn, giữ việc bảo vệ x10 khỏi bị đọc thành x0.

Bảy ảnh ô phép ADB nguyên gốc được lưu thành fixture `rage_native_*.png`. Sáu test mới kiểm tra x5/x4/x3/x2, xác nhận giảm bằng một ảnh mới, đổi viền chọn khi số giữ nguyên, chuỗi ba Rage còn lại, chữ số đầu bị thiếu và mảnh trắng không thuộc viền. Test chuỗi dùng ảnh ADB x3/x2 thật và font trong dự án để tạo x1/x0.

Đọc lại toàn bộ 24 ảnh của sáu thư mục lỗi đã có: tất cả đều trả về số đúng, các cặp trước/sau là 4→3, 3→2 hoặc 5→4. Sáu test mới và kiểm tra cú pháp đều đạt. Kết quả này xác nhận trên ảnh ADB của trận thật; chưa chạy một trận mới sau sửa OCR.

Chạy lại bộ kiểm thử toàn bộ sau sửa OCR: 213 test đạt trong 51,239 giây, exit code 0. Log tại `diagnostics/rage-20261007/native-full-test-results.txt`.
