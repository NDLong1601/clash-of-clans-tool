# Tiến độ CocMagic hai làng

Cập nhật 11/10/2026, giờ Việt Nam (UTC+7). Nguồn yêu cầu: [plan](dual-village-plan.md), [prompts](dual-village-prompts.md). Không cần lịch sử chat để tiếp tục.

**Sửa vòng lặp hybrid mới nhất:** **538 test/328.984s, exit 0** và năm gate source còn lại. Phục hồi main giữ kết quả sao và lịch đang chờ; phân loại lại RESULT không tạo startup builder mới, giữ backoff/giới hạn retry. Xe tùy chọn lỗi ở Home không tạo retry sao; resume/UNKNOWN sau xe không mở lại xe. Live bản cuối 3 chu kỳ main/440.159s, 3 lần phục hồi ảnh, chỉ một lượt xe lúc startup, không quay lại builder sau trận; camera/auto train bật, dừng tại Home. Hash source live khớp source đã test. Xem [báo cáo vòng lặp](dual-village-hybrid-repeat-fix-20261011.md).

**Lượt sửa native reward trước đó:** **529 test/368.462s, exit 0** và năm gate source còn lại. Sửa bảng Star Bonus native bị nhận thành Home, camera timeout ảnh ổn định và thông báo tiến độ/lý do navigation. Live thu xe rồi về main đạt, có receipt 72.426s; chưa tính là toàn chuỗi bot tự nhận thưởng. Xem [báo cáo sửa hybrid trước](dual-village-hybrid-fix-20261011.md).

**Lượt kiểm thử và dọn source trước:** bản `c72db1b` qua **519 test/362.975s, exit 0**, lint/syntax/asset/evidence/CLI đều đạt; kiểm checkout từ Git index cũng đạt. Đã sửa thêm nhận diện Attack/sao native, tướng đang nạp kỹ năng, camp đang chọn và plan sau chọn quân. Live có AVAILABLE và thu xe thật; phiên hybrid cuối của lượt đó xác nhận hai khu rồi Home nhưng thiếu receipt kết thúc. Khóa production chặn alias thứ hai khi probe đang chạy. Xem [báo cáo kiểm thử 11/10](dual-village-verification-20261011.md).

**Lượt sửa F1–F4 trước đó:** main giữ phương án dò khi camera=false sau chuyển làng, khóa input chung cho alias cùng VM, xen kẽ kỹ năng/deploy builder và xóa lịch sử pixel khi đổi view. Kết quả 503 test/309.939s và 17 regression được giữ trong [báo cáo sửa lỗi](dual-village-review-fixes-20261011.md). Các mục GĐ0–GĐ8 dưới đây giữ số liệu lịch sử; đọc cập nhật mới nhất trước khi dùng các giới hạn cũ.

## Trạng thái các giai đoạn

| Giai đoạn | Trạng thái thực tế |
|---|---|
| GĐ0 | Hoàn thành khảo sát offline, baseline và inventory bằng chứng. Chưa kiểm chứng thiết bị vì danh sách ADB trống; giới hạn này được chấp nhận cho đầu ra khảo sát. |
| GĐ1 | Hoàn thành phạm vi cấu hình/ba tab: 232 test đạt, kiểm tra trực quan Tkinter và main start/stop trên emulator-5556 đạt. Builder/hybrid vẫn chưa khả dụng; chưa thử đánh trọn trận hoặc hai game thật. |
| GĐ2 | Hoàn thành mã và kiểm chứng offline: 268 test tích hợp đạt; 36 test contract/coordinator đạt sau guard stop cuối. Chưa chạy game thật ở GĐ2; builder/hybrid vẫn chưa khả dụng. |
| GĐ3 | Đã có mã camera/planner, kiểm chứng offline và pan/pinch/drop thật trên Home/Practice của 127.0.0.1:16416. Chưa nghiệm thu vòng bot multiplayer, hai serial đồng thời hoặc Stop khi map game đang chuyển động không modal; giữ camera mặc định tắt. |
| GĐ4 | Đã có classification/navigation/star/rewards/cart, 336 test đạt và chuyển hai chiều + xe trống thật. GĐ5 bổ sung native xe có tiền/đang phòng thủ/Collect khóa và builder battle/result; vẫn thiếu chuỗi thưởng sao native, chưa nghiệm thu toàn bộ GĐ4. |
| GĐ5 | Đã triển khai module/helpers thật và mở builder-only GUI/CLI cho English 1600×900; 405 test đạt. Live around lặp 2 trận mới; single_point đủ hai khu/không dùng tướng/Home, sửa combo và Stop có receipt. Các nhánh thiếu native được ghi riêng cuối file; hybrid vẫn khóa. |
| GĐ6 | Đã có hybrid với hai module thật, lịch UTC+7, runtime atomic/một writer mỗi serial và trạng thái Run; **439 test nghiệm thu đạt**. Live startup + scheduled bằng clock probe đều xác nhận COMPLETE, xử lý xe, về main. Chuỗi AVAILABLE/CLAIMABLE native còn thiếu; chi tiết và giới hạn ở mục GĐ6. |
| GĐ7 | Đã triển khai recovery/Stop/cô lập runtime-input-status và hoàn thiện ba tab; offline và một giả lập thật có bằng chứng ở mục GĐ7. **Chưa nghiệm thu hai game độc lập** vì chỉ có một thiết bị; không gọi toàn giai đoạn hoàn thành. |
| GĐ8 | Đã đối chiếu code/test/bằng chứng, sửa lỗi phát hiện và kiểm chứng lại; kết quả ở [validation](dual-village-validation.md). **Chưa nghiệm thu toàn bộ**: còn thiếu chuỗi thưởng native, tướng theo tình trạng thật, hai game độc lập và một số nhánh main/recovery live. Camera vẫn mặc định tắt. |

## GĐ0 — kết quả và bằng chứng

- Trước làm: nhánh `codex/source-update...origin/main`, commit `3757485e4bb9e705ac8313fa86c738811430b42f`; hai file plan/prompts untracked của người dùng. Không có progress trước đó, không tìm thấy AGENTS.md.
- Đã đọc kế hoạch đầy đủ, quy tắc chung, README, toàn bộ nhóm file được giao và test liên quan. Main-only dependencies, cache, thứ tự train/wall/reward/spell/hero và các đường gán HOME đã ghi trong [baseline](dual-village-baseline.md).
- `python -m unittest discover -s tests -q`: **213 test, 71.026s, OK, exit 0**, không báo skip/failure/error. Log ERROR trong ca injection đã phân loại; không có test thất bại được phát hiện.
- `python tools/check_assets.py`: **ALL CHECKS PASSED, exit 0**; chỉ 9 import và 10 asset existence checks, không phải toàn bộ asset được nghiệm thu thị giác.
- Hai video có thật, ffprobe xác nhận train 1556×720/191,433333s và camera 1064×640/21,233s. Đã giải mã tuần tự, trích 122 frame theo native PTS, xem sheet và frame/crop then chốt; audit decode tới EOF xác nhận 5642/635 frame. Manifest giữ 44 quan sát, 14 crop video, 1 mẫu che nhân tạo, 2 sheet nhỏ; không thêm video hoặc full-frame trùng lặp lớn vào bộ thay đổi.
- Quan sát quan trọng: `0/7` là còn thưởng; mẫu số đổi sang 8; 100% khu một ở 02:23 vẫn chuyển khu 02:27,5–02:28,2; khu hai có 6 ô; result cuối 200%; bảng thưởng 02:53–02:54 đóng xong vẫn `4/8` tại 02:56–02:57; xe có phần thu được cùng lượt phòng thủ đang chạy. Nút Thu thập xám cuối video chưa chứng minh xe trống ổn định.
- Video camera có main/builder, zoom/pan và thuyền, builder Attack không sao; chưa chứng minh pinch theo serial, đúng MuMu, hai ảnh ADB ổn định hoặc drag khi đang chọn quân. Title cửa sổ là Android Device-1; không tự suy loại giả lập từ kế hoạch.
- Thiết bị: dùng đúng ADB tại `C:\Program Files\Netease\MuMuPlayer\nx_main\adb.exe`; version 1.0.41/36.0.0-13206524. `devices -l` exit 0, **không có serial**. ADB tự bật daemon host 5037. Không scan port/connect, không input, không khởi động bot/đánh trận; chưa có native screenshot/resolution/language đo trên thiết bị.
- Backend: có ADB `input swipe` một điểm qua wrapper; chưa có pinch/multi-touch/camera revision. MuMu CLI có version 6.6.3.0, help chưa công bố pinch; PyAutoGUI đã cài nhưng chưa có serial↔window/focus lock. Không cài tool mới hoặc gọi hai swipe là zoom đã hỗ trợ.

File bổ sung:

- `docs/dual-village-baseline.md`
- `docs/dual-village-progress.md`
- `tests/fixtures/dual_village/manifest.json`, `README.md`
- Các PNG/JPEG chọn lọc được manifest liệt kê trong cùng thư mục.

Diagnostics đầy đủ nằm tại `diagnostics/dual_village_gd0/`, gitignored. Manifest giữ hash nguồn/frame/crop, dimensions, PTS, parent và phép biến đổi. Source/cấu hình người dùng được đối chiếu hash trước/sau; kết quả kiểm tra bàn giao ghi dưới đây. Không thay đổi hành vi bot, không triển khai phần nào của GĐ1.

Kiểm tra bàn giao: **30 file được đối chiếu SHA-256, 0 thay đổi**; `git diff --exit-code`/`git diff --check` exit 0 cho tracked files. Các đầu ra mới còn untracked. Kiểm tra hash/dimensions của 15 crop + 2 sheet, parent crop, 44 frame/PTS và link tài liệu đều đạt; `handoff-validation.json` có danh sách lỗi rỗng. Bộ fixture gồm 19 file (kể cả manifest/README), khoảng 1,64 MiB. Không chạy lại full test sau thay đổi chỉ gồm tài liệu/ảnh.

Quyết định khảo sát: dùng PyAV/libav giải mã tuần tự để tránh sai seek, ffprobe đối chiếu metadata; đây là tool đã cài, không thêm dependency bot. Giữ full PNG ở diagnostics và đưa crop/sheet nhỏ vào fixtures. Phân loại `video_crop`, `adb_native` còn thiếu và `transformed_test` riêng; không gọi fixture tự dựng là ảnh game thật.

## GĐ1 — cấu hình tương thích và ba tab

Ngày thực hiện: 08/10/2026 (UTC+7). Đã đối chiếu kế hoạch, quy tắc chung, baseline, source và thay đổi trước khi sửa. Trước GĐ1 chỉ có bốn tài liệu dual-village và bộ fixture GĐ0 untracked; giữ nguyên plan/prompts/baseline và fixture. Không có AGENTS.md áp dụng. Không commit/push/deploy, không triển khai thuật toán builder hoặc coordinator GĐ2.

### Hành vi và quyết định

