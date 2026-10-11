# CocMagic hai làng — baseline GĐ0

Khảo sát ngày 08/10/2026, giờ Việt Nam (UTC+7). Chỉ thực hiện GĐ0; chưa triển khai GĐ1–GĐ8.

## 1. Phạm vi, trạng thái repo và nguồn bằng chứng

- Đã đọc toàn bộ [kế hoạch](dual-village-plan.md), mục quy tắc chung của [prompts](dual-village-prompts.md), README và `.gitignore`. Không tìm thấy `AGENTS.md` trong repo (kể cả file ẩn) hoặc các thư mục cha tới gốc ổ C:.
- Nhánh lúc bắt đầu: `codex/source-update...origin/main`; HEAD `3757485e4bb9e705ac8313fa86c738811430b42f`.
- `git status --short --branch` trước khảo sát chỉ có `?? docs/dual-village-plan.md` và `?? docs/dual-village-prompts.md`. Đây là thay đổi sẵn có, giữ nguyên. Chưa có `docs/dual-village-progress.md`.
- Đã đọc/đối chiếu `cocmagic/config.py`, `instance_store.py`, `gui.py`, `bot_engine.py`, `modules/farm_module.py`, `adb_controller.py`, `battle_planner.py`, `attack_tactics.py`, `modules/hero_module.py`, `bot_worker.py`, `session_manager.py`; đọc thêm entrypoint `gui.py`, `cocmagic/main.py`, device discovery và các test liên quan.
- Đầu ra bổ sung chỉ gồm tài liệu, manifest, crop video có chọn lọc và một mẫu che nhân tạo. Không sửa source, requirements, asset cũ hoặc cấu hình người dùng; không chạy entrypoint bot, không gửi input vào game, không commit/push/deploy.

Bằng chứng có thể mang theo repo: [manifest](../tests/fixtures/dual_village/manifest.json), [hướng dẫn fixture](../tests/fixtures/dual_village/README.md), [sheet train](../tests/fixtures/dual_village/train_evidence.jpg), [sheet camera](../tests/fixtures/dual_village/camera_evidence.jpg). Sheet chỉ phục vụ đối chiếu trực quan, không làm input nhận diện.

Bằng chứng đầy đủ tại máy này nằm trong `diagnostics/dual_village_gd0/` (đã được gitignore): `unittest.log`, `assets.log`, `baseline-results.json`, `environment.json`, `backend-tools.json`, `video_1_probe.json`, `video_2_probe.json`, `frame-index.json`, `asset-audit.json`, các sheet khảo sát và `frames/*.png`. Không đưa video hay toàn bộ frame vào repo. Manifest lưu SHA-256 nguồn/frame/crop, PTS và frame index để truy ngược hoặc trích lại khi diagnostics không còn.

## 2. Baseline thực thi

Môi trường: Windows `10.0.26200` theo ADB; Python `3.13.7` tại `C:\Users\PC\AppData\Local\Programs\Python\Python313\python.exe`. Thư viện đọc được: OpenCV `4.12.0.88`, NumPy `2.2.6`, Pillow `12.3.0`, PyAV `19.0.1`. CWD là workspace dự án.

| Lệnh | Kết quả thật | Phạm vi chứng minh |
|---|---|---|
| `python -m unittest discover -s tests -q` | Exit 0; `Ran 213 tests in 71.026s`; `OK`; không báo failure/error/skip | Regression offline hiện có; không phải đánh trận trên thiết bị |
| `python tools/check_assets.py` | Exit 0; `=== ALL CHECKS PASSED ===` | 9 import, load settings và 10 kiểm tra file tồn tại |

Không có lỗi test/asset gate tồn tại sẵn được phát hiện trong lượt chạy này; không sửa lỗi ngoài phạm vi. `check_assets.py` không kiểm tra mọi asset, nội dung ảnh, ngôn ngữ, khả năng match hay backend camera; script cũng không tự trả exit khác 0 khi thiếu asset, nên phải đọc dòng kết luận thực tế.

