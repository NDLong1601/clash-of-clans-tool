# Kế hoạch triển khai CocMagic: Làng chính, Làng đêm và chế độ kết hợp

Ngày lập: 08/10/2026, giờ Việt Nam (UTC+7).

Trạng thái: tài liệu thiết kế; các giai đoạn dưới đây chưa được triển khai hoặc nghiệm thu bởi tài liệu này.

Workspace: C:\Users\PC\Documents\CocMagic.

File prompt đi kèm: [dual-village-prompts.md](dual-village-prompts.md). File này chứa một prompt riêng cho mỗi giai đoạn GĐ0–GĐ8.

## 1. Yêu cầu đã chốt

### Giao diện

- Giữ mô hình nhiều giả lập, mỗi giả lập có cấu hình và tiến trình riêng.
- Trong từng giả lập có ba tab con: Làng chính, Làng đêm, Run.
- Tab Làng chính chứa cấu hình train hiện có.
- Tab Làng đêm chứa cấu hình Rồng con, cách thả, tướng, kỹ năng và thu tài nguyên.
- Tab Run chọn một trong ba chế độ: Làng chính; Làng đêm; Làng chính + Làng đêm. Đây là ba lựa chọn loại trừ nhau.
- Run chứa Bắt đầu/Dừng, trạng thái, lý do chuyển làng, thống kê và log. Chạy tất cả/Dừng tất cả ở cấp ứng dụng tiếp tục hoạt động.

### Hành vi của ba chế độ

| Chế độ | Hành vi |
|---|---|
| Làng chính | Chạy luồng làng chính hiện có; nếu bắt đầu ở làng đêm thì chuyển đúng về làng chính. |
| Làng đêm | Train làng đêm liên tục, gồm nhận thưởng và thu xe; không kết thúc chế độ chỉ vì đã hết thưởng sao. |
| Làng chính + Làng đêm | Lúc khởi động kiểm tra làng đêm. Còn thưởng thì làm làng đêm trước; hết thưởng thì về làng chính. Sau đó kiểm tra theo lịch 15:30 giờ Việt Nam. |

### Thưởng sao và chế độ kết hợp

- Người dùng đã xác nhận: còn sao trên nút Tấn công/Tìm trận nghĩa là còn thưởng sao chưa hoàn thành; không còn sao nghĩa là đã hoàn thành.
- Xử lý bảng nhận thưởng nếu xuất hiện, chờ bảng/hiệu ứng kết thúc rồi đọc lại vùng sao. Nếu còn lượt thưởng tiếp theo thì tiếp tục train làng đêm.
- Đọc tiến độ x/y nếu có thể để hiển thị; không cố định y bằng 7, 8 hoặc một giá trị khác.
- Không coi ảnh lỗi, ảnh chuyển cảnh, bảng che nút hoặc nhận diện thất bại là “không còn sao”.
- Người dùng mô tả mốc reset là 13:00; yêu cầu vận hành của bot là kiểm tra từ 15:30. 13:00 không phải tín hiệu tự gán đã có/đã hết thưởng. Quyết định train dựa trên màn hình thật.
- Lúc khởi động luôn kiểm tra, kể cả trước 15:30. Nếu kiểm tra hợp lệ sau 15:30 thì lần này đồng thời thỏa lịch ngày đó.
- Đến hạn trong trận: ghi nhận yêu cầu chờ, hoàn tất trận và thao tác đang dang dở, sau đó mới chuyển làng.
- Hoàn thành làng đêm trong chế độ kết hợp nghĩa là hoàn thành chuỗi thưởng đang khả dụng, không phải chỉ đánh xong một trận.
- Trước khi về làng chính, kiểm tra xe Tiên dược/tài nguyên và nhận phần đang thu được. Không chờ vô hạn các lượt phòng thủ còn đang diễn ra.

### Train làng đêm

- Combo Rồng con, bao gồm các ô tiếp viện khả dụng.
- Hai chiến thuật: thả xung quanh; thả toàn bộ tại một điểm hợp lệ.
- Tướng là tùy tình trạng thực tế. Có tướng sẵn sàng thì dùng; không có/đang nâng cấp thì vẫn train. Trạng thái tướng không rõ phải được kiểm tra lại, không giả định đã triển khai.
- Nhận diện từng ô quân, số lượng nếu có, đã thả/chưa thả, kỹ năng, chết/không khả dụng.
- Hỗ trợ trận một khu và hai khu. 100% khu một không tự động có nghĩa là trận đã kết thúc.
- Khi sang khu hai: đọc lại quân sống, tiếp viện, tướng và kỹ năng; bỏ tọa độ bản đồ khu trước.