- `config.py` là nguồn defaults, migration và validation dùng chung cho GUI/engine/CLI. Settings phẳng, schema 2, wrapper instances vẫn `version=1`. Thêm đúng các key `run_mode`, `builder_deploy_mode`, `builder_auto_setup_baby_dragons`, `builder_use_available_hero`, `builder_collect_cart`, `hybrid_check_time`, `hybrid_timezone`, `camera_auto_adjust` theo contract.
- Migration chỉ trong bộ nhớ khi load, idempotent; thiếu run_mode luôn về main, kể cả template mặc định đã chọn builder. Giữ giá trị cũ/unknown keys; deep-copy cả extension JSON để tránh chia sẻ mutable giữa template/profile/tab. Update một phần trong InstanceStore merge với settings trước đó, không thay toàn bộ profile; giữ save atomic/rollback hiện có.
- Mỗi giả lập có Làng chính, Làng đêm, Run. Giữ cấu hình main hiện có; builder có ba công tắc Rồng con/tướng/xe, hai radio cách thả, giờ kiểm tra UTC+7 và camera. Không thêm thuật toán hoặc tùy chọn kỹ năng ngoài contract; mô tả kỹ năng tự động cho giai đoạn sau.
- Run có radio loại trừ nhau, Bắt đầu/Dừng, status, thống kê tường và log. Nút lưu chung phía dưới lưu cả ba tab của instance hiện tại. Chỉ main có implementation; builder/hybrid hiện “chưa khả dụng”, lưu được lựa chọn nhưng Start bị khóa. Chạy tất cả vẫn xét mode của từng instance, báo lý do ở Run/log và không chạy main thay builder/hybrid. Engine chặn trước ADB; CLI trả mã 2. CLI thêm `--run-mode`, giữ tham số cũ và license.
- Validation áp dụng các trường main khi main/hybrid, builder khi builder/hybrid, lịch khi hybrid; camera/schema/mode được kiểm tra chung. Trường nháp của làng không dùng được giữ nguyên, không cản save; khi chọn hybrid phải hợp lệ cả hai làng. Availability được kiểm tra riêng để không cấm lưu cấu hình cho giai đoạn sau.
- Quy tắc suy event từ nâng tường chỉ dành cho main/hybrid ở API panel cũ. GUI truyền cờ event của Làng chính rõ ràng; lưu builder không tự bật event. Mở/lưu cấu hình có cả event và nâng tường tắt vẫn giữ cả hai tắt.
- Khóa inputs/radio/save khi chạy; vẫn xem tab, cuộn, sao chép log và dừng được. Bỏ bind_all/unbind_all của wheel, lọc theo instance/page; giữ cuộn riêng cho log. Focus chỉ tự cuộn theo control thực sự, không cuộn theo frame/canvas tổ tiên. Áp dụng hướng dẫn UI/UX về focus, keyboard navigation, trạng thái disabled và giữ bố cục Tkinter hiện có; không redesign toàn ứng dụng.

### Kiểm thử offline

- `python -m unittest discover -s tests -q`: **232 test, 80.963s, OK, exit 0**, không báo skip/failure/error. Baseline GĐ0 có 213 test; thêm 19 test hành vi trong `tests/test_dual_village_settings.py`.
- Test mới phủ migration idempotent/không ghi khi load/unknown keys, settings save-reload, wrapper 1, partial update, mutable isolation, validation theo làng, enum/boolean/lịch, mode chưa khả dụng ở engine/CLI, save chéo tab, hai form độc lập, khóa khi chạy, start/stop qua Run, Chạy tất cả/Dừng tất cả, license refresh không bật Start cho builder, và focus không làm nhảy trang.
- Trước bộ đầy đủ đã chạy riêng regression `test_control_panel.py` (6 test) và `test_multi_instance.py` (11 test), đều OK. Các vòng sửa test ban đầu có lỗi mock policy/license_status và assertion thông báo; đã sửa test harness trước lượt nghiệm thu đầy đủ. Không có lỗi mới còn mở.
- `python tools/check_assets.py`: **ALL CHECKS PASSED, exit 0**. Phạm vi kiểm tra giữ đúng giới hạn GĐ0, không coi đây là nghiệm thu nhận diện builder.
- `git diff --check`: đạt. Hash SHA-256 của `data/settings.json`, `data/instances.json`, `data/license-config.json` trước/sau đều không đổi. Mọi save phục vụ QA đi vào thư mục diagnostics riêng.

### Kiểm tra giao diện trực quan

Phương thức: mở cửa sổ Tkinter thật, dùng Computer Use (`node_repl` + `@oai/sky`) quan sát screenshot và click/phím/scroll. Harness tạm `diagnostics/dual_village_gd1/qa_ui.py` dùng BotPanel, BotSession và vòng lặp BotEngine thật với ADB/module giả cho hai serial; đây là phép thử UI/process, không phải hai game thật.

- Đã xem cả ba tab ở **980×840** và Làng chính tại mức tối thiểu **880×680**. Không thấy đè ngang; phần dưới truy cập bằng scrollbar/wheel, nút lưu luôn ngoài vùng cuộn. Đã cuộn trên nội dung main và chuyển tab bằng Ctrl+Tab.
- Phát hiện và sửa lỗi Run tự cuộn xuống vì FocusIn của frame/canvas tổ tiên; kiểm tra lại Run mở từ đầu trang. Thu gọn tile thống kê để log có vùng hiển thị ngay ở kích thước mặc định. Test focus ở cửa sổ tối thiểu xác nhận ô Warden được đưa đầy đủ vào vùng nhìn thấy.
- Chọn builder hiện cảnh báo và khóa Start; chọn lại main mở Start. Main chạy từ Run, xem được Làng đêm trong khi toàn bộ inputs/save bị khóa, dừng từ Run và inputs được mở lại. Snapshot `ui-running.json` xác nhận instance thứ nhất chạy/locked, thứ hai idle; `ui-stopped.json` xác nhận Đã dừng.
- Trong bước kết thúc cửa sổ QA cuối ở lượt đầu, người dùng nhấn Esc dừng Computer Use. Không thực hiện thêm thao tác Computer Use trong lượt đó; các phép thử và worker đã dừng trước thời điểm này. Người dùng sau đó xác nhận bấm nhầm và yêu cầu tiếp tục; đã tiếp tục nghiệm thu bổ sung dưới đây và đóng cả cửa sổ LIVE/QA.
- **Nghiệm thu bổ sung sau khi tiếp tục:** kiểm tra Làng đêm và Run tại 880×680, cuộn tới lịch/camera/thống kê/log, nút lưu luôn hiển thị. Thao tác UI lưu `hybrid` + `single_point` cho serial 16384; serial 16416 vẫn `main` + `around`. Đóng/mở lại ứng dụng QA, quan sát radio và đối chiếu file xác nhận cả hai cấu hình, các trường main và `legacy_note` còn nguyên; wrapper vẫn version 1.
- Bấm **Chạy tất cả** trên UI sau reload: instance hybrid bị từ chối rõ trong status/log, chỉ instance main chạy worker mô phỏng thật qua BotSession/engine loop. Quan sát cấu hình main khóa đúng; bấm **Dừng tất cả** xác nhận toàn bộ worker dừng và UI mở khóa. Đây là kiểm chứng UI/process bằng ADB/module giả, không có input game mới.
- Đã đóng toàn bộ cửa sổ QA/LIVE, `list_windows` không còn cửa sổ kiểm thử. Snapshot bổ sung `resume-ui-saved.json`, `resume-all-running.json`, `resume-all-stopped.json`; stderr hai phiên bổ sung rỗng. Hash ba file cấu hình người dùng vẫn không đổi. Không sửa thêm source/test, không chạy lặp bộ 232 test đã đạt vì không có thay đổi mã hoặc lỗi mới.

### Kiểm chứng main trên thiết bị thật

GĐ1 phát hiện thiết bị mà GĐ0 chưa có: `adb devices -l` trả **emulator-5556**, product/device `a55x`, model `SM_A5560`. Dùng đúng ADB của dự án, không scan/connect thêm. `wm size` trả physical **900×1600**; ảnh screencap Android ở chiều ngang thực tế **1600×900**, game tiếng Anh, ban đầu là main Home.

Harness `diagnostics/dual_village_gd1/live_ui.py` chỉ cô lập file settings/instances và tắt discovery; **không mock BotSession, worker, ADB, engine, farm/hero/wall hoặc license**. Giao diện/worker dùng kiểm tra license thật hiện có. Cấu hình QA: `main`, `auto_train=false`, `upgrade_walls=false`, `event_mode=false`, ngưỡng Gold/Elixir 1 nghìn tỷ để kiểm tra vòng đời và không triển khai quân.

- Bấm Bắt đầu ở Run: ADB connect thành công, OCR và bốn module khởi tạo, vòng lặp main hoạt động. Quan sát HOME → FIND_MATCH → LOOT_CHECK, đọc loot và bấm Next một lần; log thống kê `Attacks=0`, `Skipped=0` trước khi skip #1. Phiên đã dùng tìm đối thủ và phí tìm trận của game; không thả quân, không Quick Train, không nâng tường.
- Bấm Dừng ở Run: giao diện Đã dừng, `done.stopped=true`, `done.ok=true`, **process exit 0**; nút Start/save và cấu hình mở lại. Snapshot `live-running.json`, `live-stopped.json` giữ log/trạng thái thật.
- Sau khi worker dừng, game còn ở màn đối thủ. Đã bấm End Battle thủ công qua ADB và xác nhận ảnh mới trở lại main Home (`device-return-confirm.png`). Không có trận với triển khai quân được kiểm chứng trong lượt này.

### File và bằng chứng bàn giao

Source: `cocmagic/config.py`, `instance_store.py`, `gui.py`, `bot_engine.py`, `main.py`. Tests: `tests/test_dual_village_settings.py`. Tài liệu: `README.md`, file progress này. Không sửa thuật toán FarmModule, hero, wall, discovery, session/worker hoặc cơ chế license.

Bằng chứng cục bộ (gitignored) tại `diagnostics/dual_village_gd1/`: `unittest.log`, `assets.log`, `handoff-validation.json`, harness `qa_ui.py`/`live_ui.py`, các snapshot `ui-running.json`, `ui-stopped.json`, `live-running.json`, `live-stopped.json`, stdout/stderr và ảnh Android trước/sau/về Home. Hash đầu vào tại `diagnostics/dual_village_gd1-data-before.json`. Ảnh game chứa dữ liệu tài khoản nên chỉ giữ diagnostics, không thêm vào fixture/repo.

**Kết luận GĐ1:** hoàn thành phạm vi được giao, có kiểm chứng offline, trực quan và main start/stop thật. Builder/hybrid/camera/lịch chưa thực thi và không được công bố hoạt động. Chưa kiểm chứng trận main hoàn chỉnh, hai game đồng thời hoặc các nhánh builder; không dùng các phép thử mock làm bằng chứng cho các phần đó. Đầu vào GĐ2: contract tick/status/halt/recovery, safe boundary và giữ thứ tự main; không cần làm lại migration/ba tab. Đầu vào GĐ3 vẫn cần backend multi-touch thật và dữ liệu camera đã liệt kê ở baseline; thiết bị hiện có mới chứng minh main Home/start-stop.

## Khoảng trống dữ liệu còn mở

Danh sách máy đọc được (snapshot khảo sát GĐ0; GĐ1 đã có main Home native trong diagnostics nhưng chưa bổ sung các nhóm builder/camera): [`manifest.json → missing`](../tests/fixtures/dual_village/manifest.json), 19 nhóm yêu cầu (16 nhóm native ADB, 3 nhóm biến đổi dự kiến).

P0: cặp native builder Home rõ nút không sao; loading không sao; nút bị che thật; main Attack có sao; result có sao; builder tối và popup inactivity. Mẫu video/nhân tạo đã có chỉ giúp nghiên cứu, không hoàn tất live validation.

Còn thiếu: reward chain tới hết thật; xe trống không animation/failed close; tướng builder ready/upgrading/absent/unknown; số ô khác/khóa; kỹ năng có trace input; hai chiến thuật/điểm từ chối; camera native pan/pinch/limit/HUD/cạnh dưới; selected-troop drag và stop release; hai serial thật. Chưa có detector mới nên không có kết quả accuracy hoặc PASS nhận diện tự động.

## Điểm bắt đầu cho GĐ1–GĐ3

1. **GĐ1 đã hoàn thành**: kế thừa schema phẳng/validation/ba tab và availability guard; đọc kết quả/bằng chứng ở trên, không làm lại các phần đã đạt.
2. **GĐ2 đã triển khai**: contract/coordinator và kết quả offline ở mục dưới. Fake builder chỉ là test harness; runtime vẫn đăng ký main. Giữ availability guard khi tiếp tục GĐ3–GĐ5.
3. **GĐ3**, sau GĐ2: xử lý map/HUD và invalidation đồng bộ cho plan/tactics/confirmed points; nâng swipe có kết quả và ảnh xác nhận. Cần serial/resolution/backend multi-touch thật để nghiệm thu pinch, pan, stop/release và drag đang chọn quân. Camera chưa đủ điều kiện bật mặc định; thiếu live thì báo còn vướng, không công bố hỗ trợ từ mock/video.

