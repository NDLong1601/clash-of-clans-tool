# Builder farming — GĐ5

Profile nhận diện hiện tại: **English, Android 1600×900**, MuMu Android 15. Video train chỉ dùng để đối chiếu trình tự chọn quân, kỹ năng và hai khu. Mọi điểm bản đồ xuất phát từ ảnh ADB hiện tại; crop trong manifest là dữ liệu nhận diện, không phải tọa độ thả cố định.

## Cấu hình

Trong tab Run chọn **Làng đêm → Bắt đầu**, hoặc chạy `python main.py --run-mode builder --port 16416`. Cả builder và hybrid đã mở cho profile trên; xem [nghiệm thu GĐ8](dual-village-validation.md) để biết nhánh live còn thiếu. Tab Làng đêm chọn:

- `around`: chia các ô qua nhiều cạnh nhìn thấy, mỗi lần thả có receipt.
- `single_point`: xác nhận một điểm bằng lần thả đầu tiên rồi dùng điểm đó cho các ô tiếp theo. Điểm bị từ chối hoặc camera đổi sẽ bị bỏ; tìm lại có giới hạn.
- `builder_auto_setup_baby_dragons=true`: đọc Choose Army, chỉ xóa ô sai đã nhận diện, bổ sung Rồng con, đọc lại sau mỗi thay đổi. Kiểm tra dấu hoàn tất của cả Starting và Reinforcements. Không đụng placeholder khóa. Sau đó đọc lại đội hình chính tại menu mỗi trận; giữ đúng thì không mở Choose Army, đổi thì quay về sửa. Reload bỏ cache xác nhận.
- `builder_use_available_hero=true`: đọc Battle Machine/Battle Copter và tình trạng thực tế; không chờ tướng vắng/không khả dụng. Tắt để train bằng quân.
- `builder_collect_cart=true`: xử lý xe sau kết quả, đối soát thu và đóng về Home. Collect bị khóa được ghi `unavailable=true`, không bấm/chờ vô hạn, không gọi xe trống hay đã thu nếu không có bằng chứng. Ví dụ kho đầy có thể còn tiền trong xe. Lỗi mở/đóng/receipt thu vẫn chặn nhường an toàn.

Các tham số nâng cao trong JSON, độc lập timeout main:

| Key | Mặc định | Ý nghĩa |
|---|---:|---|
| `builder_prepare_timeout` | 75 giây | Chuẩn bị/tìm trận/nhận diện ban đầu |
| `builder_battle_timeout` | 540 giây | Giới hạn toàn trận |
| `builder_transition_timeout` | 35 giây | Thanh quân/chuyển khu chưa rõ |
| `builder_no_progress_timeout` | 90 giây | Watchdog quân, damage và timer đều không đổi |
| `builder_point_retries` | 4 | Số điểm thử tối đa mỗi ô |
| `builder_baby_ability_delay` | 1 giây | Tính từ receipt triển khai của từng ô; vẫn cần READY thật |
| `builder_hero_ability_interval` | 8 giây | Khoảng cách tối thiểu, không tự biến cooldown thành READY |

Camera tự chỉnh vẫn mặc định tắt. Navigation tìm thuyền/xe dùng camera GĐ3 có kiểm chứng riêng. Bật `camera_auto_adjust` cho phép zoom trong trận khi chưa chọn quân, rồi lập lại điểm; tình trạng selection hoặc hình học chưa rõ sẽ chặn input.

Delay Rồng con 1 giây là thời gian tối thiểu sau receipt thả; capture/nhận diện có thể làm thời điểm tap muộn hơn. Module ưu tiên kỹ năng READY của từng ô trước ô triển khai tiếp. Giá trị này đã dùng trong các phiên around-14 (13 receipt kỹ năng) và single-6 (14 receipt), giữ ledger qua hai khu. Có thể tăng delay qua JSON; không suy READY chỉ từ thời gian.

## Hợp đồng và vòng đời

`BuilderFarmModule` thực thi contract GĐ2, chạy đồng bộ dưới input lock của coordinator. Vòng đời là phân loại → Home/hậu xử lý → chuẩn bị → tìm trận → quét thanh quân → camera/triển khai/kỹ năng → chuyển khu hoặc result → Home/thưởng/xe. Builder-only tiếp tục khi thưởng COMPLETE.