Log unittest có `[Farm] ERROR ... Interrupted operation` và `[Engine] ERROR: Cannot connect to MuMu Player`. Đây là các tình huống được test chủ động tạo ở `test_battle_input_review.py:287` và `test_control_panel.py:69`, không phải lỗi kết nối live hoặc test thất bại. Các serial xuất hiện trong log unittest cũng là mock/fake worker, không phải danh sách thiết bị thật.

Wrapper chẩn đoán ban đầu lưu được log và nhận exit 0 của unittest, sau đó lỗi `UnicodeEncodeError` khi in tiếng Việt qua `cp1252`. Đây là lỗi wrapper khảo sát, không phải source/test bot. Asset gate được chạy riêng với `PYTHONIOENCODING=utf-8`, không chạy lại full test để làm đẹp log. Log và tóm tắt giữ đúng các kết quả này.

## 3. Main hiện có cần giữ

### Cấu hình, GUI và tiến trình

| Thành phần / điểm mã | Hiện trạng và điều kiện bảo toàn |
|---|---|
| `config.py:73,113,126` | Dictionary phẳng, defaults chứa farm/hero/wall/event; `copy()` rồi `update()` nông; load giữ key chưa biết; save ghi toàn bộ settings. Chưa có schema/settings migration hoặc `run_mode`. |
| `instance_store.py:11,16,40,56,78` | Wrapper `version=1`, danh sách profile theo serial; normalize local serial, chặn lặp/hỏng; copy/merge nông. Save atomic bằng tempfile + fsync + replace và rollback cập nhật khi lỗi. Không đưa mutable lồng nhau vào rồi coi copy nông là độc lập. |
| `gui.py:114,420,935,958,979` | `build_settings()` giữ key không hiện trên form nhưng suy `event_mode = not upgrade_walls`; validation farm/wall áp dụng chung. Mỗi `InstanceTab` có settings, Tk variables và `BotSession` riêng; start lưu trước rồi chạy; inputs/save bị khóa khi chạy. Chưa có ba tab con hoặc ba mode. |
| `gui.py:1825,1838,1875`; `bot_worker.py:19` | Giữ Chạy tất cả/Dừng tất cả, license gate/watchdog, status/log và dừng riêng instance mất kết nối. Worker kiểm tra license rồi khởi tạo engine trong process con; không import Tk ở worker. |
| `session_manager.py:10,22,45,49` | `spawn`, một process/Queue/Event theo serial; copy settings ở parent và worker; route `log/status/done/exited`; cooperative stop bằng Event. Force terminate chỉ dùng khi đóng cưỡng bức sau stop bị kẹt. Test hai process là fake worker, chưa chứng minh hai game thật. |
| `cocmagic/main.py:23,54` | CLI load settings rồi gọi BotEngine; `--port`, `--settings`, `--verbose`, license watchdog. Nếu file settings thiếu, CLI có thể tạo file; GĐ0 không gọi `main()`. GĐ1 phải chặn mode chưa khả dụng ở engine/CLI, không chỉ ở GUI. |

### Thứ tự main và các điểm chuyển trạng thái