### Camera

- Dùng zoom/drag để tìm thuyền, đưa các cạnh căn cứ vào vùng nhìn thấy và xử lý cạnh dưới bị thanh quân che.
- Mọi thao tác camera phải được xác nhận bằng ảnh mới; sau thay đổi camera phải bỏ/tính lại các tọa độ bản đồ cũ.
- Ưu tiên điều khiển theo thiết bị để chạy nhiều giả lập. Ctrl + cuộn trên cửa sổ giả lập là phương án cần khảo sát, không phải API ADB đã được chứng minh.

## 2. Nguồn và hiện trạng đã kiểm tra

### Video

1. C:\Users\PC\Downloads\1791438698091_2054695061538342203_7446498411049790191.mp4
   - Khoảng 3 phút 11 giây; 1556×720; giao diện tiếng Việt.
   - Có đội Rồng con, trận một khu, chuyển khu hai khoảng 02:27–02:30, nhận thưởng sao và thu xe cuối video.
2. C:\Users\PC\Documents\Bandicam\bandicam 2026-10-08 15-43-48-146.mp4
   - Khoảng 21 giây; 1064×640, có khung cửa sổ giả lập.
   - Thể hiện zoom/drag và tìm thuyền ở màn làng. Chưa chứng minh hành vi drag khi đang chọn quân trong trận.

Video dùng để hiểu luồng và xây fixture phù hợp. Ảnh ADB thực tế của bot là 1600×900; không lấy tọa độ/crop từ cửa sổ video để bấm trực tiếp lên Android. Trích frame bằng timestamp đã kiểm tra; nếu seek có sai lệch, giải mã tuần tự bằng FFmpeg.

### Mã hiện tại

| Thành phần | Điểm cần lưu ý |
|---|---|
| cocmagic/gui.py | InstanceTab đang chứa chung mọi cấu hình; build_settings suy ra event_mode từ việc tắt nâng tường. Cần giới hạn quy tắc này trong làng chính. |
| cocmagic/config.py | DEFAULT_SETTINGS, load/save đang dùng dictionary phẳng và merge nông. |
| cocmagic/instance_store.py | Lưu nhiều giả lập, định dạng ngoài version=1; copy/merge nông. |
| cocmagic/bot_engine.py | Gắn trực tiếp với FarmModule, FarmState.HOME, nâng tường và phục hồi về HOME. |
| cocmagic/modules/farm_module.py | Luồng riêng làng chính, Quick Train lúc khởi động, cache combo, điểm thả, spell và hero. |
| cocmagic/adb_controller.py | Có tap, tap_many, swipe, screenshot theo serial; chưa có pinch đa điểm. |
| cocmagic/battle_planner.py | Có hình thoi dự phòng theo tọa độ cố định; không còn hợp lệ sau camera đổi nếu chưa hiệu chỉnh. |
| cocmagic/modules/hero_module.py | Danh sách hero làng chính; không dùng nguyên bộ này cho tướng làng đêm. |
| cocmagic/session_manager.py, bot_worker.py | Mỗi giả lập một process, có event/status và stop_event; tiếp tục dùng. |

