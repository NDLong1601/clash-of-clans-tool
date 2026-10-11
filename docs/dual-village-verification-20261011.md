# Kiểm thử, sửa lỗi live và dọn source — 11/10/2026

Nhánh bàn giao: `codex/source-update`. Đợt này tiếp nối [sửa F1–F4](dual-village-review-fixes-20261011.md), kiểm thử lại toàn bộ GĐ0–GĐ8 và các thay đổi phát hiện trên game thật. **519 test đạt; chưa nghiệm thu toàn bộ chuỗi hybrid nhận thưởng sao.**

## Kết quả trên bản source cuối

Windows, Python 3.13.7. Các lệnh chạy trong workspace, sau khi chốt toàn bộ thay đổi Python, template và fixture:

| Kiểm tra | Kết quả |
|---|---|
| `python -m unittest discover -s tests -q` | **519 test / 362.975s / OK / exit 0**, không failure, error hoặc skip. Thời gian process gồm khởi động/thoát: 366.123s. |
| `python -m ruff check cocmagic tools tests` | Tất cả kiểm tra đạt, exit 0. |
| `python -m compileall -q cocmagic tools tests` | Exit 0. |
| `python tools/check_assets.py` | Import và asset checks đạt, exit 0. |
| `python tools/check_dual_village_evidence.py` | 9 manifest, 166 file công bố, 169 nguồn/receipt/log riêng được đối chiếu; 0 nguồn thiếu trên máy này, 0 lỗi. |
| `python main.py --help` | Exit 0; có `main`, `builder`, `hybrid`. |
| Checkout tạo từ Git index, không có settings/license/diagnostics của máy | Import/asset, evidence và CLI đều exit 0. Nguồn riêng thiếu trong checkout được báo riêng, không biến thành bằng chứng live. |

SHA-256 source trước/sau sáu gate giống nhau. Sau full suite chỉ cập nhật Markdown để ghi kết quả; không sửa lại code/template/fixture rồi dùng kết quả test cũ. Các dòng log lỗi trong ca giả lập disconnect, input failure và watchdog là đầu vào kiểm thử, không phải test thất bại.

Log và receipt đầy đủ nằm riêng trong `diagnostics/verification_20261011/`: `checks.json`, `unittest.log`, `tested-source.json`, `evidence-audit.json`, `clean-checkout-final.json`, `final-audit.json`. Bộ 509 test trước khi sửa các lỗi live được giữ trong `unittest-before-live-fixes.log`; không dùng số liệu đó để nghiệm thu bản cuối.

## Lỗi phát hiện trên game thật và cách sửa

| Vấn đề | Thay đổi và kiểm chứng |
|---|---|
| Artwork trên nút Attack thay đổi làm Home thành UNKNOWN | Bổ sung crop chữ `Attack!` thật. Chỉ chấp nhận cùng chân dung thợ phân biệt làng và HUD Home; modal vẫn có ưu tiên. Main dùng cùng guard để phục hồi/tap Attack. Test có Home mới, làng sai và modal. |
| Sao native `0/8` không khớp artwork lấy từ video | Bổ sung template sao native trong đúng ROI. `0/8` là AVAILABLE; OCR không đọc được vẫn không biến thành COMPLETE. Các yêu cầu hai ảnh mới, camera ổn định và không che được giữ nguyên; fixture che trả UNKNOWN. |
| Tướng đã thả đang nạp kỹ năng bị đọc là chưa thả khi cạnh thanh máu chỉ lộ một phần | Cho phép cạnh ngắn hơn, vẫn yêu cầu hai cạnh thanh máu và dấu hiệu màu. Fixture native xác nhận DEPLOYED/CHARGING, không coi là một tướng mới để thả lại. |
| Camp đã chọn nhưng chưa thả bị tap lại làm hủy chọn | `BuilderSlot.selected` nhận diện bằng kích thước/vị trí card, không dựa vào màu header. Retry bỏ tap chọn khi camp vẫn đang chọn; điểm bản đồ vẫn cần ảnh mới và receipt deployment. Có ca camp đầu và camp thứ năm khác màu. |
| Plan dò footprint trước chọn quân chưa sử dụng biên cấm vừa xuất hiện | Sau chọn quân, dựng lại plan từ ảnh mới nếu plan cũ là footprint; kiểm revision/motion trước input. Test buộc dùng ảnh sau chọn và điểm mới; không giữ điểm cũ khi view bị vô hiệu hóa. |