- `FarmState` ở `farm_module.py:113`: `HOME → TRAIN (startup) → COLLECT → HOME → FIND_MATCH → LOOT_CHECK → ATTACKING → BATTLE_WAIT → RESULT → COLLECT → HOME`.
- `HOME` (`:388`) kiểm tra `auto_train` và `_initial_trained` trước khi xác nhận Home. Cờ đặt ngay khi chuyển TRAIN; TRAIN (`:1600`) mở Army → Saved Recipes → Use Slot 1, phân biệt Save Army, retry tối đa ba lần và đóng panel. Sau thành công chuyển COLLECT. Không tự chạy lại Quick Train sau mỗi trận, reload hoặc suspend/resume.
- Engine (`bot_engine.py:150`) xử lý popup định kỳ, gọi `farm_mod.tick()`, rồi mới xét wall khi state HOME, không `recovering_home`, không event mode và bật `upgrade_walls`. COLLECT (`farm_module.py:1651`) hiện chỉ đổi enum HOME; không thu xe hay thu tài nguyên builder. Như vậy tick COLLECT về HOME là lúc engine có thể nâng tường trước tick HOME bắt đầu trận tiếp.
- FIND_MATCH (`:451`) có các pha menu/army/loading, xác nhận Attack đã mở menu, retry tối đa bốn lần khi tap Home không thành công. LOOT_CHECK (`:550`) dùng loot threshold và planner; không đạt thì Next. Gold/elixir là OR giữa các ngưỡng bật, dark là điều kiện bổ sung.
- ATTACKING (`:599`) lập tactics theo base → hiệu chuẩn/kiểm tra combo → quân → siege → hero → spell → kỹ năng → BATTLE_WAIT. Dò điểm mới bằng quân và ảnh mới xác nhận lượng giảm trước batch; giữ quy tắc Electro nhiều hướng, hero theo hướng đã xác nhận, spell không rõ thì không ném mù.
- BATTLE_WAIT (`:1379`) ưu tiên Home/result/xác nhận rút, sau đó kỹ năng và hard timeout (mặc định 85s), rồi spell pending, rồi rút sớm theo min_farm/star_target. Spell recovery có cooldown monotonic 2s và giới hạn; không rút sớm bỏ phép đang đối soát, hard timeout vẫn ưu tiên. Timer trận/hero hiện dùng `time.time()`, không phải toàn bộ đã monotonic.
- RESULT (`:1543`) chỉ tăng `attack_count` sau thấy Home; hủy pending spell và chuyển COLLECT. Các nút Okay/Return Home cũ là main-specific; không dùng làm bộ phân loại hai khu hay thưởng sao builder.
- Event reward (`:243,315`) ngắt chuỗi input, ưu tiên tài nguyên, chờ hai ảnh sạch rồi chọn lại card; reward generation giúp đối soát batch hero/spell. Fast batch chỉ dùng ngoài vùng thẻ, farm chia tối đa 80 tap/nhóm. Giữ khả năng result/reload hủy phần input còn lại.

### Recovery và điểm nhường chưa có

- Engine khởi tạo trực tiếp `FarmModule`, `HeroModule`, `WallModule`; kiểm tra screenshot đúng 1600×900 trước chạy. Status/halt/wall gating dùng trực tiếp farm và `FarmState.HOME`. Chưa có coordinator, module contract hoặc village classifier.
- Connection lost (`bot_engine.py:206`; farm `:341`) tìm đúng Try Again, tap thành công thì reset, chờ 10s có thể ngắt qua stop Event, xóa screenshot. Reset giữ `_initial_trained`, thống kê; xóa combo/map/hero/spell/input state rồi đặt enum HOME. Đây chưa phải xác nhận đang ở main Home.
- Popup inactivity (`bot_engine.py:226,270`) dùng độ sáng và ROI text, tap vị trí cố định rồi đặt HOME; popup khác và `_go_home_safe()` (`farm_module.py:1733`) cũng có đường đặt HOME sau thao tác/back mà chưa xác nhận làng đích. Builder nền tối là mẫu âm bắt buộc trước khi dùng chung.
- `recovering_home` (`:1751`) chỉ nghĩa là Attack đã thất bại và đang retry, không bao quát modal/train/wall/batch/pending spell. Hiện không có `can_yield` an toàn. GĐ2 cần kiểm tra trước trận mới và sau hậu xử lý, không suy nhường điều khiển từ enum HOME.
- `tap_many` chỉ kiểm tra stop trước khi gửi shell; không cắt shell đang chạy giữa nhóm. Một số tap/swipe/chờ vẫn dùng `time.sleep`. Không cam kết stop tức thì hoặc đổi làng giữa batch đang cần đối soát.

## 4. Cache và không gian tọa độ