Tài liệu đối chiếu cơ chế: [Builder Battles](https://support.supercell.com/clash-of-clans/en/articles/builder-base-versus-battles-3.html), [Android multi-touch](https://developer.android.com/develop/ui/views/touch-and-input/gestures/multi). Kiểm chứng lại nếu hành vi trên game/giả lập thực tế khác mô tả.

## 3. Thiết kế và hợp đồng chung

### Cấu hình

Ưu tiên giữ dictionary phẳng trong lần mở rộng này để tương thích code hiện tại. Giữ các key làng chính cũ; thêm nhóm có tiền tố builder_, hybrid_, camera_ và key run_mode. Không lồng dictionary mới rồi tiếp tục dùng copy/merge nông mà không xử lý chia sẻ dữ liệu.

Định hướng cấu hình, cần triển khai validation thống nhất cho GUI và CLI:

    {
      "settings_schema_version": 2,
      "run_mode": "main",
      "builder_deploy_mode": "around",
      "builder_auto_setup_baby_dragons": true,
      "builder_use_available_hero": true,
      "builder_collect_cart": true,
      "hybrid_check_time": "15:30",
      "hybrid_timezone": "Asia/Ho_Chi_Minh",
      "camera_auto_adjust": false
    }

- run_mode: main | builder | hybrid. builder_deploy_mode: around | single_point.
- camera_auto_adjust=false là mặc định trong các giai đoạn đang phát triển. Quyết định bật mặc định chỉ sau nghiệm thu GĐ8; không ghi đè lựa chọn người dùng đã lưu.
- Cấu hình cũ thiếu key mới được hiểu là main. Migration lặp lại không làm mất/đổi giá trị cũ và giữ key chưa biết.
- settings_schema_version là phiên bản settings; không tự đổi wrapper version=1 của instances.json nếu không có migration tương ứng.
- Khi lưu từ một tab, giữ nguyên cấu hình của hai tab còn lại. Bắt đầu kiểm tra/lưu các trường áp dụng cho chế độ đã chọn; hybrid cần hợp lệ cả hai làng. Không để trường ẩn của làng không dùng chặn chạy vô lý.
- Trong khi bot chạy, xem được các tab nhưng khóa chỉnh cấu hình của phiên hiện tại; không hỗ trợ đổi chế độ giữa trận trong phạm vi này.
- Các chế độ chưa đủ thành phần phải được báo chưa khả dụng trong giai đoạn trung gian; engine/CLI cũng phải chặn rõ, không lặng lẽ chạy main thay builder.

### Module và điều phối

Tên file dưới đây là định hướng; có thể điều chỉnh để phù hợp mã thật nếu ghi lại trong báo cáo:

- Module làng chính hiện tại và BuilderFarmModule mới có cùng hợp đồng tick, status, halt_reason, reset/recover và khả năng nhường điều khiển.
- RunCoordinator quyết định làng cần hoạt động; chỉ một module được gửi input tại một thời điểm trên một serial.
- VillageNavigator xác nhận làng, chuyển làng bằng thuyền và phục hồi khi camera lệch.
- CameraController quản lý pan/zoom, chờ ổn định và camera_revision.
- BuilderScreenReader/StarBonusReader phân loại màn hình, thanh quân và thưởng sao.
- BuilderRewards xử lý bảng thưởng và xe tài nguyên.
- RuntimeStore lưu tiến độ lịch theo giả lập, độc lập với cấu hình người dùng.

Điểm nhường điều khiển phải là HOME đã xác nhận, không có modal, không đang train/thu/nâng tường/xác nhận mua, không có input batch hoặc thao tác cần đối soát. Coordinator kiểm tra yêu cầu chuyển trước khi module bắt đầu trận mới. Không suy ra điểm nhường chỉ từ tên enum HOME.

Chuyển làng xóa cache màn hình và tọa độ có liên quan. Giữ thống kê phiên và cờ thiết lập đội hình hợp lệ; không vô tình chạy lại Quick Train làng chính ở mọi lần đổi làng.

### Thưởng sao

StarBonusObservation nên có trạng thái AVAILABLE, CLAIMABLE, COMPLETE, UNKNOWN; kèm thời điểm, lý do, vùng quan sát và tiến độ tùy chọn. Nhận diện làng đêm và nút Attack phải hợp lệ trước khi kết luận không có sao.

- AVAILABLE: thấy sao/tiến độ thưởng; x=0 vẫn có thể là còn nhiệm vụ.
- CLAIMABLE: bảng thưởng cần xử lý; xử lý xong phải quan sát lại, không tự gán COMPLETE.
- COMPLETE: nút và vùng sao nhìn rõ, không có sao qua ít nhất hai ảnh mới ổn định.
- UNKNOWN: ảnh không dùng được, chuyển cảnh, che khuất, nhận diện mâu thuẫn. Chờ và thử lại có giới hạn; không ghi hoàn thành lịch.

OCR x/y chỉ bổ trợ. Các số 0/7, 4/8 và ngưỡng khác phải được chấp nhận nếu phù hợp ảnh; không cố định mục tiêu sao theo video.

### Lịch và lưu runtime

- Wall clock có múi giờ UTC+7 cho lịch; monotonic cho timeout, cooldown và chờ thao tác.
- Nếu dùng ZoneInfo, xử lý môi trường Windows thiếu tzdata; UTC+7 cố định là fallback hợp lệ cho yêu cầu này.
- Trạng thái dự kiến: last_valid_bonus_check_at, last_daily_check_date, last_bonus_state, pending_builder_check, next_retry_at, last_error. Không lưu tọa độ trận để tái dùng sau restart.
- Runtime có một writer cho mỗi serial, ghi atomic; có thể dùng data/runtime/<id-an-toan>.json và gitignore thư mục này. Không để các worker cùng sửa một file tổng mà gây mất cập nhật.
- Startup luôn đọc màn hình thật; runtime chỉ giúp lịch/log, không thay thế kiểm tra khởi động.
- Kiểm tra hợp lệ sau 15:30 ghi nhận lịch ngày đó. UNKNOWN không được ghi là đã kiểm tra xong/đã nhận thưởng.
- Máy ngủ qua lịch thì kiểm tra bù một lượt hiện tại; không phát lại từng ngày đã bỏ lỡ.
- Nếu train làng đêm không tiến triển hoặc nhận diện không phục hồi được, ghi rõ lỗi. Hybrid chỉ quay main nếu xác nhận chuyển được an toàn; không đánh dấu hoàn thành thưởng. Có retry giới hạn; nếu màn hình không xác định thì dừng riêng giả lập đó.

### Camera và dữ liệu ảnh

- Backend phải phân biệt pan một điểm với pinch nhiều điểm. Hai lệnh swipe độc lập không mặc nhiên là pinch hợp lệ.
- Ưu tiên backend gửi thao tác theo serial. Nếu fallback bằng cửa sổ, định danh đúng cửa sổ, quản lý focus/khóa input dùng chung và kiểm chứng không thao tác nhầm giả lập.
- Bắt đầu bằng zoom/pan có giới hạn và đo thay đổi thật từ ảnh. Nếu đã chạm giới hạn zoom, dừng gửi thêm thay vì lặp vô hạn.
- camera_revision tăng khi hình học bản đồ thay đổi; các điểm thả, vùng công trình, mục tiêu spell và vị trí trên bản đồ phải được tính lại hoặc biến đổi có xác nhận.
- HUD/thanh quân thuộc không gian màn hình; bản đồ thuộc không gian camera. Không dịch tọa độ HUD theo bản đồ.
- Không dùng hình thoi tọa độ cũ làm fallback sau pan/zoom. Nếu chưa xác định được hình học mới thì phục hồi khung nhìn chuẩn hoặc báo không lập được kế hoạch.
- Ưu tiên chỉnh camera trước khi chọn quân. Thử nghiệm riêng drag lúc đang chọn quân để phát hiện thả nhầm; mọi điều chỉnh giữa trận phải tạm dừng chuỗi triển khai và đối soát sau đó.

## 4. Các giai đoạn triển khai

Trình tự: GĐ0 → GĐ1 → GĐ2 → GĐ3 → GĐ4 → GĐ5 → GĐ6 → GĐ7 → GĐ8. Không tuyên bố giai đoạn hoàn thành nếu tiêu chí quan trọng chỉ mới có mock hoặc chưa chạy được trên thiết bị trong giai đoạn yêu cầu thử thật.

### GĐ0 — Khảo sát, baseline và dữ liệu kiểm chứng

Mục tiêu: xác định trạng thái thật của repo, môi trường giả lập và bộ ảnh cần cho tính năng.

Công việc:
- Đọc hướng dẫn repo, git status, các file liên quan; ghi nhận thay đổi người dùng trước khi làm.
- Chạy bộ test baseline và công cụ kiểm tra asset, phân loại lỗi tồn tại sẵn.
- Đối chiếu hai video, lưu danh mục timestamp và trạng thái thay vì lấy tọa độ video làm tọa độ ADB.
- Nếu có thiết bị kết nối, đọc danh sách serial/kích thước ảnh và chụp ảnh ADB không thay đổi trạng thái game.
- Lập fixture manifest cho main/builder home; sao còn/hết; bảng thưởng; xe có tiền/trống/đang phòng thủ; thanh quân có/không tướng; hai khu; camera zoom/pan.
- Khảo sát khả năng backend zoom, ghi rõ phần nào mới là phương án và phần nào đã chứng minh.

Đầu ra: docs/dual-village-baseline.md, manifest và fixture có nguồn gốc/kích thước rõ ràng; danh sách thiếu dữ liệu.

Nghiệm thu: baseline có kết quả thật, không gọi fixture tự dựng là ảnh game thực tế; xác định được giới hạn của mẫu video và các trường hợp cần lấy ảnh thêm.

### GĐ1 — Cấu hình tương thích và ba tab

Phụ thuộc: GĐ0. File chính: config.py, instance_store.py, gui.py, main.py; có thể thêm helper validation.

Công việc:
- Thêm defaults/schema/normalization và migration lặp an toàn; giữ nguyên key làng chính và định dạng instance hợp lệ.
- Tách UI thành ba tab trong mỗi giả lập; chuyển nút chạy/dừng/log sang Run; không sao chép widget gây hai nguồn dữ liệu.
- Hiện ba chế độ với lựa chọn main mặc định; lưu riêng theo serial.
- Tách quy tắc nâng tường/sự kiện khỏi lựa chọn làng; sửa validation đúng phạm vi.
- Giữ hành vi khóa cấu hình khi chạy, license và Chạy tất cả/Dừng tất cả.
- Thêm khả năng engine/CLI báo chế độ chưa triển khai trong giai đoạn trung gian.

Đầu ra: UI dùng được cho main, settings mới lưu/đọc lại được và chỗ hiển thị builder/hybrid rõ tình trạng.

Nghiệm thu: cấu hình cũ mở được; đổi tab/lưu không mất dữ liệu; hai giả lập không dùng chung giá trị mutable; main vẫn khởi động/dừng được. Kiểm tra giao diện trực quan và kiểm thử hành vi lưu/validation, không snapshot từng chi tiết trang trí.

### GĐ2 — Hợp đồng module, điểm nhường và phục hồi

Phụ thuộc: GĐ1. File chính: bot_engine.py, farm_module.py, bot_worker.py, session_manager.py; thêm contract/coordinator nếu cần.

Công việc:
- Đưa phụ thuộc trực tiếp FarmState.HOME thành hợp đồng trạng thái đủ rõ cho hai module.
- Xây điểm nhường được kiểm chứng trước trận mới và sau hoàn tất hậu xử lý.
- Giữ đúng thứ tự nâng tường, Quick Train ban đầu, event rewards, spell recovery, hero và các batch input hiện có.
- Routing status/halt/reload theo module đang hoạt động; reconnect không tự coi màn hình là main HOME.
- Chờ có thể dừng được, không tạo hai vòng tick gửi input đồng thời.

Đầu ra: engine có thể điều phối module qua hợp đồng chung; main chạy qua hợp đồng này; fake builder dùng trong test, không trình bày là train thật.

Nghiệm thu: yêu cầu chuyển làng không cắt giữa trận, modal, nâng tường hay batch; cờ startup train không bị lặp khi suspend/resume; các test main liên quan vẫn qua.

### GĐ3 — Backend camera và nâng cấp điểm thả làng chính

Phụ thuộc: GĐ2. File chính: adb_controller.py, battle_planner.py, attack_tactics.py, farm_module.py; thêm camera_controller.py/backend phù hợp.

Công việc:
- Làm pan có kết quả trả về và pinch/zoom theo backend đã kiểm chứng trên MuMu.
- Xác định vùng thao tác an toàn, đo ảnh ổn định, giới hạn số lần điều chỉnh, giải phóng mọi điểm chạm/phím khi dừng hoặc lỗi.
- Tách tọa độ HUD và bản đồ; quản lý camera_revision; làm mới mọi cache bản đồ khi cần.
- Điều chỉnh hình học planner để cạnh dưới có thể được đưa lên khỏi thanh quân; xác nhận thả bằng tín hiệu thực tế trước khi thả hàng loạt.
- Tích hợp sau lọc đối thủ phù hợp và trước triển khai; không zoom mỗi base bị bỏ qua nếu không cần.
- Giữ camera_auto_adjust tắt mặc định ở giai đoạn phát triển; có phương án hoạt động rõ khi backend không hỗ trợ.

Đầu ra: backend camera, planner cập nhật, ảnh trước/sau và kết quả thử thật có serial/resolution/điều kiện.

Nghiệm thu: pan/zoom thật được xác nhận; điểm trên bản đồ cũ không bị tái dùng; HUD không bị dịch theo bản đồ; thử được cạnh dưới bị che; kiểm tra không thả quân ngoài ý muốn khi drag. Nếu không có thiết bị hoặc backend không hoạt động, báo phần chưa kiểm chứng, không đánh dấu đủ điều kiện bật mặc định.

### GĐ4 — Chuyển làng, thưởng sao và thu tài nguyên

Phụ thuộc: GĐ3. Thêm village_navigator.py, bộ nhận diện builder và handler reward/cart theo cấu trúc phù hợp.

Công việc:
- Phân loại main home, builder home, attack menu, battle, result, modal, loading và unknown bằng nhiều dấu hiệu phù hợp.
- Tìm thuyền ở nhiều mức camera; pan/zoom giới hạn; chỉ coi chuyển làng thành công sau khi xác nhận đích.
- Làm bốn trạng thái thưởng sao, xác nhận vắng sao bằng ít nhất hai ảnh mới ổn định.
- Handler bảng thưởng: bấm nút đúng, xác nhận bảng đóng, đọc lại sao; không nhầm sao thưởng với sao kết quả trận hoặc sao làng chính.
- Handler xe: tìm xe, mở, đọc trạng thái, thu phần có thể thu, đối soát thay đổi, đóng đúng màn hình.
- Không dùng nút “Okay” chung hoặc nền tối làm bằng chứng duy nhất để bấm.

Đầu ra: navigator và các handler có thể chạy riêng trong phiên kiểm chứng; fixture/test phủ cả thành công và nhận diện không rõ.

Nghiệm thu: vòng main → builder → main thành công dù camera ban đầu lệch; AVAILABLE/COMPLETE/UNKNOWN phân biệt đúng; nhận bảng thưởng xong vẫn đọc lại; xe trống không gây vòng lặp và phòng thủ đang diễn ra không chặn vô hạn.

### GĐ5 — Train làng đêm đầy đủ

Phụ thuộc: GĐ2–GĐ4. Thêm modules/builder_farm_module.py và các helper vision/hero/tactics chuyên biệt.

Công việc:
- Chu kỳ: xác nhận home → chuẩn bị combo → tìm trận → quan sát → chỉnh camera → triển khai → kỹ năng → chuyển khu hoặc kết quả → về làng → thưởng/xe.
- Đọc số ô khả dụng, thiết lập Rồng con nếu cấu hình bật và xác nhận đã chọn đúng; không chờ/đụng ô khóa và không gọi Quick Train của main.
- Quét tướng mỗi trận. Thiếu tướng không chặn train; lỗi nhận diện không làm dịch nhầm toàn bộ chỉ số ô.
- Hai kiểu thả có hành vi riêng. Một điểm phải được xác nhận hợp lệ; xung quanh chia ô theo các điểm khác nhau quanh biên nhìn thấy.
- Theo dõi vòng đời từng ô và kỹ năng; hero có chính sách sử dụng riêng, không lấy logic Warden làm mặc định.
- Khu hai quét lại trạng thái và tiếp viện, giữ đúng kỹ năng dùng một lần đã dùng; không coi 100% là kết thúc nếu đang chuyển khu.
- Timeout và đếm thời gian riêng cho chuẩn bị/trận/chuyển khu; không kế thừa timeout 85 giây của main.
- Theo dõi không tiến triển, giới hạn retry và nhận diện result rõ ràng. Hoàn tất một trận trước khi nhận lệnh nhường làng.

Đầu ra: chế độ builder độc lập chạy được; trạng thái/metrics sẵn sàng cho hybrid.

Nghiệm thu: chạy đủ hai kiểu thả; có/không có tướng; trận kết thúc khu một và trận sang khu hai; thu thưởng/xe; hết thưởng sao vẫn tiếp tục ở builder-only; Stop/reload không dùng lại dữ liệu trận cũ. Có dữ liệu thực tế cho các nhánh chính hoặc ghi rõ nhánh chưa thử.

### GĐ6 — Chế độ kết hợp và lịch 15:30

Phụ thuộc: GĐ5. File chính: coordinator/engine, runtime store, config, UI status và CLI.

Công việc:
- Startup luôn kiểm tra builder; quyết định ưu tiên theo thưởng sao, xử lý bảng claim đang mở trước.
- Khi còn sao, chạy builder đến hết lượt thưởng khả dụng; thu xe rồi mới yêu cầu về main.
- Lịch UTC+7 chạy bên trong bot, không cần cron hay automation bên ngoài; kiểm tra >= 15:30 và trạng thái đã kiểm tra.
- Hợp nhất startup check với daily check khi phù hợp, chống hai lượt chuyển làng liên tiếp vì cùng một nguyên nhân.
- Lưu runtime atomic theo serial; xử lý restart, ngủ máy, lỗi đọc file và UNKNOWN không giả thành hoàn thành.
- Nếu deadline rơi giữa trận, gửi pending request và nhường tại safe boundary; không lập tức bấm thuyền/back.
- Hiển thị lý do chuyển, kết quả kiểm tra, lịch tiếp theo, lỗi và retry.

Đầu ra: ba chế độ hoạt động đúng, hybrid có lịch và lưu tiến độ.

Nghiệm thu bằng fake clock: khởi động 09:00/15:29/15:31; 15:30 giữa trận; ngủ qua lịch; restart; qua ngày; hết sao; còn sao; bảng claim; unknown; ngày đã kiểm tra. Đọc sao hợp lệ sau 15:30 tính cho ngày đó, không lặp thêm daily check; kiểm tra trước 15:30 vẫn phải kiểm tra lại theo lịch.

### GĐ7 — Phục hồi, nhiều giả lập và hoàn thiện quan sát

Phụ thuộc: GĐ6.

Công việc:
- Mất kết nối/reload tại main, builder, chuyển khu, bảng thưởng và chuyển làng: hủy input chờ, chờ game, phân loại lại trước hành động.
- Dừng trong gesture, batch, chờ modal hoặc chờ lịch: không gửi nhóm input mới sau khi đã nhận stop; giải phóng gesture; báo trạng thái đúng.
- Bảo đảm runtime/settings/cache/status và camera không bị dùng chéo giữa các serial.
- Rà soát nhận diện popup nền tối để không nhầm làng đêm thành inactivity; chỉ route handler phù hợp trạng thái.
- Giới hạn thời gian/không tiến triển cho chuyến đi builder trong hybrid. Khi fallback main phải ghi chưa hoàn thành, không sửa dữ liệu thành COMPLETE.
- Hoàn thiện UI các tab ở cửa sổ nhỏ, cuộn, focus bàn phím, trạng thái đã lưu/chưa lưu, tiếng Việt và log gọn.
- Kiểm tra license/watchdog và Chạy tất cả/Dừng tất cả vẫn dừng đúng từng tiến trình.

Đầu ra: báo cáo recovery/multi-instance và sửa các lỗi phát hiện.

Nghiệm thu: hai giả lập chạy khác chế độ không ảnh hưởng nhau; reconnect một giả lập không reset giả lập kia; stop hoạt động trong giới hạn của thao tác ADB đang thực thi, không tuyên bố dừng tức thì nếu batch hiện tại chưa kết thúc.

### GĐ8 — Nghiệm thu tổng thể và tài liệu sử dụng

Phụ thuộc: GĐ7.

Công việc:
- Chạy bộ regression hiện có và các test mới; phân biệt lỗi có từ baseline với lỗi mới.
- Thử thực tế ma trận ở mục 5; không gọi kết quả mock là kiểm chứng game thật.
- Kiểm tra artifacts debug có thể truy ngược tới trạng thái/frame mà không cần log mọi ảnh liên tục.
- Quyết định bật camera mặc định dựa trên bằng chứng; cập nhật khả năng khả dụng builder/hybrid đúng thực tế.
- Cập nhật README, cấu hình ví dụ không chứa dữ liệu tài khoản, quy tắc lịch, migration và cách xử lý lỗi.
- Hoàn thành docs/dual-village-validation.md: ca thử, môi trường, kết quả, ảnh/log, hạn chế còn lại và cách quay về main.

Đầu ra: phiên bản có thể dùng cả ba chế độ và hướng dẫn; nếu còn nhánh chưa kiểm chứng, nêu rõ phạm vi đó thay vì công bố hoàn tất toàn bộ.

Nghiệm thu: không mất cấu hình cũ, không hồi quy main, đúng chuyển làng theo sao/lịch, không tọa độ camera cũ, chạy nhiều giả lập độc lập. Quay về main bằng run_mode=main; camera có công tắc tắt để chẩn đoán. Tắt một tính năng không được che lỗi khiến luồng được công bố không hoạt động.

## 5. Ma trận kiểm thử tối thiểu

| Nhóm | Trường hợp bắt buộc | Kết quả mong đợi |
|---|---|---|
| Config/UI | File cũ; thiếu key; key chưa biết; đổi tab; save/reload; CLI | Không mất cấu hình; default main; validation đúng chế độ |
| Cô lập | Hai serial cấu hình và runtime khác nhau | Không ghi đè hoặc dùng nhầm dữ liệu |
| Sao | 0/y, x/y, hết sao, che nút, animation, ảnh None, main home | Còn thưởng / hoàn thành / không rõ được phân loại đúng |
| Thưởng | Bảng nhận thưởng; nhận xong còn sao; nhận xong hết sao | Kiểm tra lại, không kết thúc chuỗi quá sớm |
| Xe | Có tiền; trống; phòng thủ đang chạy; lỗi đóng bảng | Thu đúng; chờ có giới hạn; về màn làng được xác nhận |
| Điều hướng | Khởi động mỗi làng; thuyền ngoài màn hình; zoom khác | Chuyển đúng đích, không bấm điểm cũ |
| Camera | Pan; zoom; giới hạn zoom; cạnh dưới bị che | Hình học cập nhật, không bấm vào HUD hoặc thả nhầm khi kéo |
| Combo | Số ô khác nhau; tướng sẵn sàng/không có; quân không đúng | Chuẩn bị/triển khai đúng hoặc báo lỗi cụ thể |
| Chiến thuật | Around; single_point; điểm đầu bị từ chối | Xác nhận triển khai trước khi tiếp tục |
| Hai khu | Result ở khu một; 100% đang chuyển khu; tiếp viện | Không rút nhầm, không thả lại ô đã triển khai/kỹ năng hết |
| Scheduler | Trước/sau 15:30; giữa trận; restart; qua ngày; ngủ máy | Một yêu cầu hợp lệ, nhường đúng lúc, kiểm tra bù |
| Recovery | Mất ADB; connection lost; reload; modal không rõ | Hủy input cũ; phân loại lại; không lặp vô hạn |
| Stop | Đang gesture/batch/chờ/reward | Không phát input mới sau điểm dừng; giải phóng gesture |
| Main regression | Train đầu; wall/event; spell; hero; lọc loot | Hành vi đã có được giữ đúng |

Unit/integration test dùng fake clock, fake ADB và frame fixtures cho logic quan trọng. Test thị giác phải có mẫu âm và ảnh gần giống, không chỉ ảnh mẫu thuận lợi. Kiểm tra GUI trực quan cho thay đổi bố cục; không cần test tự động chỉ để phản chiếu màu/chữ tĩnh.

Lệnh baseline/nghiệm thu toàn bộ hiện có:

    python -m unittest discover -s tests -q
    python tools/check_assets.py

Trong mỗi giai đoạn chạy test liên quan và kiểm tra bắt buộc. Chỉ mở rộng/chạy lặp toàn bộ khi tích hợp lớn, có lỗi hoặc tới nghiệm thu; không chạy lại vô ích cho thay đổi tài liệu.

## 6. Cách theo dõi và bàn giao

Tạo/cập nhật docs/dual-village-progress.md khi bắt đầu triển khai. Mỗi giai đoạn ghi:

- Trạng thái: chưa làm / đang làm / hoàn thành phần code / đã kiểm chứng thực tế / còn vướng.
- File thay đổi và quyết định thiết kế khác kế hoạch, nếu có.
- Test đã chạy và kết quả thật.
- Ca thử trên game: serial, độ phân giải/ngôn ngữ, dữ liệu bằng chứng; chỉ ghi những gì thực sự quan sát.
- Phần chưa làm/chưa kiểm chứng và điều kiện để tiếp tục.
- Điểm bắt đầu rõ ràng cho giai đoạn kế tiếp.

Không thay đổi mã nguồn chỉ vì tài liệu này được tạo. Mỗi prompt trong file đi kèm là một yêu cầu triển khai riêng khi người dùng gửi nó cho agent.