Ảnh regression công bố được biến đổi từ ADB native, giữ ROI cần kiểm tra và loại tên/số dư. Manifest ghi parent/hash/phép biến đổi. Đây là fixture để kiểm code, không thay cho receipt chạy trọn chuỗi game thật.

## Kết quả live và giới hạn

Thiết bị thử là một MuMu Android 15, English, ảnh ADB 1600×900. `emulator-5556` và `127.0.0.1:16416` là hai alias của cùng VM; không tính thành hai game độc lập. Probe dùng engine/module/reader/ADB thật, không giả thưởng sao; tắt auto-train main, nâng tường và event. Không đổi giờ Windows hoặc cấu hình người dùng.

- Các lượt đầu ghi nhận lỗi chuyển làng/nhận diện Home, rồi lỗi chọn camp/tướng; được giữ như bằng chứng thất bại trước sửa, không xóa hoặc gán lại PASS.
- `live-builder-final/receipt.json`: probe quanh biên exit 0, 240.452s, xử lý result kế thừa rồi một trận mới, thu xe và trở lại Home; receipt xác nhận counter/bar đổi và Collect disabled. Metrics `battle_count=2` gồm result cũ, không phải hai trận mới. Phiên này còn một camp chưa thả trước bản sửa nhận diện camp thứ năm; **không gọi là PASS thả đủ toàn quân**.
- `live-hybrid-final.log` trên bản sửa cuối: khu một ghi 6 deployment, sau khu hai tổng 11, chuyển result rồi Home, không ghi rejected point hoặc unconfirmed ability trong các sự kiện đã lưu. Tuy nhiên **không có receipt kết thúc phiên**; chỉ dùng để xác nhận các bước đã quan sát, không công bố hoàn thành hybrid hoặc nghiệm thu around dưới tải mục tiêu.
- Khi `live-hybrid-native` đang sở hữu VM, worker thử qua alias `emulator-5556` bị chặn trước input bằng khóa production; `live-alias-lock.json` ghi `alias_worker_blocked=true`, `input_sent=false`.

Đã có bằng chứng native AVAILABLE và thu xe có tiền. Vẫn thiếu chuỗi AVAILABLE → nhiều trận → CLAIMABLE → nhận thưởng/lượt tiếp → COMPLETE → về main; tướng thật vắng/nâng cấp, kỹ năng Copter tự động, hai VM độc lập và các nhánh main/camera/recovery chưa phủ trong [ma trận GĐ8](dual-village-validation.md). Test offline không thay những ca live này. Camera tiếp tục mặc định tắt và giữ lựa chọn đã lưu.

## Dọn source và cách chạy lại

Bỏ import/biến thừa, chuẩn hóa định dạng các file Python mới và thêm cấu hình Ruff giới hạn ở lỗi cú pháp/tên/import. `requirements-dev.txt` tách Ruff khỏi dependency chạy bot; không thêm package lint vào runtime. `tools/check_assets.py` kiểm import bằng `import_module`, giữ asset gate hiện có.

Các probe gửi input dùng helper `tools/live_probe_support.py` để lấy cùng khóa VM với engine, kể cả alias. Acquire bị từ chối không được release touch của chủ đang chạy; exception hoặc lỗi release vẫn đóng lease. Ba regression riêng kiểm các trường hợp này. Probe chỉ quan sát dùng chế độ không acquire input.

`.ruff_cache/`, diagnostics và archive `CocMagic_Release.zip` nằm ngoài Git. Archive gốc được giữ nguyên. Đối chiếu SHA-256 xác nhận bốn file `settings.json`, `instances.json`, `license-config.json`, `license-key.bin` của người dùng không đổi; không đưa các file này vào commit. Các file code, template, fixture có provenance và tài liệu triển khai được giữ trong source.

```powershell
python -m pip install -r requirements-dev.txt
python -m ruff check cocmagic tools tests
python -m unittest discover -s tests -q
python tools/check_assets.py
python tools/check_dual_village_evidence.py
```

Trước push kiểm tra whitespace, liên kết Markdown nội bộ, file ngoài phạm vi và mẫu credential trong phần staged. Không coi push source là công bố bản phát hành đã nghiệm thu toàn bộ game thật.