| Cache | Vòng đời thật / nguy cơ khi thêm hai làng và camera |
|---|---|
| ADB `_cached_screenshot`, `_frame_matches` (`adb_controller.py:132,174`) | TTL mặc định 0,35s; ảnh mới xóa kết quả match; input/shell/tap_many xóa ảnh và frame matches. Đọc xác nhận phải `use_cache=False`; hai lần gọi cùng cache không phải hai ảnh độc lập. |
| ADB `_template_cache`, `_match_positions` (`:197,374`) | Template theo path và vị trí match theo template/region/frame shape; `invalidate_cache()` không xóa chúng. Vị trí cũ được match lại trong pad 12 rồi tìm toàn vùng khi cần. Chưa có village/camera revision trong key. |
| Farm `_button_cache`, `_button_templates`, `_home_verified`, `_find_phase` (`:1658,1697`) | UI buttons có kiểm tra ROI pad 18; riêng Home đã verified có đường tap cache trực tiếp. `invalidate_ui_cache()` xóa buttons/home flag/find phase và `_battle_plan`, không phải reset toàn bộ battle/vision state. |
| Farm `_combo_profile` (`:687,713`) | Cards/hero/resolution giữ suốt phiên; chỉ quét khi thiếu hoặc thử hiệu chuẩn lại khi bar không khớp. Reload xóa. Không dùng combo main cho builder; đổi làng phải phân vùng/xác nhận lại cache thay vì lặp startup train. |
| Farm `_vision_frame`, `_count_cache`, `_depleted_cache`, `_guarded_frame` (`:761`) | Count/depleted gắn identity ảnh. Main có quy tắc x0 hoặc bão hòa thấp cho hết quân; không áp dụng nguyên quy tắc cho thanh builder có kỹ năng và quân sống. Reset reload xóa. |
| Map `_battle_plan`, `_attack_tactics`, `_confirmed_main_points`, `_electro_drop_points`, `_hero_entry`, `_verified_battle_points` | Khởi tạo/làm mới theo trận, nhưng chưa có invalidation theo camera revision. `invalidate_ui_cache()` chỉ xóa plan; tactics/điểm khác còn cho tới reset/khởi tạo trận. Không tái dùng sau pan, zoom, chuyển khu hoặc làng. |
| Hero/spell `_deployed_hero_slots`, timestamps, `_pending_ability_names`, `_hero_abilities_used`, `_pending_spells`, `_spell_check_frames`, `_selected_battle_card`, `_reward_generation` | Trạng thái input còn dang dở phải hoàn tất hoặc hủy/đối soát trước nhường. Spell giữ cả ảnh mốc chưa xác nhận và index đã cast; không xóa bừa khi suspend main. Reload phải hủy vì trận cũ không còn đáng tin. |
| Asset/OCR `_spell_templates`, hero `_portrait_templates()` và các `troop_vision` lru_cache; `ScreenReader._digit_tpls` | Cache dữ liệu ảnh/font, khác cache vị trí runtime. Không có dữ liệu sẵn chứng minh nhận diện tướng/quân builder. Process con cô lập giữa instance. |

`BattlePlanner` chỉ nhận ảnh `(900,1600)`; fallback `CONSTRUCTION_DIAMOND` (`battle_planner.py:32`) là `(800,75),(1430,440),(800,805),(170,440)`. Nó lọc HUD/điểm dưới y≈695 và tạo ứng viên cần thử; không phải hình học hợp lệ sau camera đổi. `AttackTactics` lưu hướng vào, tâm, hotspots và rage entries theo ảnh base; còn các tham chiếu cố định `(800,450)`/ROI 1600×900. GĐ3 phải xử lý cả planner lẫn tactics và verified points. HUD/card thuộc màn hình, không được dịch theo phép biến đổi bản đồ.

Hero hiện tại (`hero_module.py:26`) chỉ gồm king, queen, warden, royal_champ, prince, luke; chính sách nhóm kỹ năng theo Warden delay/máu thấp thuộc main. Không coi đây là bộ tướng hoặc chính sách kỹ năng builder.

Các test bảo toàn trọng yếu đã nằm trong lần chạy full: `test_farm_regressions`, `test_capture_cache`, `test_connection_recovery`, `test_control_panel`, `test_multi_instance`, `test_event_rewards`, `test_battle_input_review`, `test_video_burst_regressions`, `test_selected_count_frames`, `test_spell_regressions`, `test_deployment_perimeter`, `test_confirmation_dialogs`, `test_wall_module`, `test_wall_price_regressions`, `test_licensing`, `test_process_utils`. Chưa có test contract/coordinator/camera/builder/scheduler mới.