Ghi chú lịch sử GĐ1: lượt đó chưa triển khai GĐ2–GĐ8. Lượt hiện tại chỉ triển khai GĐ2 theo yêu cầu mới, không tự chuyển sang camera/navigation/train builder.

## GĐ2 — hợp đồng module, điểm nhường và phục hồi

Ngày thực hiện: 08/10/2026 (UTC+7). Phụ thuộc GĐ1 có đủ trong source: schema 2, validation chung, ba tab, availability guard tại GUI/engine/CLI và test tương ứng. Báo cáo GĐ1 có bằng chứng main start/stop thật; GĐ2 kế thừa bằng chứng đó, không coi đó là thử game cho mã GĐ2.

Trước khi làm, workspace đã có thay đổi GĐ1 ở README/config/gui/instance_store/main/bot_engine, bốn tài liệu dual-village, fixtures, test settings và `CocMagic_Release.zip`. Giữ nguyên phần sẵn có. Trong lúc GĐ2 chạy xuất hiện thêm thay đổi ngoài lượt này ở `battle_planner.py` (chuẩn hóa shape Hough bằng reshape) và `test_deployment_perimeter.py` (một regression tương ứng); không chỉnh/xóa/nhận đó là implementation GĐ2. Bộ tích hợp được chạy trên workspace gồm cả hai thay đổi này. Không commit/push/deploy, không tác động game hoặc sửa cấu hình cá nhân.

### Contract thực tế

Contract nằm trong `cocmagic/village_module.py`, dùng Protocol nhỏ, không thêm framework/state machine chung. `FarmModule` triển khai trực tiếp; BuilderFarmModule thật chưa có.

| API | Quy tắc |
|---|---|
| `device_serial` | Mọi module đăng ký với một coordinator phải cùng serial. Một worker sở hữu một coordinator và một ADB controller cho serial đó. |
| `tick(yield_requested=callback) -> bool` | Tick đồng bộ, không tạo input nền; chỉ active module được tick. Callback đọc yêu cầu hiện tại, kể cả yêu cầu đến trong tick; kiểm tra trước khi mở trận mới. False dừng phiên. |
| `status_line`, `metrics`, `halt_reason` | Route theo active; metrics riêng từng module, main giữ attack/skip/wall count. Payload giữ `status`/`wall_count` tương thích GUI và thêm active_module, confirmed_screen, halt_reason, switch_target/reason, module_metrics. |
| `confirmed_screen` | Màn hình đã nhận diện gần nhất: UNKNOWN/HOME/MENU/SCOUT/BATTLE/RESULT/MODAL. UNKNOWN sau invalidation/reload/chuyển làng. Không dùng riêng giá trị này để cấp quyền input hoặc nhường. |
| `can_yield` | Chỉ true sau tick đã hoàn tất hậu xử lý và kiểm tra ảnh HOME mới, không modal, không thao tác còn đối soát. Luôn false khi đang tick, suspend, dừng hoặc halt. |
| `suspend()` | Chỉ chấp nhận tại can_yield. Không reset setup, reward, spell, hero hay thống kê giữa chừng; yêu cầu không an toàn bị từ chối. |
| `resume()` | Sau navigation xác nhận đích, xóa cache tọa độ UI/map/combo/hero và ảnh nhận dạng; giữ `_initial_trained`, bộ đếm phiên và cờ reward. Vào RECOVERING, phải đọc ảnh mới. Từ chối nếu còn thao tác chưa đối soát. |
| `reset_after_reload()` | Hủy input/trạng thái trận cũ không còn đáng tin; giữ startup flag và thống kê; reset cache wall đúng module; vào RECOVERING/UNKNOWN. |
| `invalidate_after_popup()` | Popup chỉ đóng bảng thì phân loại lại, giữ pending spell cùng cast_index/ảnh mốc, reward_generation, hero/tactics và bộ đếm; không dùng reset reload cho mọi popup. |

`RunCoordinator` dùng RLock cho tick/popup/navigation và khóa riêng cho pending request. Request có thể đến trong batch hoặc wall mà không phải chờ lấy khóa input. Không có vòng tick thứ hai hoặc thread input của module. Callback recovery trong tick được gọi lại trên cùng thread; tick lồng bị từ chối. Cô lập giữa worker vẫn do BotSession/process spawn hiện có; không thêm singleton/coordinator chia sẻ giữa serial/process.

`request_switch(target, reason)` chỉ nhận module đã đăng ký. Giữ pending qua trận, modal, train, collect, wall, batch, spell/ability chưa đối soát và reload. Yêu cầu mới đến khi navigation đang chạy không bị xóa nhầm; yêu cầu trùng đích đã xác nhận được tính là đã đáp ứng. Khi chưa có navigation callback, giữ pending và đứng tại Home, không giả vờ chuyển module. Callback thất bại/không trả True thì dừng, giữ request và không tick đích. Runtime GĐ2 chỉ đăng ký main; builder/hybrid tiếp tục bị chặn trước ADB.

### Điểm nhường và bảo toàn main

- Kiểm tra callback ngay trong `_state_home`, trước cả Attack cache lẫn Attack vừa nhận diện. Khi có request, xác nhận màn hình trước, hoàn tất startup train nếu còn cần, rồi giữ HOME để bàn giao; không đợi engine quan sát enum HOME sau một tick đã mở trận.
- Thứ tự giữ như cũ: Quick Train đầu phiên → COLLECT → hậu xử lý wall → HOME mở trận tiếp. Wall được inject vào main và chạy trong cùng tick thay cho engine kiểm tra FarmState. Trước wall/handoff phải có ảnh HOME mới; sau wall đã tương tác phải đọc ảnh mới và kiểm tra panel đã đóng. Không chạy wall khi event mode hoặc đang retry Attack; request pending vẫn có thể nhường sau một Attack bấm hụt nếu đã xác nhận lại Home.
- Không nhường trong train/collect/result, modal/reward, input batch, xác nhận nâng tường, spell pending hoặc ability group pending. `_in_tick` bao trùm cả batch, wall và đối soát. `blocks_handoff` của wall kiểm tra purchase/Gems/list/Upgrade More/Add Wall; classifier cũng chặn bảng reward, confirmation và Quick Train Use/Save Army còn mở, kể cả khi nút Home vẫn nhìn thấy.
- Không thay thuật toán loot/perimeter/deploy, spell recovery, hero abilities hoặc cách chọn event rewards. Chỉ thay cách sở hữu input, điểm bàn giao, xác nhận recovery và chờ. Suspend không xóa tiến độ; chỉ hủy dữ liệu trận sau reload hoặc sau khi đã kết thúc và nhường an toàn. Quick Train không chạy lại khi resume/reload vì giữ `_initial_trained`.

### Recovery và stop

- Engine không import/so sánh FarmState nữa; tick/status/halt/reset đi qua coordinator active. Connection lost/Try Again và popup reload reset đúng active; popup dismiss chỉ invalidate active. Main inactivity heuristic cũ chỉ áp dụng trong ngữ cảnh main đã nhận diện, không áp dụng cho builder hoặc trạng thái UNKNOWN.
- Reload không gán HOME. Main phân loại ảnh mới: Home → hậu xử lý COLLECT (hoặc RESULT nếu còn kết quả cần ghi nhận); scout → LOOT_CHECK; battle → BATTLE_WAIT, không phát lại deployment không rõ kết quả; result → RESULT; menu → FIND_MATCH. Modal trận trả về handler battle/reward; màn không xác định chờ có giới hạn 30 lần rồi halt riêng phiên, không tự chọn main/làng đích.
- Các wait trong engine/farm/wall và ADB tap/swipe/key/wait-template dùng stop_event. Farm unwind ngay khỏi chờ khi stop; wall bỏ vòng đối soát/cleanup khi đã dừng. ADB kiểm tra stop trước input và kiểm tra lại tap_many sau chuẩn bị script. Không gửi batch mới sau stop. Shell batch đang thực thi vẫn phải kết thúc/timeout; không tuyên bố cắt tức thì giữa batch đã gửi.
- Không sửa license, worker hoặc session lifecycle; giữ kiểm tra license trong process con, watchdog/stop Event, spawn/Queue/status/done/exited. Không chia sẻ mutable runtime hoặc ADB controller giữa serial.

### File GĐ2

- Mới: `cocmagic/village_module.py`, `cocmagic/run_coordinator.py`, `tests/test_run_coordinator.py`.
- Sửa: `cocmagic/bot_engine.py`, `cocmagic/modules/farm_module.py`, `cocmagic/modules/wall_module.py`, `cocmagic/adb_controller.py`.
- Cập nhật harness regression: `tests/test_connection_recovery.py` (kỳ vọng RECOVERING thay HOME, stop không tap) và `tests/test_farm_regressions.py` (engine qua coordinator, wall gate thuộc main).
- Báo cáo: file progress này. Không bật builder/hybrid hoặc camera; fake module/ADB/navigation chỉ nằm trong test.

### Kiểm chứng

- Lượt tích hợp trước bổ sung cuối: `python -m unittest discover -s tests -q`: **263 test, 53.342s, OK, exit 0**, gồm 30 test GĐ2 và 1 test planner ngoài phạm vi, không skip/failure/error.
- Lượt nghiệm thu tích hợp sau bổ sung stop/bảng Quick Train và xác nhận wall từ crop thật: `python -m unittest discover -s tests -q`: **268 test, 51.911s, OK, exit 0**, gồm 35 test GĐ2 mới, 232 test đã có ở GĐ1 và 1 test planner ngoài phạm vi. Không skip/failure/error. Phủ farm/event/wall/spell/hero/recovery, capture/burst/confirmation, worker/session, GUI/settings và license. Log: `diagnostics/dual_village_gd2/regression-tests-final.log` (gitignored).
- Rà soát cuối bổ sung guard stop ngay trước/sau suspend, tránh gọi navigation nếu người dùng dừng đúng điểm bàn giao. `python -m unittest discover -s tests -p test_run_coordinator.py -q`: **36 test, 4.804s, OK, exit 0**; log `diagnostics/dual_village_gd2/coordinator-tests-final.log`. Thay đổi cuối chỉ ở coordinator/contract test, không sửa chiến thuật hoặc các nhóm đã đạt tích hợp; không chạy lặp toàn bộ khi focused check đã phủ thay đổi này.
- `python tools/check_assets.py`: **ALL CHECKS PASSED, exit 0**. Phạm vi vẫn chỉ là import/asset checks cũ, không phải nghiệm thu builder vision. `git diff --check` đạt; warning chuyển LF/CRLF không phải lỗi whitespace.
- Các lỗi harness ở lượt đầu (halt đặt trước tick, ghép crop reward/wall nhầm kích thước) đã được sửa; không dùng kết quả lượt lỗi để báo đạt. Fake builder/navigation không phải implementation hoặc kiểm chứng game thật.

### Giới hạn và đầu vào giai đoạn sau

GĐ2 hoàn thành phần mã và kiểm chứng offline theo kết quả ở trên; chưa chạy main trọn trận hoặc chuyển hai làng trên game thật với mã GĐ2. Không có BuilderFarmModule, VillageNavigator, star reader, camera backend, scheduler/runtime hoặc hoạt động builder/hybrid thật. Nhận diện của main sử dụng asset hiện có và các modal đã biết; classifier hai làng đầy đủ/unknown modal và popup builder cần dữ liệu GĐ4/GĐ7 đã liệt kê ở baseline. Inactivity khi startup UNKNOWN cần ảnh/handler được kiểm chứng, không bấm chỉ vì nền tối.

GĐ3 tiếp tục từ contract này để thêm camera và vô hiệu hóa toàn bộ cache tọa độ liên quan. GĐ4 phải cung cấp navigation chỉ trả True sau xác nhận làng đích, chạy đồng bộ dưới input lock; GĐ5 cung cấp module builder thật theo contract và chỉ mở availability sau nghiệm thu. Không tạo fake builder trong runtime để mở mode sớm.

