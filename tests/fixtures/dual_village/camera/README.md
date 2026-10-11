# Fixture camera GĐ3

Đọc `manifest.json` và `docs/dual-village-camera.md`. Nguồn thật là ảnh ADB 1600×900 trên `127.0.0.1:16416`, MuMu Android 15; frame gốc nằm trong diagnostics, không phải video.

- `pan-*.jpg`, `zoom-*.jpg`: giữ kích thước native, che resource HUD `[1300,0,1600,195)`, JPEG quality 94. Matcher vốn loại vùng này. Đây là ảnh biến đổi, không phải native nguyên bản.
- `selected-*.png`, `drop-*.png`: crop lossless thanh quân `[0,735,1600,900)`; nguồn Practice thật. Khi ghép vào canvas trong test, canvas đó là synthetic composite, không phải ảnh chụp game mới.
- `connection-modal-crop.png`: crop native `[330,280,1230,580)` từ popup thiết bị khác. Chỉ dùng để kiểm tra camera từ chối modal, không làm tín hiệu tự reload.
- `test_camera_controller.py` cũng tạo biến thể chỉ đổi HUD bằng noise seed 42. Biến thể đó không chứng minh gesture thật.

Manifest có nguồn, serial, resolution, parent hash, output hash và phép biến đổi. Nhãn `transformed_test` áp dụng cho mọi file đã xuất; thông tin live là nguồn parent và log gesture. 10→9→7 chứng minh một probe hợp lệ rồi batch hai quân; 5→5 trong cặp selected drag chỉ chứng minh một card/Practice. Các ảnh không nghiệm thu multiplayer end-to-end, builder hoặc hai giả lập đồng thời.