## 5. Đối chiếu hai video

### Metadata, viền và phương pháp timestamp

| Nguồn | Output ffprobe | Giới hạn tọa độ/ngôn ngữ |
|---|---|---|
| `C:\Users\PC\Downloads\1791438698091_2054695061538342203_7446498411049790191.mp4` | H.264; 1556×720; 191,433333s; 5642 frame khai báo; nominal 30/1, average 42315/1436; time_base 1/600; 51.327.698 byte | Tiếng Việt; không có viền desktop; có thanh home iOS ở đáy và Control Center cuối video. Không phải ảnh ADB 1600×900. |
| `C:\Users\PC\Documents\Bandicam\bandicam 2026-10-08 15-43-48-146.mp4` | H.264; 1064×640; 21,233s; 635 frame khai báo; nominal 30/1, average 6350000/212333; time_base 1/30000; 31.507.070 byte | Game tiếng Anh; title `Android Device-1`, thanh cửa sổ khoảng 40px trên, watermark Bandicam; viền đen phải khoảng 7px, dưới khoảng 6px. Game viewport ước lượng `[1,40,1057,634)` ≈1056×594, cần hiệu chuẩn lại nếu dùng cho vision. Video không chứng minh cửa sổ là MuMu. |

Đã đọc metadata bằng `ffprobe -v error -show_format -show_streams -of json <video>`. Trích 122 frame được chọn bằng PyAV 19.0.1/libav, **giải mã tuần tự từ đầu, không seek**; chọn frame đầu có `frame.pts × frame.time_base >= timestamp yêu cầu`. Đã xem sheet bao quát và frame/crop nguyên kích thước cho các mốc dưới. Manifest giữ 44 quan sát chọn lọc. Không dùng `frame_index / 30`: hai video không có average fps đúng 30; yêu cầu 170,5s thực tế chọn PTS **170,666667s**, 187s chọn **187,033333s**. Các mốc khác trong bảng lấy PTS đã xác minh, không suy theo đồng hồ trong game.

Đã giải mã thêm cả hai stream tới EOF để đối chiếu: train đúng 5642 frame, PTS cuối 191,4s, khoảng hở PTS lớn nhất 0,533333s; camera đúng 635 frame, PTS cuối 21,2s, khoảng hở lớn nhất 0,066667s. Audit ở `full-decode-audit.json`; các khoảng hở củng cố việc phải dùng PTS thay vì giả định 30fps liên tục.

### Video train: các mốc có bằng chứng