## GĐ3 — camera thật và tích hợp có kiểm soát

Ngày thực hiện: 08/10/2026, UTC+7. Giữ toàn bộ thay đổi GĐ1/GĐ2 có sẵn và `CocMagic_Release.zip` untracked; không commit/push/deploy, không sửa cấu hình cá nhân hoặc mở builder/hybrid. Không có AGENTS.md áp dụng. Đã đọc plan/prompts/baseline/progress, xác nhận contract GĐ2 từ mã coordinator/farm và chạy baseline mới **269 test, 71.833s, OK** (`diagnostics/dual_village_gd3-baseline.log`).

Chi tiết backend/hợp đồng/tọa độ/thời gian và từng bằng chứng: [dual-village-camera.md](dual-village-camera.md). Mã mới `cocmagic/camera_backend.py`, `camera_controller.py`; sửa `adb_controller.py`, `battle_planner.py`, `attack_tactics.py`, `modules/farm_module.py`. Test mới `tests/test_camera_controller.py`, fixture có nguồn/transform trong `tests/fixtures/dual_village/camera/`. README và progress cập nhật; không sửa coordinator/GUI/license/settings/availability trong GĐ3.

### Hợp đồng GĐ2 được giữ

Camera chạy đồng bộ bên trong tick, cùng quyền sở hữu input của active module và coordinator; không có vòng input nền. Quick Train/wall/reward/hero/spell/yield vẫn theo contract GĐ2. Không dùng enum HOME để cho phép gesture. Camera chỉ chuẩn bị sau đối thủ đạt loot và trước chọn quân; chưa chứng minh selection hoặc gặp modal/scene đổi thì dừng camera/recovery. Callback chỉ hủy geometry/vision map; giữ HUD/combo/portrait, cast index, hero abilities và startup flag. Reload hoặc chuyển scene vẫn cần ảnh mới, không tự gán làng/khung nhìn chuẩn.

### Hành vi đã có

- Pan trả boolean input/release; CameraController yêu cầu ảnh mới ổn định và biến đổi map đúng hướng. Zoom dùng protocol B hai slot trong một script, không phải hai swipe. Backend kiểm tra raw axes, viewport/rotation, permissions và contact đang hoạt động mỗi lần; hỗ trợ hẹp MuMu Android 15 đã thử.
- SUCCESS/UNCHANGED/ERROR/UNSUPPORTED/STOPPED tách rõ. Có giới hạn operation/capture, zoom-limit suppress, budgets chuẩn hóa/chuẩn bị; script có trap release và host finally cleanup bypass Stop. Không có fallback Ctrl+wheel/focus desktop.
- Camera epoch tăng trước gesture hoặc khi thấy ngoại cảnh đổi; invalidates screenshot/template positions và mọi plan/tactics/confirmed/hero entry/hotspot/spell targets. Guard epoch/HUD chặn tọa độ cũ trước input; không áp affine để dịch HUD/map targets.
- Tracked planner chỉ dùng geometry mới hoặc reference có chứng nhận; không fallback hình thoi theo resolution. Cạnh hull bị crop qua HUD không tạo điểm giả nếu không có hỗ trợ đỏ. Pan lên rồi quét lại các đoạn cạnh dưới; pan-limit dừng lặp. Điểm dưới còn thấy vẫn cần count giảm trước batch.
- `camera_auto_adjust=false` giữ mặc định và đường legacy/revision=0 của main. Bộ main regression kiểm tra loot/perimeter, selected counts, burst/event, spell/hero, recovery, wall, coordinator/session, settings/UI và license. Camera bật vẫn là chế độ phát triển, có thể bỏ đối thủ khi không đo được geometry/backend.

### Kiểm chứng game thật

MuMuManager xác định Android Device-1 đang chạy ở `127.0.0.1:16416`; ADB ban đầu trống, đã connect đúng endpoint này, không scan/start emulator. Physical 900×1600; screencap landscape **1600×900**, Android 15.0, SM-A5560. Shell input group cho phép `sendevent`; Xiaomi Touchscreen raw axes 900×1600, viewport rotation=1. Ảnh native/log/harness ở `diagnostics/dual_village_gd3/`.

- Home: pan dy **-57.64 px**, pinch scale **.86303**; zoom tiếp tại limit identity, repeat không gửi input. Không dùng exit code Android thay cho xác nhận camera.
- Practice Flying Circus: pinch scale **.66741**, pan dy **-165.90 px**, HUD giữ vị trí và số quân không giảm trong camera. Kéo lên cho phép point cạnh dưới từ ảnh mới tại **(952,644)**: probe **10→9**, rồi batch hai quân **9→7**. Result ghi đúng x3 quân đã dùng; Return Home có ảnh. Một số zoom/pan tiếp đạt limit, toàn bộ đỉnh đáy vẫn sát HUD; không báo đã kéo được mọi điểm đáy.
- Practice Bowling with Witches: selected drag dy **-211.02 px**, count **5→5**, damage **0%**. Chưa suy các card/scene khác; runtime vẫn từ chối chọn quân/unknown, kèm nhận diện frame trắng native trước gesture.
- Stop: raw backend đã submit script và chạy cleanup, trạng thái STOPPED; `dumpsys input` raw/cooked pointerCount=0. **Ảnh trước đã có popup thiết bị khác kết nối**, nên mẫu này chỉ chứng minh cleanup raw, chưa chứng minh Stop giữa chuyển động camera game. Đã thêm guard modal và test chặn; để nguyên popup, không reload tranh phiên. Không còn bot/QA worker gửi input.
- Đã hash và decode lại video camera **635 frame** tuần tự tới EOF, xem 4/13/20s và sheet GĐ0. Video chứng minh zoom/pan/HUD nhưng không ghi giao thức input; không dùng tọa độ video có viền làm ADB.

Fixture mới ~5.8MB: 4 frame map JPEG quality 94 che resource HUD, 5 bar crop PNG và 1 crop modal. Manifest có parent/output hash, serial, dimensions và phép biến đổi; tất cả là `transformed_test` từ native ADB, không gọi chúng là native nguyên bản. Synthetic HUD noise/composites được ghi rõ trong test/README.

### Kiểm thử và giới hạn nghiệm thu

Nghiệm thu mã cuối: `python -X utf8 -m unittest discover -s tests -q`: **298 test, 94.049s, OK**, exit 0, không skip/failure/error (`diagnostics/dual_village_gd3/regression-tests-final-verified.log`). Có **29 test camera mới** cộng baseline 269 test. Focused camera trước đó: 29 test, 9.351s, OK. `python tools/check_assets.py`: ALL CHECKS PASSED; `python -m compileall -q cocmagic tests/test_camera_controller.py` và `git diff --check` đạt. Warning LF/CRLF không phải whitespace failure. Lượt chỉnh guard batch cuối có NameError do đặt kiểm tra single-tap vào nhánh batch; đã sửa đúng nhánh, test event 14 ca đạt rồi toàn bộ 298 test đạt. Không dùng lượt lỗi làm bằng chứng đạt.

**Chưa đánh dấu toàn bộ GĐ3 hoàn thành**: chưa chạy vòng main multiplayer qua engine/coordinator từ lọc loot tới result, chưa hai serial thật đồng thời, chưa Stop lúc camera game đang chuyển động không modal. Pinch/Home/Practice/drop ở cạnh dưới đã có bằng chứng thật; các khoảng trống mới không phủ nhận bằng chứng này nhưng vẫn chặn bật camera mặc định. Các backend/resolution/rotation khác không được công bố hỗ trợ. Đầu vào GĐ4: dùng CameraResult và revision, xác nhận lại map/đích từ ảnh; không suy normalize là chứng nhận hình thoi hoặc dùng tọa độ video. Đầu vào GĐ5 vẫn cần planner/army/hero/stage2 chuyên biệt cho builder.

## GĐ4 — classification, navigation, thưởng sao và xe

Ngày 08/10/2026 (UTC+7). Giữ các thay đổi GĐ1–GĐ3, settings/license/instances và `CocMagic_Release.zip`; không commit/push/deploy, không mở builder/hybrid, không thêm vòng train. Chi tiết API, giới hạn và probe: [dual-village-navigation.md](dual-village-navigation.md).

- Mã mới: `builder_screen_reader.py`, `village_navigator.py`, `builder_rewards.py`, `tools/dual_village_probe.py`. Home cần anchor riêng từng làng cùng HUD chung; modal/unknown/loading chặn input. Navigator chạy đồng bộ dưới lock, dùng camera GĐ3 tìm thuyền và xác nhận hai ảnh đích; không giữ tọa độ qua camera/scene. Callback cho coordinator đã có, engine main tiếp tục đường cũ; nối hai module ở GĐ6.
- `StarBonusObservation` có AVAILABLE/CLAIMABLE/COMPLETE/UNKNOWN, timestamp/region/progress/capture IDs. COMPLETE chỉ sau hai capture mới độc lập ổn định, đúng builder Home, nút/vùng sao rõ. OCR x/y strict chỉ hiển thị; `0/y` có sao vẫn AVAILABLE, không cố định y. None, lặp ảnh, loading, modal, che riêng vùng sao, che nút, sao bay, main/result và mâu thuẫn đều không thành COMPLETE.
- Thưởng: title + sao lớn + bảng xanh + nút đúng + builder HUD; tap một lần, đợi đóng, đọc lại từ cặp mới. Còn sao trả AVAILABLE, bảng không đóng không replay. Xe: vị trí từ ảnh hiện tại, xác nhận title/close, phân biệt enabled/disabled bằng template và màu; tap Collect một lần, đối soát counter/bar + disabled ổn định rồi đóng và xác nhận Home. Empty/defending không chờ trận; hết ngân sách hoặc tap không đổi báo chưa đối soát, không lặp vô hạn.
- Asset audit có xem hình/kích thước/ngôn ngữ; poster `Night_Village.png` và nút chung không được dùng làm bằng chứng Home. Asset mới là lossless native crop; reuse/video/font-generated được phân loại riêng trong `assets/dual_village/manifest.json`. Fixture/receipt ở `tests/fixtures/dual_village/navigation/`, gắn vào manifest GĐ0 qua `additional_evidence_modules` mà giữ nguyên lịch sử khảo sát.

### Kiểm thử và thiết bị

- Baseline đầu GĐ4: **298 test, 76.671s, OK**, `diagnostics/dual_village_gd4-baseline.log`. Nghiệm thu mã cuối: **336 test, 167.373s, OK, exit 0**, `diagnostics/dual_village_gd4/regression-final.log`; thêm 38 test image/transaction/OCR. Asset checks, compileall và whitespace check đạt. Lỗi OCR/generic modal ban đầu đã sửa và chạy lại targeted trước full; không có lỗi còn mở trong bộ kiểm thử.
- Ảnh native **1600×900**, **English**, serial **127.0.0.1:16416**, MuMu đã kiểm chứng GĐ3. ADB còn alias `emulator-5556`; không thử hai serial độc lập, không scan/connect mới. Screenshot/input thật; không mock navigator/camera/reader/rewards trong vòng live.
- Vòng cuối: main ban đầu lệch/boat không an toàn → **1 pan + 1 boat tap** → hai ảnh xác nhận builder. Reader xác nhận COMPLETE bằng hai capture mới. **1 pan tìm xe**, mở đúng `Elixir Cart`, hai ảnh empty/disabled, tap close, xác nhận builder Home. Cố ý pan builder để che thuyền, navigator tìm lại → **1 pan + 1 boat tap** → hai ảnh main. Probe cuối xác nhận `main_home`, language `en`; không có bot/QA worker tiếp tục input.
- Native receipt, capture IDs, monotonic timestamps, SHA-256 và export JPEG: `navigation/live-receipt.json`. Raw log/PNG/harness ở `diagnostics/dual_village_gd4/`. Vòng live không Find Match/Find Now hoặc thả quân. Khảo sát trước đó chỉ mở/đóng menu Attack hai làng. Các lần đầu gặp guard camera/console encoding được ghi trong tài liệu, không tính là thành công.