`can_yield` chỉ đúng sau hậu xử lý và hai ảnh Home mới ổn định, bằng chứng còn mới, ngoài tick/input/modal. Metrics gồm số lần tìm trận, kết quả, khu, triển khai, receipt kỹ năng quân/tướng, thưởng, xe, điểm từ chối và recovery. Coordinator cung cấp `builder_bonus_state`, `builder_stage`, `builder_can_yield` để GĐ6 quyết định lịch; GĐ5 chưa chạy hybrid.

Thanh quân được tìm lại từ ảnh mỗi trận và mỗi khu. Camp ID đọc từ nhãn số, không suy từ vị trí x0 hay depleted của main. Menu đọc được `x1`; trong trận không có số lượng đáng tin thì `count=None`. Tướng tìm lại trên toàn thanh cả khi lớp sáng cooldown che đường viền. Một lần tap chỉ được tính thành công khi trạng thái sau khác theo đúng receipt; UNKNOWN không thành công. Quân chết ngay sau tap kỹ năng được ghi `unconfirmed_abilities` và cảnh báo, không tăng số kỹ năng thành công và không bấm lại.

Khu hai cần HUD chuẩn bị xuất hiện lại được xác nhận sau giao tranh. 100% không phải tín hiệu result. Result cần title Total Damage và Return Home; Return/Find Now không bị bấm lặp khi màn cũ còn hiện. Ledger kỹ năng một lần theo camp giữ qua khu hai; restart bỏ ledger cũ và đọc trạng thái hiện tại, không phục hồi giả kỹ năng.

Stop chặn input kế tiếp; reload/popup đổi generation và hủy tọa độ/chuỗi cũ. Reload đọc lại từ đầu, bỏ cache setup/trận. Popup thường giữ ledger kỹ năng đã dùng nhưng bỏ bản đồ. Ảnh lạ, troop chưa mở/không nhận diện, quá số retry hoặc không có receipt sẽ dừng riêng instance với lý do.

## Kiểm chứng

Chi tiết kết quả từng phiên và giới hạn nghiệm thu nằm trong [progress](dual-village-progress.md). Fixture trong `tests/fixtures/dual_village/builder/manifest.json` ghi nguồn native, hash và biến đổi che tên; không gọi fixture biến đổi là live. Assets trong `assets/dual_village/builder/manifest.json` ghi từng crop native và parent hash.

Probe chạy module thật, không thay vision/input bằng mock:

```powershell
$env:PYTHONIOENCODING='utf-8'
python tools/builder_farm_probe.py --serial 127.0.0.1:16416 --mode around --new-battles 2 --seconds 960 --output diagnostics/dual_village_gd5/probe-around
python tools/builder_farm_probe.py --serial 127.0.0.1:16416 --mode single_point --no-hero --new-battles 2 --seconds 960 --output diagnostics/dual_village_gd5/probe-single
```

Chỉ chạy một controller trên mỗi serial. Không chạy probe cùng worker GUI/CLI. Receipt ghi ảnh, input, gesture, metrics, lỗi và Home cuối. `--new-battles` chỉ đếm kết quả sau Find của probe; `battle_count` vẫn gồm kết quả được khôi phục lúc khởi động. Probe chỉ hoàn tất khi đã hậu xử lý và xác nhận Home. `--stop-after-inputs N` hoặc `--stop-file PATH` dùng kiểm tra hủy input; receipt phân biệt completed/cancelled/budget_exhausted.

Chưa suy rộng profile này sang ngôn ngữ/độ phân giải khác. Camp 8, loại quân mới, tướng vắng/đang nâng cấp thật, kỹ năng Copter tự động, chuỗi thưởng sao và thu một phần mà Collect còn enabled cần native bổ sung. Đã quan sát Collect bị khóa dù xe còn tiền khi kho đầy; handler chỉ xác nhận nút không khả dụng và Home, chưa suy nguyên nhân từ thanh kho. Khi thiếu mẫu, module giữ UNKNOWN/báo lỗi hữu hạn.