| PTS video | Quan sát đã kiểm tra | Hệ quả / phần chưa biết |
|---|---|---|
| 00:00,000; 00:12,000 | Builder home tối, sao trên Attack và `0/7` | AVAILABLE dù tử số bằng 0 |
| 00:04,000 | Main home sau chuyển làng | Mẫu âm phân biệt hai làng |
| 00:16,000 | Bảng Bắt đầu tấn công, 5 ô Rồng con | Có hàng tướng trong menu nhưng chưa đủ xác nhận ready; không suy tướng đã thả |
| 00:17,000 | Mây/Đang tìm kiếm đối thủ | Không thấy sao do loading phải UNKNOWN |
| 00:20,000 → 00:25,000 → 00:27,000 | Trước thả 5 ô; sau đó ô 1/2 có thanh máu; rồi cả 5 ô đã triển khai | Cặp trước/sau thả; không kế thừa cách đọc xN của main |
| 00:27,000 → 00:35,000 → 00:40,000 | Thanh tím kỹ năng còn; sau đó 1 ô xám, ô 2/3 mất thanh tím, rồi ô 2 xám | Có bằng chứng thay đổi trạng thái kỹ năng/chết. Video không có trace input đủ để chốt mỗi tap hay thời điểm kích hoạt tối ưu |
| 01:02,000 | Result trận đầu 100%, nút Về làng | Có trận kết thúc ở một khu; sao result không phải sao thưởng Home |
| 01:48,000 | Builder home có `6/8` | Không cố định mẫu số theo `0/7` đầu video |
| 01:53,000; 01:56,000 → 01:57,000 | Trận thứ ba, khu một trước/sau thả | Bối cảnh trận hai khu |
| 02:23,000 → 02:27,200 | 100% khu một nhưng vẫn là màn trận | 100% chưa phải result; mốc sớm hơn 02:25 cũng đã đạt 100% |
| 02:27,500 → 02:27,800 → 02:28,200 | Camera chuyển khu; tới khu tối mới, đếm chuẩn bị 1 phút, có 6 ô | Bỏ tọa độ khu cũ; năm quân sống có thanh máu, ô thứ sáu tiếp viện. Không thấy chân dung tướng đã triển khai |
| 02:29,000 → 02:30,500 | Khu hai trước/sau triển khai, timer sang 2 phút, tổng damage đang 100% | Quét lại card và kỹ năng từng ô; không phục hồi kỹ năng đã dùng |
| 02:49,000 | Result cuối 200%, Về làng | Mẫu âm sao result hai khu |
| 02:50,667 → 02:52,000 | Loading về Home và sao bay | Không đọc sao đang animation thành COMPLETE |
| 02:53,000; 02:54,000 | Bảng “Thưởng Sao!”, 155.000 vàng + 155.000 tiên dược | CLAIMABLE; counter dưới bảng đang thay đổi, không bypass modal |
| 02:56,000; 02:57,000 | Bảng đóng, sao và `4/8` vẫn hiện | **Nhận thưởng xong vẫn còn lượt thưởng**; phải đọc lại và tiếp tục. Chưa thấy toàn chuỗi kết thúc |
| 02:59,000 → 03:00,000 | Pan tới xe, mở Xe Tiên dược; hai dòng phòng thủ xong có nút thu, một dòng đang bị tấn công | Có tiền thu + phòng thủ đang chạy cùng lúc |
| 03:03,000; 03:04,000 | Chỉ còn dòng đang bị tấn công; nút Thu thập xám, hạt tiên dược và số tiền còn chuyển động | Không gắn nhãn “xe trống ổn định”; còn thiếu ảnh thật trạng thái 0, không animation |
| 03:06,000 → 03:07,033 | Thuyền ở builder rồi sang main | Tham chiếu điều hướng/camera, không chứng minh bot đã điều hướng đúng |

### Video camera

- 00:00 → 00:04: main được phóng lớn trong khi HUD vẫn ở chỗ cũ.
- 00:06 và 00:10: khung nhìn dịch tới bờ/thuyền, thuyền phóng lớn.
- 00:12 → 00:14: builder home ở các mức camera, nút Attack hai rìu nhìn rõ **không có hàng sao**. Đây là mẫu video ứng viên COMPLETE; camera đang thay đổi nên chưa thay thế được cặp ADB ổn định.
- 00:16: thuyền builder lớn; 00:17 sang main; 00:20 main trở về khung nhìn rộng.
- Video chứng minh bản đồ đổi tỷ lệ/vị trí và chuyển hai chiều bằng thuyền, **không ghi lại phím/chuột hay giao thức multi-touch**. Không xác nhận Ctrl+scroll chính là input đã dùng, không chứng minh pinch qua ADB hoặc drag lúc chọn quân trong trận.

## 6. Thiết bị và backend camera

Chỉ dùng binary cấu hình dự án `C:\Program Files\Netease\MuMuPlayer\nx_main\adb.exe`; không gọi hàm discovery/port scan, không `adb connect`, không dò host/USB ngoài môi trường dự án.

```text
adb version
Android Debug Bridge version 1.0.41
Version 36.0.0-13206524
Running on Windows 10.0.26200

adb devices -l
List of devices attached
```