### Nghiệm thu còn thiếu

Tài khoản thử đang hết sao/cooldown, nên **chưa có native AVAILABLE/CLAIMABLE/reward lặp tiếng Anh hoặc thu tiền thật**. Test positive các trạng thái đó dùng composite trên canvas native, art video Việt/asset cũ và text English render bằng font; manifest ghi rõ không live verified. Chưa có xe native đang phòng thủ, storage đầy/thu một phần mà Collect vẫn enabled; cần thêm receipt handler cho trường hợp nút còn enabled. Battle/result native trong fixture là main Practice GĐ3, chưa phải builder/stage2. Resolution/ngôn ngữ khác và modal chuyên biệt cần thêm profile/handler; dữ liệu lạ dừng ở UNKNOWN/MODAL.

GĐ4 đã có implementation và kiểm chứng chuyển làng/xe trống thật; chưa đánh dấu nghiệm thu toàn bộ thưởng và xe có tiền. GĐ5 bổ sung train và native battle; GĐ6 nối coordinator/lịch/runtime; GĐ7 tích hợp recovery/multi-instance. Giữ availability và camera default như trước.

## GĐ5 — train builder độc lập

Ngày 08/10/2026, UTC+7. Giữ thay đổi GĐ1–GĐ4, dữ liệu/license/instances và archive có sẵn; không commit/push/deploy. Không có AGENTS.md áp dụng. Đã đọc plan, quy tắc chung, baseline/progress, contract/coordinator GĐ2, camera GĐ3 và navigation/rewards GĐ4 trước khi sửa. Baseline mới: **336 test, 208.611s, OK**, log `diagnostics/dual_village_gd5/baseline.log`.

### Mã và contract

- `modules/builder_farm_module.py`: vòng thật Home/hậu xử lý → setup → menu/tìm trận → camera/triển khai/kỹ năng → chuyển khu/result → thưởng/xe. Engine đăng ký module builder riêng qua coordinator, không khởi tạo main farm/hero/wall khi chọn builder. Banner không đọc trường main đang để nháp. Chưa thêm scheduler/runtime hybrid GĐ6.
- `builder_vision.py`: profile English 1600×900, Choose Army, menu x1, nhãn camp và chân dung riêng, trạng thái undeployed/deployed/dead/unavailable/unknown, skill ready/used/charging. Không dùng x0/depleted của main. Đọc vị trí mới khi số ô đổi; tìm chân dung tướng toàn thanh khi white cooldown làm đứt contour. Health frame tướng cần cạnh ngang, không suy từ màu cỏ phía sau ô.
- Setup chỉ sửa ô sai có nhận diện và nút remove đúng; xác nhận bỏ/thêm rồi mới tiếp tục. Kiểm tra dấu hoàn tất cả Starting/Reinforcements; bỏ placeholder khóa. Cache setup đã xác nhận giúp không mở Choose Army mỗi trận; menu chính được kiểm tra lại trước Find Now. Combo đổi thì quay về sửa. Reload/resume bỏ cache này. Troop chưa mở/không rõ/hết ngân sách báo lỗi hữu hạn.
- `builder_tactics.py`: around phân tán góc/cạnh; single_point dùng một điểm đã được game nhận. Mọi thả quân có receipt, điểm từ chối bị loại, cap retry theo ô. Dùng geometry hiện tại: planner tracked GĐ3, đoạn biên đỏ mảnh/gấp khúc riêng builder, hoặc footprint cấu trúc nhìn thấy cho khu hai không có biên. Không dùng diamond/tọa độ video làm input. Không có đủ bằng chứng thì không bấm map.
- Kỹ năng Rồng con theo camp ID, delay mặc định 1 giây từ receipt triển khai và READY thật; ghi attempt trước tap, chỉ tăng metrics khi thấy USED. Ledger giữ qua khu hai. Tướng dùng thanh nạp/white cooldown, khoảng tối thiểu 8 giây và READY thật; không Warden delay. Chết ngay sau tap được ghi cảnh báo/`unconfirmed_abilities`, không ghi skill thành công hoặc bấm lại.
- Khu hai cần HUD chuẩn bị xuất hiện lại được xác nhận sau giao tranh, quét lại survivors/reinforcements/hero/điểm/skill. Không dùng 100% làm result. Builder result cần Total Damage + Return Home. Result làng khác không tăng số trận builder. Return và Find Now không replay nếu màn cũ chưa đóng.
- Timeout builder riêng: chuẩn bị 75s, toàn trận 540s, nhận diện/chuyển khu 35s, không tiến triển 90s; đọc thanh quân lỗi thoáng qua và geometry chưa rõ có ngân sách riêng. Watchdog đọc cả glyph timer: quân/damage đứng yên khi game vẫn đếm ngược không phải kẹt. Stop chặn input kế tiếp; generation đổi khi reload/popup hủy chuỗi cũ. Reload bỏ cache trận/setup/bonus, classify lại. Popup thường giữ ledger đã dùng, bỏ map.
- `can_yield` chỉ sau hậu xử lý và cặp Home mới ổn định, ngoài input/modal/tick. Metrics theo contract gồm tìm trận/kết quả/khu/deploy/skill/thưởng/xe/retry/recovery/uncertain. Coordinator thêm bonus state/stage/can_yield cho GĐ6. COMPLETE chỉ là trạng thái thưởng; builder-only tiếp tục.
- GĐ4 được bổ sung receipt resume bảng xe đang mở, native cart bị resource icon che, native “You are being attacked!”, và tìm lại từ Home mới sau gesture đã release nhưng settle timeout. Không tái dùng tọa độ gesture lỗi. GĐ3 camera mặc định vẫn tắt; main farm/deploy policy giữ nguyên.

### Bằng chứng và kiểm chứng

Video train GĐ0 đã đối chiếu lại qua contact sheets: chọn combo, triển khai/kỹ năng theo ô, chuyển khu và về làng. Runtime dùng ảnh ADB native, không tọa độ video. Các crop mới có parent/output SHA-256 trong `assets/dual_village/builder/manifest.json`; fixture chọn lọc có nguồn và mask rõ trong `tests/fixtures/dual_village/builder/manifest.json`.

Bản tóm tắt receipt live giữ trong `tests/fixtures/dual_village/builder/live-receipt.json`, kèm hash nguồn, metrics, map input theo khu và kiểm tra độc lập sau Stop. Manifest GĐ0 thêm entry GĐ5, giữ các quan sát lịch sử. Không đưa toàn bộ ảnh trận/tên tài khoản từ diagnostics vào repo.

Thiết bị: **127.0.0.1:16416**, MuMu Android 15, English 1600×900. `emulator-5556` là alias cùng thiết bị, không tính hai máy. Probe chạy module/input/vision thật, trace và ảnh nằm trong ignored `diagnostics/dual_village_gd5`; không có fake builder trong runtime.

| Nhánh | Mã/offline | Live đã quan sát |
|---|---|---|
| Setup đúng, ô khóa, tiếp viện | Có kiểm tra trước/sau, tối đa 16 sửa đổi; ô vừa bỏ phải được lấp trước khi sửa ô khác | Native Choose Army 6 chính + 1 tiếp viện + placeholder; không sửa khi đúng. Chủ động đổi tiếp viện sang Bomber, `live-setup-stop` tự nhận/sửa đúng ô đó về Rồng con. Reader độc lập sau Stop xác nhận cả 7 ô đúng và hai nhóm complete. around-14 chỉ mở setup một lần rồi giữ cache qua các Find sau. |
| around và hero | Có distribution/receipt/retry tests | `live-around-14`: 2 lần Find mới, 3 kết quả (1 trận tiếp quản từ phiên trước), 646.404s, 18 receipt deploy, 13 skill quân, 4 skill tướng, 3 thu xe, không halt, safe Home. Không gọi đây là 3 trận mới. |
| Một khu | Có result/khu tests | Các trận around kết thúc khu một, trả Home, thưởng COMPLETE, xử lý xe rồi tiếp tục Find. |
| single_point, không dùng tướng, hai khu | Có test semantics, hero skip, stage ledger | `live-single-8-timer`: **completed/safe_home=true**, 380.095s, 1 Find mới, 2 kết quả gồm 1 khôi phục; trận mới đủ 2 khu, 10 deploy, 7 skill, hero/reject/uncertain=0. Cả 6 ô khu một dùng một điểm; 4 ô khu hai dùng một điểm mới. Thuật toán không phục hồi giả skill cũ. `live-single-6` trước đó có 2 Find mới, cả hai sang khu hai, 21 deploy/14 skill/retry 1; hậu xử lý cuối lỗi Collect khóa nên không gọi phiên đó full-loop PASS. `live-single-7-restart` lỗi watchdog bỏ sót timer đã được sửa và phủ crop native/offline + live cuối. |
| Tướng Machine/Copter, thiếu/nâng cấp | Có native charge/cooldown + absent/gray/shifted-bar tests | Machine triển khai và kỹ năng có receipt ở around. Copter/bar khu hai có native và quan sát thủ công; chưa xác nhận kỹ năng Copter tự động. Thiếu/nâng cấp tướng thật chưa có mẫu; tắt dùng tướng được thử riêng. |
| Điểm bị từ chối | Có bounded retry/revision tests | `live-single-6` có 1 điểm bị từ chối rồi tìm lại thành công, không bấm lặp điểm đó; hai trận vẫn sang khu hai. Phiên này có lỗi hậu xử lý xe riêng đã nêu. |
| Thưởng sao | GĐ4 handlers + tests | COMPLETE native bằng cặp Home mới; vẫn tìm trận tiếp. Chưa có native AVAILABLE/CLAIMABLE/chuỗi thưởng trong cooldown hiện tại. |
| Xe tiền/trống/phòng thủ/Collect khóa | Có receipt/resume/close/disabled-balance tests | Native thu tiền: counter/bar đổi, Collect disabled, Home. `cart-debug/receipt.json` thành công; around-14 thu 3 lần. around-13 xác nhận xe đang phòng thủ + disabled và Home. Kho đạt 5,5M, xe còn tiền nhưng Collect disabled: single-7-restart xác nhận `success/returned_home/unavailable=true`, `collected=false`, không suy “xe trống” hoặc nguyên nhân từ màu thanh kho. |
| Stop/reload, kết quả bất ngờ | Có cancellation/foreign-result/reset/finite budgets tests | `live-stop-select`: chỉ Home Attack → Find → chọn camp, Stop chặn map tap tiếp theo; cancelled, không completed. `live-setup-stop` Stop ngay sau chọn Rồng con, không đóng bảng/tìm trận tiếp. Sau probe đã force-stop/start đúng package game; module mới phân loại lại trận đang có rồi Home bất ngờ, không cộng kết quả giả. Inactivity native cùng module được nhận/reload ở around-7 (recoveries=1). Reload callback giữa select/map và bỏ cache trong cùng tick chỉ kiểm chứng offline; không gọi force-stop là ca đó. |

Các phiên khảo sát đầu có halt do bóng nền/xe/biên/tướng/nhãn camp/survivor được giữ receipt lỗi. Không dùng tap thành công làm receipt nhận diện và không cộng các phiên lỗi thành vòng train hoàn chỉnh. `tools/builder_farm_probe.py` ghi `completed`, `cancelled`, `budget_exhausted`, `safe_home` cho các phiên mới.

### Nghiệm thu mã cuối và availability

- `python -m unittest discover -s tests -q`: **405 test, 219.832s, OK, exit 0**, không skip/failure/error. Log `diagnostics/dual_village_gd5/final-tests-verified.log`. So với baseline 336: thêm 65 test builder, 3 test navigation/cart và 1 test CLI; các ca GUI/availability cũ được cập nhật theo mode đã mở. Phủ hồi quy main farm/deploy/spell/hero/wall/recovery, camera/coordinator, settings/GUI/CLI/session/license.
- Focused builder cuối: **65 test, 19.011s, OK** (`builder-tests-final.log`); GUI/settings/CLI: **20 test, 13.863s, OK** (`settings-gui-cli.log`). Đây là kiểm thử offline, không gọi GUI/CLI worker đã đánh trọn trận thật. Vòng live dùng cùng BuilderFarmModule, reader/ADB/camera/navigation/rewards thật qua probe.
- Lượt full trước: 405 test/294.511s có 1 failure ở test mới dùng ảnh ghép GĐ4 vẫn còn thông báo xe trống, không phải bằng chứng đạt. Đã thay bằng fixture native xe còn tiền/Collect disabled, kiểm tra tiền đề không có `cart_empty`; test riêng **1 test/2.371s OK**, rồi chạy lại toàn bộ đạt kết quả ở trên. Không sửa mã bot để chiều ảnh ghép sai.
- `python tools/check_assets.py`: **ALL CHECKS PASSED**, chỉ phạm vi import/asset cũ. Hash/decode asset và fixture builder được kiểm trong test riêng; hash nguồn/receipt live cùng Stop/single-point assertions cũng đã đối soát. Compileall và `git diff --check` đạt; kiểm tra whitespace các file GĐ5 mới đạt. Warning LF/CRLF không phải failure.
- `AVAILABLE_RUN_MODES` mở **main/builder**; GUI Start/Start All và CLI dùng cùng validation. Builder không bị trường main đang để nháp chặn. `hybrid` vẫn từ chối với lý do GĐ6; camera tự chỉnh mặc định false. Không thay license, dữ liệu cấu hình cá nhân, archive, hoặc tạo bản phát hành.
- Game cuối ở Builder Home có ảnh mới; tất cả probe đã kết thúc và Stop Event được đặt. Không còn controller live gửi input. Main không hồi quy trong bộ test trên; **chưa chạy lại main multiplayer live** ở GĐ5.

### Giới hạn dữ liệu và đầu vào GĐ6

Đã kiểm chứng live các nhánh chính trên một tài khoản **6 ô chính + 1 tiếp viện**, Machine, English 1600×900/MuMu Android 15. Không suy các fixture biến đổi thành tài khoản thật có ít ô/tướng vắng/nâng cấp. Camp 8, thiếu/nâng cấp tướng native, kỹ năng Copter tự động, AVAILABLE/CLAIMABLE/chuỗi thưởng sao native, thu một phần mà Collect còn enabled, và zoom tự động trong trận builder cần dữ liệu bổ sung. Reload callback giữa select/map trong cùng tick được phủ offline; force-stop/start game và inactivity reload là các kiểm chứng live khác đã tách ở bảng. Chưa thử hai thiết bị độc lập hoặc profile ngôn ngữ/resolution khác.

Builder-only đã có vòng lặp thật, ledger/receipt/timeout riêng, trạng thái thưởng, metrics và điểm nhường sau Home/hậu xử lý cho GĐ6. GĐ6 tiếp tục nối scheduler/hybrid và runtime store; GĐ7 hoàn thiện recovery/multi-instance tích hợp, không cần dựng module giả. Hướng dẫn cấu hình, timeout, policy và probe: [dual-village-builder.md](dual-village-builder.md).

## GĐ6 — hybrid, lịch UTC+7 và runtime từng serial

Thực hiện đêm 08–09/10/2026, UTC+7. Đã đọc plan, quy tắc chung, baseline/progress và đối chiếu module GĐ5 thật trước khi sửa. Giữ toàn bộ thay đổi GĐ1–GĐ5 đã có, cấu hình cá nhân/license và archive; không commit/push/deploy. Không có AGENTS.md áp dụng. Hướng dẫn vận hành: [dual-village-schedule.md](dual-village-schedule.md).

### Hành vi và quyết định

- `hybrid_coordinator.py` kế thừa coordinator GĐ2, đăng ký **FarmModule và BuilderFarmModule thật** qua engine. Một worker sở hữu input; không có scheduler worker riêng. Startup chọn builder, xác nhận/chuyển từ main Home; restart trong trận main được phân loại và hoàn tất trước handoff. Builder đang trong trận dùng recovery GĐ5.
- Hook Home của builder chạy trước setup/Attack. CLAIMABLE được handler GĐ4 nhận và đọc lại. AVAILABLE tiếp tục nhiều trận; `0/7`, `0/8`, `4/8` đều không bị coi là hết lượt. COMPLETE chỉ từ reader hai ảnh mới ổn định; kiểm tra/thu xe, đọc lại bonus rồi về main. Nếu sau bảng xe/nhận thưởng còn sao thì tiếp tục builder. Builder-only giữ hậu xử lý cũ và train tiếp khi COMPLETE.
- Khi lỗi/UNKNOWN có 3 lần đọc với cooldown 15 giây monotonic; có budget cả chuyến mặc định 1800 giây/12 kết quả và kiểm tra tiến độ không đổi. Thưởng nhận thêm là một bằng chứng tiến triển, kể cả OCR x/y giống lượt trước. Chạm budget trong trận không bấm thuyền/back; chờ Home. Fallback chỉ khi xác nhận Home/main; ghi lỗi/chưa hoàn thành và retry hữu hạn, không sửa bonus thành COMPLETE. Không xác nhận được màn hình thì dừng riêng instance.
- Lịch wall clock UTC+7, ZoneInfo thiếu tzdata fallback cố định +07:00, không dùng timezone Windows. Điều kiện `now >= cutoff` và chưa có valid check ngày hiện tại. Callback trước Attack của main poll lại sau tick dài. Startup sau mốc thỏa daily; trước mốc không tiêu daily; máy ngủ kiểm tra một ngày hiện tại. Dấu `last_daily_request_date` tách biệt valid check để retry buổi sáng đã cạn vẫn được cấp budget daily mới, nhưng UNKNOWN không được ghi ngày đã kiểm tra hợp lệ.
- `hybrid_runtime.py` lưu mỗi serial một file có hash tên, atomic tempfile/fsync/replace. OS lock giữ suốt phiên và kiểm tra thread sở hữu writer. Hai process cùng serial bị từ chối; serial khác không ghi đè nhau. Runtime lưu timestamp/state/progress/pending/retry/error, không lưu tọa độ trận. File thiếu/hỏng/sai schema log và phục hồi UNKNOWN; persisted COMPLETE không bỏ startup scan. Engine đóng writer trong finally.
- Mở hybrid cho GUI/CLI qua validation chung. Run hiển thị mode, làng đã xác nhận, lý do, sao/x-y nếu biết, lần đọc hợp lệ/lịch tiếp, pending/retry/lỗi. Runtime không vào settings. Main-only không khởi tạo hybrid runtime và builder-only không dùng lịch hybrid. Camera vẫn mặc định false.

### Sửa phụ thuộc được phát hiện trên game

Lượt probe đầu nhận được inactivity thật, reload đúng nút nhưng sau đó Home main bị UNKNOWN vì template profile chứa level cũ và mẫu Attack khác ảnh hiện tại. Bot hết timeout, ghi UNKNOWN/chưa hoàn thành và dừng riêng instance; **không tính lượt này thành thành công**. Raw receipt/log giữ ở `diagnostics/dual_village_gd6/live-cycle/` và `live-cycle.log`.

Đã thêm hai crop native có nguồn/hash vào manifest: viền profile không chứa chữ số level và biến thể Attack main hiện tại. Không hạ ngưỡng; vẫn cần portrait riêng làng + Attack + HUD chung, mẫu âm thiếu portrait/nút đơn/modal. Fixture `hybrid/main-home-level71.png` chỉ giữ 5 vùng HUD, che tên/tài nguyên/map và được ghi **transformed_test**, không gọi là native full frame. Popup inactivity không tự gán Village.BUILDER; status lấy làng từ ảnh hoặc navigation được xác nhận. Ảnh/asset mới giữ kích thước native, không tọa độ video.

### Kiểm chứng game thật

Thiết bị **127.0.0.1:16416**, English 1600×900, MuMu Android 15; `emulator-5556` là alias cùng máy, không tính hai instance thật. Probe dùng engine, hai module, camera/navigation/rewards/ADB thật; main có `auto_train=false`, `upgrade_walls=false`, `event_mode=false` trong settings riêng của probe, không sửa cấu hình người dùng và không giả tick thành công. Daily pass chỉ tiến wall clock riêng của probe, không đổi giờ Windows.

- `live-cycle-2`: **completed=true, 2 pass, 160.371s**, startup sau 15:30 thỏa ngày 08/10 và scheduled ở ngày probe 09/10 15:31. Native COMPLETE bằng hai ảnh Home mới; kiểm tra xe mỗi chuyến, 1 lần thu có receipt, lượt sau xe disabled/empty được đóng hữu hạn. Main giữ pending trong RECOVERING/COLLECT rồi nhường; 2 tick main thật, không Find/Attack mới ở hai làng, không claim thưởng native. Về main được navigator xác nhận.
- `live-final`, đúng mã nghiệm thu cuối: **completed=true, 2 pass, 149.155s, 8 tap**, 2 tick main thật. Startup thật ngày 09/10 khoảng 00:05 UTC+7 đọc COMPLETE nhưng `last_daily_check_date=null`, giữ lượt daily. Clock probe tiến sang 10/10 15:31: marker request có trước valid check, pending giữ tại COLLECT, sau Home mới chuyển builder; đọc COMPLETE mới ghi daily ngày 10/10, không replay ngày bỏ qua. Hai giao dịch xe success/returned_home, xe trống/Collect disabled, không giả đã thu thêm tiền; no attack/battle/claim mới. Final inspector độc lập xác nhận `main_home`. Stop đã đặt, writer đóng, không còn process probe/test gửi input. Receipt chọn lọc lưu hash mã nguồn cuối; runtime probe nằm riêng diagnostics.
- Bộ bằng chứng chọn lọc: [hybrid/live-receipt.json](../tests/fixtures/dual_village/hybrid/live-receipt.json), [fixture manifest](../tests/fixtures/dual_village/hybrid/manifest.json). Raw logs/images/runtime/receipt ở `diagnostics/dual_village_gd6/`, gitignored; không đưa thông tin tài khoản hoặc toàn bộ ảnh game vào bộ thay đổi.

### Kiểm thử và giới hạn

- Fake clock/contract cuối: **34 test, 3.358s, OK** (`hybrid-final-tests.log`). Phủ 09:00/15:29/15:31, startup đang train qua mốc, pending giữa battle/modal/wall và ngay trong tick dài, qua ngày/ngủ nhiều ngày, restart COMPLETE/trận main, UNKNOWN/retry/budget/fallback/Stop, reward xong vẫn còn sao qua nhiều result, runtime thiếu/hỏng, atomic failure, thread/process writer và hai serial độc lập. Có test hồi quy cạn retry buổi sáng vẫn giữ lượt daily; marker request không phải valid completion.
- Navigation/reward/cart focused: **22 test, 130.272s, OK** (`navigation-tests.log`). Bộ tích hợp trước sửa marker budget buổi sáng: **438 test, 237.172s, OK**, không skip/failure/error (`final-integration-tests.log`); nghiệm thu mã cuối được ghi bổ sung bên dưới.
- **Nghiệm thu mã cuối:** `python -m unittest discover -s tests -q`: **439 test, 244.926s, OK, exit 0**, không skip/failure/error (`acceptance-tests.log`). Phủ main farm/deploy/spell/hero/wall/recovery, camera/navigation/reward/cart, GĐ2 handoff, GUI/CLI/settings/session/license, builder-only và 34 test hybrid. So với 405 test GĐ5: thêm 34; test availability cũ được cập nhật theo hybrid đã mở. Không dùng lượt full trước hoặc các test có harness lỗi ban đầu để thay kết quả mã cuối.
- `tools/check_assets.py`: **ALL CHECKS PASSED**; compileall, hash/decode crop mới, cú pháp/whitespace file mới và `git diff --check` đạt. Warning LF/CRLF không phải lỗi. Asset gate vẫn chỉ kiểm tra phạm vi cũ, không thay bằng chứng nhận diện.
- Kiểm tra hình học **Tk thật** ở 980×840 và 880×680: Run page/canvas cùng chiều rộng 925/825, nội dung cuộn dọc, nút lưu được map; mode/hint/pending/lỗi và timestamp UTC+7 có dữ liệu. `gui-layout.json` là đo widget, **không phải screenshot/kiểm chứng trực quan**. Availability/start/CLI, save/profile và khóa khi chạy được bộ GUI regression kiểm tra.