Hai lệnh exit 0. ADB tự khởi động daemon host ở tcp:5037 khi liệt kê; không có serial được liệt kê. Vì vậy chưa chạy `wm size`, `screencap`, `input --help`, `getevent -lp` hoặc kiểm tra helper trên Android. **1600×900 là yêu cầu từ source/kế hoạch, chưa phải độ phân giải thiết bị đo được trong GĐ0.** Không kết luận mọi giả lập đều tắt chỉ từ danh sách ADB trống.

| Khả năng/tool tại máy này | Bằng chứng và trạng thái |
|---|---|
| ADB pan một điểm | `ADBController.swipe()` (`:106`) đã gọi `input swipe`, có serial, invalidates screenshot; wall module đang dùng để cuộn danh sách. Hàm không trả kết quả `_shell()` cho caller, chưa có xác nhận ảnh sau camera pan. Có primitive sẵn, chưa kiểm chứng pan game trong GĐ0. |
| Pinch nhiều điểm | Repo không có pinch, pointer-down/up, multi-touch backend hoặc camera controller. Hai swipe độc lập không phải pinch đã được hỗ trợ. Chưa có thiết bị để thử thực tế. |
| MuMu CLI | Có `mumu-cli.exe`, `MuMuManager.exe` trong `nx_main`, file `nemu-vcontrolmanager.dll`; CLI version trả `6.6.3.0`. Help `control`, `control tool`, `control shortcut` không công bố lệnh pinch/pointer. `shortcut` chỉ create/delete shortcut; tên DLL không chứng minh API touch. Các lệnh help trả mã Windows `4294967295` (-1) dù in help; lệnh version exit 0. |
| Thư viện host | Có `pyautogui 0.9.54`; không có `pynput`, `uiautomator2`, `adbutils`, `ppadb`. `scrcpy` và `adb` không nằm trên PATH (ADB cấu hình vẫn có). Không cài thêm package/helper. |
| Fallback cửa sổ | PyAutoGUI/Ctrl+scroll là phương án cần khảo sát, chưa có mapping serial↔window, khóa focus/input và release khi stop. Video đổi camera không chứng minh fallback này hoạt động trên MuMu. |
| Phương án backend Android | Helper gửi MotionEvent nhiều pointer hoặc backend touch chuyên dụng chỉ là hướng cần đánh giá. `getevent`/`sendevent`, quyền input, helper đã cài, minitouch/scrcpy server và khả năng simultaneous contacts đều chưa đo; không tự gán “có root” hay “pinch được”. |

Đầu vào thử GĐ3: thiết bị dự án kết nối, serial/resolution thật, quyền và backend hợp lệ; ảnh trước/sau cùng serial; kiểm tra pan, pinch đồng thời, giới hạn zoom, HUD cố định, camera ổn định, stop/error release, hai serial/focus, cạnh dưới bị bar che và drag đang chọn quân. Chỉ đánh dấu hỗ trợ sau các phép thử này.

## 7. Fixture hiện có và thiếu

Manifest có **44 quan sát video, 14 crop video PNG, 1 crop biến đổi che nhân tạo, 2 contact sheet**, tổng khoảng 1,64 MiB trước README. Crop giữ pixel video, có parent/PTS/crop box/dimensions/hash; không tự resize thành 1600×900 để gọi là ADB. Các nhãn là chú giải thủ công cho giai đoạn sau, chưa là output của bộ nhận diện.

Ba nhóm được tách rõ: `video_crop` (nguồn video), `adb_native` (hiện thiếu toàn bộ), `transformed_test` (ảnh che nhân tạo, không là trạng thái game thật). Full PNG nguồn đã trích ở diagnostics, ngoài bộ thay đổi; contact sheet có resize/label/JPEG nên `test_input=false`.

Ưu tiên P0 trong `missing`: cặp Home builder thật không sao ổn định; loading không sao; nút thật bị che; main Attack có sao; result có sao; builder tối đối chiếu inactivity. Đã có mẫu video/crop âm cho loading/main/result, mẫu không sao trên video và mẫu che nhân tạo; vẫn phải bổ sung bản ADB đúng môi trường. Crop đơn lẻ không chứng minh được đúng làng hay không có modal.