Chưa có native AVAILABLE/CLAIMABLE/chuỗi thưởng mới trong lượt thử GĐ6 vì game đã hết sao; nhánh đó có test real-module với fake input/clock và fixtures GĐ4, không gọi là đã đánh chuỗi thưởng thật. Chưa hai thiết bị vật lý/serial độc lập chạy hybrid đồng thời, chưa visual QA riêng panel trạng thái mới hoặc live hybrid quay vòng main multiplayer. Các giới hạn GĐ3–GĐ5 về profile/ngôn ngữ/tướng/camera còn hiệu lực.

GĐ7 tiếp tục từ implementation này: recovery trong các giao dịch/chuyển làng, Stop/input đang thực thi, hai instance thật và kiểm tra trực quan Run. Khi có thưởng sao native mới, bổ sung chuỗi claim → còn sao → nhiều trận → hết sao → xe → main, giữ đầy đủ receipt; không sửa reader thành COMPLETE để vượt thiếu dữ liệu.

## GĐ7 — recovery, cô lập instance và giao diện quan sát

Thực hiện 09/10/2026, UTC+7. Đã đọc plan, quy tắc chung, baseline/progress và kiểm tra ba mode thật đã mở ở GĐ6. Giữ các thay đổi GĐ0–GĐ6 đang có, cấu hình cá nhân/license và archive; không commit/push/deploy. Áp dụng skill UI/UX cho focus, cuộn và trạng thái disabled, giữ bố cục Tk hiện tại. Phạm vi mã và offline đã triển khai; **chưa gọi toàn GĐ7 hoàn thành** vì chưa chạy được hai game độc lập đồng thời.

### Sửa lỗi và hành vi hiện tại

- Guard chung tại mỗi lần lấy ảnh ADB chặn mất ảnh/sai resolution, connection, inactivity và reload client trước khi rewards/cart/navigation hay module dùng ảnh. `RecoveryInterrupted` tháo chuỗi thao tác đang chạy, không nuốt lỗi rồi tiếp tục bằng tọa độ cũ. Reset cả cache main/builder **của serial đó**, camera revision, quân/kỹ năng/điểm thả và pending handoff; giữ thống kê và Quick Train đã khởi tạo. Handoff bị ngắt mở lại source module để phân loại, không để source treo ở suspended.
- Mất ảnh có tối đa 6 lần đọc; connection/inactivity tối đa 3 lần reload đến khi ảnh mới xác nhận màn dùng được; input lỗi tối đa 3 lần trong phiên. Không thấy nút retry thì không đoán vị trí, tối đa 6 ảnh rồi dừng riêng instance. Chờ 10 giây connection/4 giây inactivity dùng Stop Event; sau đó bắt buộc đọc lại. UNKNOWN lúc đang thả quân main hủy các điểm còn lại. Lỗi farm ngoài dự kiến dừng riêng instance thay cho Back/Okay rồi gán HOME. Main-only khởi động ở Builder Home chỉ dùng navigator sau khi xác nhận đúng làng; không reset mù về Main Home.
- Inactivity cần đồng thời hai anchor native `Anyone there?` và `Reload`, không dùng nền tối/chữ sáng. Connection/modal cụ thể có ưu tiên trước HUD, battle, reward và xe. Reader battle/thanh quân cũng từ chối modal. Bảng xe mất ở lần đọc lại trước Collect không được dùng nút cũ. Popup rate/open-link cần đúng response; bỏ nhánh bấm giữa màn hình.
- Mọi mode giữ OS lock theo serial trong suốt worker. Main/builder dùng store để giữ khóa, không ghi lịch hybrid; hybrid tái dùng cùng writer. Worker thứ hai bị từ chối không gửi CANCEL làm gián đoạn worker đang sở hữu input. Settings được deep-copy qua session/worker/engine; camera listeners, revision, thanh quân và ledger thuộc từng controller/module. Callback lỗi được log một lần đến khi phục hồi, không reset game; status bị buộc về serial của worker và event khác serial bị bỏ ở cả session/UI.
- Runtime vẫn tempfile/fsync/atomic replace. Windows giữ file tạm được retry tối đa 3 lần, tổng chờ thêm 0,15 giây, chỉ cho lỗi access/sharing tương ứng; lỗi disk khác dừng ngay. Ghi thất bại giữ bản cũ, xóa temp, đánh dấu chưa hoàn thành và dừng riêng instance trước Attack/xe tiếp theo.
- Reload hybrid đưa bonus về UNKNOWN/chưa hoàn thành, giữ budget chuyến và retry; startup đọc lại làng thực tế sau chuyển thuyền dang dở. Watchdog giữ giới hạn chuyến 1800 giây/12 kết quả, 4 lượt tiến độ không đổi, 3 lần UNKNOWN cách nhau 15 giây; fallback/retry 5 phút, tối đa 3 lượt. Chỉ về main sau Home rõ và navigation xác nhận đích. UNKNOWN/AVAILABLE bị watchdog chặn vẫn là chưa hoàn thành, không đổi thành COMPLETE, không ghi valid daily check từ UNKNOWN.
- UI có trạng thái chưa lưu/đã lưu/lỗi cụ thể, lưu chung cả hai làng và mode; radio mode cùng một biến. Chạy khóa cấu hình/save nhưng vẫn đổi tab, cuộn, copy log và Stop được. Status đến muộn không ghi đè “Đang dừng”. Log ghép fragment thành dòng, bỏ dòng trùng liên tiếp, giới hạn buffer/dòng. Lỗi scan host giữ các worker hiện tại và không spam cùng thông báo; scan hợp lệ chỉ dừng serial biến mất. License grace/expiry, Chạy tất cả/Dừng tất cả và đóng ứng dụng giữ lifecycle hiện có.

Các file chính: `cocmagic/recovery.py`, `adb_controller.py`, `bot_engine.py`, `ui_dialogs.py`, `builder_screen_reader.py`, `builder_vision.py`, `builder_rewards.py`, `camera_backend.py`, `camera_controller.py`, `run_coordinator.py`, `hybrid_coordinator.py`, `hybrid_runtime.py`, `modules/farm_module.py`, `modules/wall_module.py`, `bot_worker.py`, `session_manager.py`, `gui.py`. Thêm `tests/test_recovery_isolation.py`, bổ sung regression hiện có và `tools/dual_village_ui_probe.py`. Không thêm tính năng game ngoài kế hoạch.

### Ma trận recovery, Stop và nhiều instance

| Tình huống | Bằng chứng GĐ7 | Kết quả/giới hạn |
|---|---|---|
| Connection trong main/builder/chuyển khu/reward/cart/chuyển làng | Failure injection qua ADB guard và module/helpers thật, từng giao dịch riêng | Chỉ tap retry đã nhận diện; unwind trước input kế tiếp, xóa cache cả hai module cùng serial, actual village UNKNOWN. Chưa ngắt mạng thật ở từng màn. |
| Mất ADB hoặc loading trong deploy main | 6 ảnh lỗi, ảnh đúng resolution nhưng UNKNOWN, cache điểm/kỹ năng đang có | Không dùng điểm cũ; chỉ instance lỗi halt. Không tự gán HOME. |
| Reload trong handoff | Source đã suspend, reload trước navigation trả về | Hủy yêu cầu cũ, source được classify lại; hybrid giữ pending recovery/budget, không ghi COMPLETE. |
| Inactivity/nền tối | Native dark Home/battle/reward/cart âm; ghép hai anchor cho ca dương; popup native live | Nền tối không đủ. Live reload đúng một nút, status UNKNOWN/chưa hoàn thành rồi xác nhận Main Home mới. |
| Cart mất panel trước Collect | Hai lần đọc: đầu có nút, sau không có panel | Không replay nút Collect cũ, báo failure/không giả đã thu. |
| Stop tap batch | Injection trong command đang chạy, timeout và kill thất bại | Không gửi batch mới; kill đúng remote job qua pidfile riêng rồi CANCEL. Batch đã gửi có thể chạy tới khi command trả về/timeout. Cleanup không xác nhận thì báo lỗi và dừng. |
| Stop pan/pinch | Injection và native Stop sau khi command thật đã bắt đầu | Pan 0,698s; pinch 3,714s sau Stop, release xác nhận. Raw slot cleanup lỗi không được CANCEL che thành “đã release”. |
| Stop kỹ năng/modal/reward/cart/thuyền/chờ | Real-module injection và regression GĐ2–GĐ6 | Không follow-up input/receipt kỹ năng/claim giả. Chờ dùng Event. Chưa live Stop ở mọi loại modal hoặc trong trận GĐ7. |
| Hai worker khác mode/cấu hình | Hai process spawn, serial A builder/min_gold 123; B main/456, IO giả, module/guard/store thật | Input và status đúng serial. A mất 6 ảnh rồi dừng, B vẫn sống; hai runtime đọc lại đúng sau đóng writer. Đây không phải hai game thật. |
| Hybrid độc lập, writer/callback/runtime lỗi | Fake clock, hai coordinator, OS lock thread/process, atomic disk/share injection | Lịch/pending/cache không dùng chéo; không mất bản runtime cũ, callback không reset game; duplicate writer không CANCEL owner. |
| Camera/cửa sổ/focus | Backend ADB swipe + evdev slots theo serial, không có desktop fallback | Không phụ thuộc cửa sổ/focus, không có click chuột desktop. Pinch chỉ mở capability cho touchscreen/rotation/resolution đã probe; unsupported dừng nhánh camera. Mất game/capture/context chặn thao tác tiếp. |
| License/Chạy tất cả/Dừng tất cả/đóng app/scan thêm | Tk tests, hai profile khác mode, grace→expiry, cooperative close, scan lỗi/mất một serial/thêm serial | Grace giữ worker; expiry dừng tất cả có chủ đích. Scan host lỗi không dừng tất cả; scan hợp lệ mất A chỉ stop A. Close chờ worker và không tự terminate trước yêu cầu force-close hiện có. |
| Builder không tiến triển/UNKNOWN | Fake clock + module thật, unchanged progress, timeout, UNKNOWN/reload, runtime failure | Retry/budget hữu hạn, ghi chưa hoàn thành; chỉ fallback qua Home được xác nhận. UNKNOWN không thành COMPLETE. |
| Ba tab/cửa sổ nhỏ/focus/save/log | Tk thật, ảnh đúng window handle 980×840 và 880×680; test focus/save/disk failure | Tab xem được khi chạy, inputs khóa, instance khác chỉnh được; footer lưu luôn hiện, Run cuộn đến lỗi/pending/log, dòng trùng được gộp. |

Giới hạn Stop được hiển thị tại Run: command ADB thường/batch tối đa **15 giây**; screenshot **10 giây**; probe/pinch **5 giây mỗi command**. Cleanup có thể thêm **6–9 giây** gồm kết thúc remote job, raw slot release/CANCEL và finally worker. Không thể thu hồi những tap thuộc batch đã được Android nhận trước Stop; đã giảm batch từ tối đa 80 xuống **16 tap** và đọc ảnh giữa các nhóm. Không cam kết dừng tức thì. Nếu ADB mất hoàn toàn thì release chỉ là thử hữu hạn và báo **chưa xác nhận**. Không giữ phím desktop; Android keyevent hữu hạn, không gửi keyevent tiếp sau Stop.

### Kiểm chứng một game thật và giao diện

ADB ban đầu trống; lần kiểm tra sau có đúng **emulator-5556**, MuMu Android 15, English, ảnh thực tế **1600×900** (`wm size` physical 900×1600). Không scan/connect thêm cổng, không tính alias của cùng máy là thiết bị thứ hai. Probe sở hữu lease theo serial, dùng engine/guard/modules/ADB/camera/navigation/rewards thật, runtime riêng trong diagnostics, tắt train/wall/event của probe và không sửa settings cá nhân. Không Find/Attack/trận mới hoặc claim thưởng trong GĐ7.