Các khoảng trống tiếp theo: Home hai làng 1600×900 ở ngôn ngữ thật; chuỗi reward tới thật sự hết sao; xe trống ổn định/failed close; tướng builder ready/upgrading/absent/unknown; số ô khóa/khác nhau; before/after kỹ năng có trace; hai chiến thuật và điểm bị từ chối; pan/pinch native, giới hạn zoom/cạnh dưới, drag chọn quân và hai serial. Các ca None/resize/affine còn ở mục biến đổi dự kiến, chưa giả thành ảnh có thật.

Audit asset trực quan ở `asset-audit.json` và manifest:

- `mainvill.png` 4320×6000 là poster, không phải template main home.
- `night.png` 134×70 chỉ là rìu Attack; `thuyennight.png` 33×30, `thuyensun.png` 33×26 là crop thuyền nhỏ. Có thể khảo sát lại ở scale/ngôn ngữ native; tên file chưa chứng minh match được.
- `nighthero1.png` 101×81 và `nighthero2.png` 100×93 là chân dung tướng builder, không chứa đầy đủ các trạng thái ready/deployed/ability/dead.
- `okaystar.png` 228×84 là nút “Okay” tiếng Anh, khác “Ok” trên bảng thưởng video tiếng Việt; không dùng nút chung làm bằng chứng nhận diện bảng.
- `base.png` 127×131 và `home_attack.png` 105×130 là main Attack tiếng Anh. `tests/fixtures/builder_available_region.png` và `builder_unavailable_region.png` (110×110) là thợ thường/Goblin cho nâng tường, **không phải ảnh làng đêm**. Giữ test main đang dùng chúng.

## 8. Điều kiện đầu vào GĐ1–GĐ3

| Giai đoạn | Có thể kế thừa | Điều kiện/việc cần làm trước nghiệm thu |
|---|---|---|
| GĐ1 | Baseline 213 test, schema phẳng và wrapper version=1 đã khảo sát; fixture/nguồn có manifest | Migration idempotent, giữ unknown keys, settings độc lập; validation main/builder/hybrid đúng phạm vi; ba tab/ba mode, khóa khi chạy và license/all-run giữ nguyên; engine/CLI từ chối mode chưa triển khai. Không cần chờ thiết bị để viết migration/UI, nhưng thử start/stop main thật vẫn còn thiếu. |
| GĐ2 | Thứ tự farm/wall/train/reward/spell, cache và recovery ở trên | Contract/module active, điểm nhường có kiểm chứng trước trận và sau hậu xử lý; không nhường trong modal/wall/batch/spell pending; giữ startup train qua suspend/resume; classify lại sau reload, một owner input/serial. Fake builder chỉ dùng test và ghi rõ. |
| GĐ3 | ADB swipe primitive; planner/tactics và cache phụ thuộc camera đã xác định | Phụ thuộc GĐ2; chọn và chứng minh pinch thật trên MuMu; native before/after và drag-selected safety. Chưa đủ bằng chứng để bật camera mặc định. Không dùng hình thoi cũ sau thay đổi camera. Nếu tiếp tục thiếu thiết bị, phân biệt code/offline với nghiệm thu live còn vướng. |

Kết luận GĐ0: hoàn thành khảo sát offline, baseline và danh mục bằng chứng; hạn chế live được ghi rõ. Main giữ nguyên. Chưa có chức năng builder/hybrid/camera mới được công bố hoạt động.

Kiểm tra bàn giao: SHA-256 trước/sau của 30 file source/entrypoint/requirements/gitignore và file người dùng hiện có trong `data/` không đổi. `git diff --exit-code` và `git diff --check` exit 0 cho tracked files; bộ đầu ra mới còn untracked. Đã kiểm tra tồn tại/hash/dimensions của 15 crop và 2 sheet, parent của crop, hash/PTS của 44 quan sát và các link tài liệu, không phát hiện lỗi. Chi tiết ở `diagnostics/dual_village_gd0/handoff-validation.json`. Không chạy lại full test vì chỉ thêm bằng chứng/tài liệu.