- Lượt 1: nhận đúng inactivity native, tap Reload một lần; status bonus UNKNOWN, incomplete=true, actual village chưa xác nhận. Main Home được đọc lại. Navigator tiếp theo chưa có Home ổn định nên **completed=false**, 0 boat tap/0 camera; dừng sau 38,132s, release xác nhận. Giữ receipt lỗi, không gọi đây là vòng chuyển làng thành công.
- Lượt 2: **completed=true, 141,322s**, thử Stop thật trong pan/pinch trên Home bằng timer sau khi command input đã gửi; đo thời gian nêu trên. Tiếp đó Main→Builder (1 boat tap/1 camera), đọc COMPLETE từ **hai ảnh Home mới** không sao; 0 claims. Xe trống/Collect unavailable được đóng, `collected=false`, không giả thu tiền. Builder→Main (1 boat tap), final inspector xác nhận Main Home. Cuối probe Stop được đặt, release xác nhận và cả lease/runtime đóng.
- UI probe dùng phiên mô phỏng, file settings tạm, không ADB/license IO: chụp trực tiếp handle cửa sổ CocMagic, không phụ thuộc foreground. Đã xem ảnh ba tab ở 880×680, phần Run cuộn cuối và instance thứ hai; canvas/content cùng rộng 825, cấu hình hybrid đang chạy khóa, builder còn lại editable. Bộ 980×840 rộng 925 và có ảnh riêng. Lượt chụp bằng vùng desktop bị cửa sổ khác che đã bỏ, không dùng làm bằng chứng. Đây là visual QA giao diện thật với dữ liệu giả, không phải hai worker game thật.

Receipt chọn lọc không có ảnh tài khoản: [live](../tests/fixtures/dual_village/recovery/live-receipt.json), [UI](../tests/fixtures/dual_village/recovery/ui-receipt.json), [manifest](../tests/fixtures/dual_village/recovery/manifest.json). Raw log/ảnh/probe/runtime ở `diagnostics/dual_village_gd7/`, gitignored. Manifest ghi hash raw receipt/output và mã tại bàn giao; không giả hash bàn giao là hash của mọi phiên probe trung gian.

### Kiểm thử và giới hạn bàn giao

- Baseline tại đầu GĐ7: **439 test/292,968s**, 1 error ở child-process writer test do output Windows cp1252 được decode UTF-8. Đã thêm `-X utf8` cho child test; không thay license/runtime để né lỗi encoding.
- Lượt tích hợp trung gian: **463 test/507,079s, 2 failures + 2 errors**. Phát hiện hai assertion cũ về Stop/reset, status bị tính khi không có callback trong harness, và access denied tạm ở atomic replace. Đã sửa hành vi/test hợp đồng tương ứng và thêm ca Windows retry hữu hạn; không coi lượt lỗi là đạt.
- Focused mã cuối: recovery/isolation **26 test/20,924s OK**; hybrid/runtime **39 test/7,729s OK**; coordinator **36 test/16,677s OK**. UI/settings bổ sung license/close/scan: **26 test/24,582s OK**, gồm 3 ca thêm sau khi discovery của lượt full cuối đã bắt đầu. Lượt UI đầu thiếu status observer vì fixture tắt license card; sửa harness và chạy lại đạt, không sửa policy cấp phép.

- **Tích hợp mã cuối:** `python -X utf8 -m unittest discover -s tests -q`: **473 test/338,375s, OK, exit 0**, không skip/failure/error (`final-integration-tests.log`). Mọi mã sản phẩm cuối đã có trong lượt này. Sau khi discovery bắt đầu chỉ thêm 3 test lifecycle/license/scan, đã đạt cùng bộ UI 26 test ở trên; tổng danh mục hiện tại **476 test**, không cộng hai lượt trùng nhau thành 499 test.
- `python tools/check_assets.py`: **ALL CHECKS PASSED, exit 0** (`assets-final.log`); compileall và `git diff --check` đạt, cảnh báo LF/CRLF không phải failure. Asset gate chỉ kiểm phạm vi import/asset cũ, không thay bằng chứng nhận diện. `git diff --name-only -- data` rỗng: không thay dữ liệu cấu hình cá nhân/license được track. Lease live chỉ tạo lock, runtime probe nằm riêng diagnostics.

Giới hạn còn lại: **thiếu thiết bị thứ hai độc lập**, nên hai mode/cấu hình khác nhau mới được kiểm chứng qua hai process và transport mô phỏng, chưa đủ nghiệm thu hai giả lập thật. Chưa có native AVAILABLE/CLAIMABLE/chuỗi claim→còn sao→nhiều trận→xe→main mới; live chỉ kiểm chứng COMPLETE hợp lệ và xe không thu được. Connection/reload tại từng màn chiến đấu/chuyển khu/reward, Stop trong batch/kỹ năng/modal và mất ADB khi đang giữ raw touch được failure injection, chưa đủ mọi nhánh live. GĐ7 không chạy lại main/builder multiplayer đầy đủ, không mở hỗ trợ ngôn ngữ/resolution/touchscreen mới; các giới hạn GĐ3–GĐ6 về tướng/profile vẫn còn. Đây là đầu vào cần cho nghiệm thu tiếp, không cho phép thay UNKNOWN bằng COMPLETE hoặc bỏ guard để vượt thiếu dữ liệu.


## GĐ8 — nghiệm thu tổng thể (09/10/2026)

Đã đọc kế hoạch/quy tắc chung/baseline/toàn bộ progress và đối chiếu implementation với từng yêu cầu, gồm toàn bộ ma trận mục 5. [Báo cáo nghiệm thu](dual-village-validation.md) có checklist PASS/offline, PASS/live, FAIL và CHƯA KIỂM CHỨNG; không dùng fixture hoặc lời xác nhận giai đoạn trước để công bố PASS game. Manifest/file/hash/dimensions và raw receipt riêng của GĐ3–GĐ7 được kiểm lại bằng gate evidence.

Lỗi phát hiện trong phiên thật và sửa:

- Main pre-deployment có Surrender thay End Battle, guard GĐ7 nhận UNKNOWN, làm mất deployment/timeout. Nhận thêm Surrender + tiêu đề timer threshold chữ; loại builder bằng hai anchor. Hai lần thử đầu thất bại được giữ, hai fixture HUD đã che dữ liệu riêng và mẫu âm bổ sung.
- Camera bật: nhóm kỹ năng chỉ bấm HUD vô hiệu tactics do animation map khi đối soát Freeze đã nhận. Giữ phân biệt HUD/map, receipt ghi mục tiêu đã gửi và chịu được invalidation; không cho map cũ qua guard. Có test nhánh event nhanh/guarded.
- Camera bật: offset ngoài đường đỏ có thể rơi vào HUD dù đường nguồn đã mask. Planner tracked lọc điểm cuối bằng ScreenSpace; fallback hiệu chỉnh cũng lọc HUD. Test hình học tổng hợp tái hiện trước sửa; đường camera tắt không đổi.
- CLI help bỏ thông báo hybrid chờ GĐ6; engine thất bại trả exit 1 trong cả hai nhánh license. Không đổi cơ chế cấp phép. Asset gate thiếu file nay exit 1, đã thử injection không sửa file thật.
- UI bỏ câu hybrid chờ GĐ6 còn sót trong nhánh capability không khả dụng; chỉ sửa thông báo, dùng skill ui-ux-pro-max, giữ layout/khóa cấu hình. Sau sửa chạy 26 test UI/settings, 20.095s OK, không skip.

Đã chạy gate đầu phiên 476 test/319.991s OK (test exit 0; wrapper in log lỗi encoding cp1252 được ghi riêng), gate tích hợp trung gian 482/293.348s rồi 484/345.248s OK. **Gate cuối 486 test/469.922s OK, exit 0, không skip**; thời gian có tải probe builder, không dùng làm benchmark. Focused main 3, CLI 3, main regression 54, connection 6, spell 18, event 14 đều đạt; camera cuối 33/8.588s OK. Phiên live bổ sung ghi tại validation, đây là nguồn kết luận cuối phiên.

Live dùng production CLI/LicenseClient/watchdog/engine/modules/ADB trên **emulator-5556**, MuMu Android 15, English, screencap landscape 1600×900. Chỉ một game hiện hữu; alias 127.0.0.1:16416 không tính thành máy thứ hai. Settings probe/runtime/ảnh/log giữ riêng trong `diagnostics/dual_village_gd8/`; không thay settings/instances/key người dùng. Lịch bằng fake clock được tách khỏi chu kỳ live; không đổi giờ máy hoặc giả trạng thái sao. Camera vẫn false mặc định, giá trị saved camera=true được migration giữ nguyên.

Main legacy camera tắt đã hoàn tất một trận mới: Quick Train Slot 1 đúng một lần, quân/xe/hai tướng, 5 Rage + 1 Freeze, hero abilities, timeout/Okay/result/Home. Counter 2 gồm một result kế thừa và một trận mới, không công bố thành hai trận mới. Các phiên camera lỗi giữ nguyên làm bằng chứng, chỉ phiên chạy lại đạt được tính PASS.

Main camera bật sau sửa đã đạt một trận mới (187.601s), 2 pan xác nhận rev1/2, quân/xe/hai tướng/5 Rage/1 Freeze và Home; có 4 skip do ảnh chưa ổn định. Hybrid startup COMPLETE/cart unavailable/main đạt (151.665s); đây không phải lịch live 15:30 hoặc chuỗi thưởng. Builder single_point chạy riêng đạt 5 ô Rồng con + 5 skill tại cùng `(1277,536)`, hero off, một khu/result/Home (278.538s), có thu xe trước trận. Around chạy đồng thời full gate bị thiếu quân khi hết giờ: chỉ PASS cho tiếp tục dù COMPLETE/Machine skill/một khu, **FAIL triển khai đủ trong phiên tải đó**; kết quả chạy lại riêng và giới hạn tại validation. Không đổi lỗi thành PASS toàn tính năng từ goal=true của harness.

File GĐ8: `cocmagic/main.py`, `cocmagic/gui.py`, `cocmagic/modules/farm_module.py`, `cocmagic/battle_planner.py`, `tools/check_assets.py`; thêm evidence gate, hai test acceptance, mở rộng camera tests, crop timer/fixture/manifest/receipt chọn lọc. Cập nhật README, validation, progress, camera/builder docs và settings example sạch. Kiểm hash 4 file data cá nhân không đổi; settings thử giữ riêng. Giữ thay đổi GĐ1–GĐ7 và `CocMagic_Release.zip` có sẵn; không tự commit/push/deploy.

**Chưa công bố hoàn thành GĐ8/toàn tính năng.** Các đầu vào còn thiếu: native AVAILABLE/CLAIMABLE và chuỗi nhiều trận/lượt thưởng tiếp đến COMPLETE; tướng thật vắng/nâng cấp và Copter skill; hai game độc lập khác mode + reconnect một bên + Chạy tất cả/Dừng tất cả; main wall/event live và các nhánh recovery/camera chưa phủ nêu trong validation. Không hạ yêu cầu hoặc fallback âm thầm để đóng nghiệm thu.

Bàn giao cuối: lượt around riêng bị gián đoạn trước receipt; không gán PASS từ log giữa trận. Resume production CLI chỉ xử lý result kế thừa/thưởng/xe/Home, 0 Find mới; main-only startup từ builder về main Home đạt (28.884s), ảnh ADB độc lập cuối xác nhận main_home. Tất cả probe đã kết thúc. Evidence gate **9 manifest/160 file công bố/163 nguồn-receipt-log riêng, 0 lỗi**, negative gate từ chối 3 dạng giả; 61 link hợp lệ, compileall và diff check đạt. Around thiếu quân dưới tải cao vẫn là lỗi/giới hạn chưa giải quyết, cần kiểm deployment dưới tải mục tiêu. Receipt chọn lọc và file thay đổi đầy đủ ở validation; không có dữ liệu runtime/key/log/video riêng mới trong git.
