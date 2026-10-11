# CocMagic: farm hai làng

## Cấu trúc dự án

```text
CocMagic/
├── gui.py, main.py       # Lệnh chạy cũ; chuyển vào package
├── CocMagic.lnk          # Shortcut có logo, mở giao diện không có terminal
├── CHAY.bat, CHAY.vbs    # Cách mở giao diện khác trên Windows
├── cocmagic/             # Mã chương trình
│   ├── gui.py            # Giao diện nhiều giả lập
│   ├── main.py           # Lệnh chạy không giao diện
│   ├── config.py         # Mặc định và đường dẫn
│   └── modules/          # Farm, hero, nâng tường
├── data/                 # Cấu hình người dùng theo máy và từng giả lập
│   ├── settings.json
│   └── instances.json
├── assets/               # Ảnh mẫu và phông chữ nhận diện
├── tests/                # Kiểm thử và ảnh mẫu cho kiểm thử
└── tools/                # Công cụ kiểm tra, chẩn đoán
```

Khi nâng cấp từ cấu trúc cũ, chuyển `settings.json` và `instances.json` ở thư mục gốc vào `data/` trước khi mở bot. Không sửa trực tiếp file trong `cocmagic/` để thay cấu hình người dùng.

Trên Windows, cài thư viện một lần bằng `python -m pip install -r requirements.txt`, rồi nhấp đúp `CocMagic.lnk` để mở bảng điều khiển với logo riêng và không hiện terminal. Shortcut trỏ đến thư mục hiện tại; nếu chuyển thư mục dự án, cần tạo lại shortcut. Cũng có thể nhấp đúp `CHAY.vbs` để mở không có terminal. `CHAY.bat` mở giao diện bằng `pythonw` và tự đóng cửa sổ dòng lệnh ngay sau khi chạy; do là file batch nên có thể chớp terminal trong thoáng chốc. Có thể dùng `python gui.py` nếu cần xem lỗi khởi động trong terminal. Logo trong giao diện và biểu tượng cửa sổ được lấy từ `assets/logobot.png` và `assets/logobot.ico`. Muốn chính file `.exe` mang icon riêng thì cần build.

Sau khi mở game trên màn hình Android 1600 × 900, bảng điều khiển cho phép lưu cấu hình, bắt đầu/dừng bot, xem log và số viên tường đã nâng trong phiên. Trong tab Làng chính, hai lựa chọn loại trừ nhau: **Nâng tường khi farm** hoặc **Đánh sự kiện** (vẫn farm, không nâng tường). Chế độ chạy main/builder/hybrid được chọn riêng ở Run. Có thể nhập tài nguyên như `9tr`, `500k` hoặc `9.000.000`. Muốn chạy không có giao diện, dùng `python main.py --port 5555`.

Ở chế độ **Đánh sự kiện**, chọn **Ưu tiên bonus tài nguyên**, bấm **Lưu cấu hình** rồi **Bắt đầu bot**. Bot vẫn luyện và triển khai combo như bình thường, đồng thời xử lý bảng **Pick a Reward!** mỗi khi bảng xuất hiện (kể cả mốc 33%, 67%, 100%). Bot ưu tiên tài nguyên đã chọn; nếu không có, lần lượt tìm dầu đen, dầu tím, vàng trong những thẻ nhận diện được. Bot không chọn bonus lính để giữ nguyên vị trí thanh quân. Sau khi chọn, bot chờ hai ảnh mới liên tiếp không còn bảng, rồi chọn lại ô quân/phép đang dùng trước khi tiếp tục. Nếu trận đã sang kết quả hoặc về làng, bot hủy chuỗi thả còn lại. Nếu không nhận diện được tài nguyên hoặc bảng không đóng, bot dừng và ghi lý do vào log để người dùng xử lý thủ công.

Thiết lập này lưu riêng cho từng giả lập. Khi chạy bằng dòng lệnh, đặt `"event_mode": true`, `"upgrade_walls": false` và `"event_resource_priority": "dark"` (hoặc `"elixir"`, `"gold"`) trong `data/settings.json`. Chế độ mặc định có `event_mode=false`. Nhận diện bonus dựa trên giao diện tiếng Anh trong ảnh mẫu; bot xử lý khi thấy bảng, không cần đọc phần trăm phá hủy.

## Hai làng: sử dụng và phạm vi đã kiểm chứng

Mỗi giả lập có **Làng chính**, **Làng đêm**, **Run**. Cấu hình train/farm và nâng tường/sự kiện nằm trong Làng chính; cấu hình Rồng con, cách thả, tướng sẵn sàng, thu xe, lịch và camera nằm trong Làng đêm. Tab Run chọn chế độ, bắt đầu/dừng và hiển thị trạng thái, thống kê, log. Nút **Lưu cấu hình cả ba tab** lưu toàn bộ cấu hình của giả lập đang chọn. Khi chạy, cấu hình bị khóa nhưng vẫn chuyển tab để xem được.

Có thể chạy **Làng chính (`main`)**, **Làng đêm (`builder`)** hoặc **Làng chính + Làng đêm (`hybrid`)**. Builder-only dùng Rồng con, hai chiến thuật, tướng theo trạng thái thật, kỹ năng từng ô, hai khu và hậu xử lý thưởng/xe; hết sao vẫn tiếp tục. Hybrid kiểm tra builder lúc startup, train đến khi hết chuỗi thưởng khả dụng, thu xe rồi ưu tiên main; kiểm tra lại từ **15:30 UTC+7** mỗi ngày tại điểm chuyển an toàn. Profile triển khai hiện tại là **English, ảnh ADB landscape 1600×900, MuMu Android 15**. Ba mode đã mở trong GUI/CLI, nhưng nghiệm thu đầy đủ còn thiếu nhánh live; xem [ma trận GĐ8](docs/dual-village-validation.md). Camera tự chỉnh vẫn mặc định tắt. Chạy tất cả xét mode riêng của từng giả lập.

Settings dùng dictionary phẳng, schema 2; wrapper `data/instances.json` vẫn là `version=1`. File cũ thiếu `run_mode` được hiểu là main. Migration chỉ diễn ra trong bộ nhớ khi đọc, giữ giá trị và key chưa biết; dữ liệu mới được ghi khi lưu. Các trường của làng đang chạy được kiểm tra chung cho GUI/CLI/engine; hybrid cần hợp lệ cả hai làng. Trường nháp của làng không dùng được giữ lại và kiểm tra khi chọn lại làng đó. Quy tắc sự kiện/nâng tường chỉ thuộc cấu hình Làng chính; lưu builder không tự bật event rewards.

| Key mới | Mặc định / giá trị hợp lệ |
|---|---|
| `settings_schema_version` | `2` |
| `run_mode` | `main`; `main`, `builder`, `hybrid` |
| `builder_deploy_mode` | `around`; `around`, `single_point` |
| `builder_auto_setup_baby_dragons` | `true` |
| `builder_use_available_hero` | `true` |
| `builder_collect_cart` | `true` |
| `hybrid_check_time` | `"15:30"`; HH:MM từ 00:00 đến 23:59 |
| `hybrid_timezone` | `"Asia/Ho_Chi_Minh"` (UTC+7 cố định) |
| `hybrid_builder_budget_seconds` | `1800`; 300–7200 giây mỗi chuyến builder |
| `hybrid_max_battles` | `12`; 1–50 trận mỗi chuyến builder |
| `camera_auto_adjust` | `false`; giữ lựa chọn đã lưu |

GUI: Run → chọn chế độ → Bắt đầu; chọn cách thả và công tắc Rồng con/tướng/xe ở tab Làng đêm. CLI: `python main.py --run-mode hybrid --port 16416` (hoặc `builder`, `main`); vẫn giữ `--settings`, `--verbose`, `--activate` và license hiện có. Tham số CLI không ghi đè file cấu hình. Runtime hybrid lưu trong `data/runtime/` theo serial chuẩn của giả lập; các alias ADB đã xác minh cùng VM dùng chung runtime và khóa input. Startup luôn đọc lại màn hình, kể cả runtime từng ghi COMPLETE. Xem [lịch và xử lý lỗi hybrid](docs/dual-village-schedule.md) và [cấu hình, timeout và giới hạn builder](docs/dual-village-builder.md).

## Chạy nhiều giả lập

- Mở từng giả lập MuMu với ADB debugging và đặt game ở độ phân giải **1600 × 900**. Chương trình tự quét các cổng MuMu và tạo một tab cho mỗi giả lập. Nếu chưa thấy tab mới, bấm **Quét lại** hoặc **Thêm cổng** và nhập cổng ADB, ví dụ `16416`.
- Mỗi tab có cấu hình, nút **Bắt đầu bot / Dừng bot**, trạng thái, nhật ký và số tường đã nâng riêng. Có thể dùng **Chạy tất cả / Dừng tất cả** ở phía trên. Mở thêm giả lập khi chương trình đang chạy sẽ tạo thêm tab sau lần quét tiếp theo; bot của tab mới chỉ chạy sau khi bạn bấm Bắt đầu.
- Cấu hình mặc định lấy từ `data/settings.json`; cấu hình riêng theo cổng được lưu trong `data/instances.json`. Tệp này được tạo tự động và lưu lại khi mở chương trình lần sau. `python gui.py --port 16416` sẽ mở đúng tab đó; cách chạy một giả lập bằng `python main.py --port ...` vẫn dùng `data/settings.json`.
- Khi kết nối ADB của một giả lập mất, chỉ bot của tab đó dừng. Nếu ADB hiển thị nhiều địa chỉ cho cùng một giả lập, chương trình đối chiếu ID phiên khởi động Android và chỉ tạo một tab. Một phiên bot chỉ được gắn với một định danh ADB.

- `min_gold` và `min_elixir`: chỉ cần **một trong hai** ngưỡng đang bật đạt yêu cầu. Giá trị `0` tắt ngưỡng đó. Nếu cả hai bằng `0`, không lọc theo vàng và dầu tím.
- `min_dark`: nếu lớn hơn `0`, đây là điều kiện bổ sung bắt buộc.
- `auto_train`: dùng Quick Train Slot 1 **một lần khi khởi động** để nạp hàng đợi. Các vòng sau dùng cùng combo và không mở bảng luyện quân nữa.
- Lần đánh đầu tiên, bot quét thanh triển khai thực tế và ghi nhớ vị trí các ô quân, xe công thành, phép và những hero có mặt. Không cần cố định số ô hoặc số hero theo Town Hall. Sau khi đổi combo, dừng bot rồi chạy lại để quét combo mới.
- Thanh quân được quét theo cả khung ngang và cạnh đứng, kể cả các ô xám. Chân dung hero được đối chiếu thêm ở ảnh xám để giữ đúng vị trí khi màu thay đổi; xe công thành có các mẫu cho cả ô được chọn. Số lượng được đọc đủ cả dãy chữ số sau `x`, giữ trạng thái chưa rõ nếu một chữ số bị mất thay vì đọc `x10` thành `x0`.
- Nếu thanh quân tạm thời bị xám khi chuyển cảnh, bot chờ và kiểm tra lại. Khi tọa độ cache không còn khớp, bot thử định vị lại một lần; bot chỉ chuyển sang chờ trận sau khi xác nhận có quân đã được thả.
- Nút ở Home, menu tìm trận và Next được ghi nhớ sau lần nhận diện đầu. Các nút trong menu và Next được kiểm tra trong vùng nhỏ trước khi dùng tọa độ cũ; nếu vị trí đổi, bot nhận diện lại. Sau khi bấm Attack ở Home, bot kiểm tra đã mở menu; nếu vẫn ở Home, bot thử lại tối đa 4 lần rồi báo lỗi rõ ràng.
- Khi game hiện **Connection lost**, bot nhận diện và bấm đúng **Try Again**, ngắt chuỗi thả quân/phép hiện tại, chờ **10 giây** rồi kiểm tra lại màn hình để farm tiếp. Cache trận và combo cũ được xóa sau reload. Có thể bấm Dừng trong thời gian chờ này.
- Ảnh ADB được lấy ở dạng thô trên giả lập hỗ trợ; định dạng không phù hợp tự chuyển về PNG. Một ảnh có thể được dùng lại trong tối đa 0,35 giây khi chưa có lệnh thao tác; mọi tap, nhóm tap và lệnh shell đều xóa cache ảnh. Kết quả nhận diện được dùng lại trên cùng ảnh, còn vị trí đã học luôn được kiểm tra lại và tìm lại nếu nút chuyển chỗ.
- Với **mỗi đối thủ**, bot đọc tài nguyên và tìm đường viền đỏ để chọn điểm ngoài vùng cấm. Màu nền, cây, tượng và các trang trí không loại điểm thả. Nếu viền đỏ bị che, nằm ngoài camera hoặc cảnh nền lạ, bot dùng khung hình thoi cố định của vùng xây dựng để dò bốn cạnh ở nhiều khoảng cách; không bỏ qua base chỉ vì không thấy cỏ xanh. Bot thử từng điểm bằng một quân, kiểm tra số quân giảm trên tối đa ba ảnh mới rồi mới thả tiếp ở điểm đã xác nhận. Các vùng tên người chơi, tài nguyên, End Battle, Next/phần trăm phá hủy và thanh quân được loại khỏi điểm dò. Nếu game từ chối toàn bộ điểm thì bot rút khỏi trận; ảnh trắng, ảnh đang tải hoặc không thấy vùng base không tạo kế hoạch thả.
- Quân tạo một hướng tấn công chính; khi `attack_around=true`, bot xác nhận thêm một hướng khác để chia quân. Electro được chia trên tối đa ba hướng cách nhau: xác nhận các hướng trước, rồi gửi phần quân còn lại trong một nhóm lệnh. Điểm đã xác nhận được dùng lại cho các ô khác trong cùng trận. Nếu có xe công thành, bot thả tại hướng quân đã xác nhận rồi thả các hero cùng hướng; bot không bấm xe như kỹ năng hero.
- Điểm mới được thử riêng bằng một quân; sau khi có đủ điểm, bot gửi nhóm quân còn lại (tối đa 16 tap mỗi command ADB) rồi kiểm tra số lượng trên ảnh mới. Ở chế độ sự kiện, nhóm nhanh chỉ dùng tọa độ ngoài các thẻ bonus; nếu bonus ngắt giữa nhóm, bot chọn tài nguyên rồi đọc số quân còn lại để tiếp tục. Vị trí nằm trên vùng thẻ dùng luồng kiểm tra từng thao tác. Khi OCR chưa rõ, bot so hình chữ số tách khỏi khung và nền; đổi màu/khung chọn không được coi là quân đã thả.
- Các cặp chọn–thả hero được gửi trong một nhóm, bấm vào phần chân dung phía trên để tránh nút đổi chế độ Quản Giáo và mũi tên ở đáy ô. Bot kiểm tra thanh máu sau nhóm, chờ thêm ảnh nếu giao diện cập nhật chậm rồi chỉ thử lại tướng chưa được xác nhận. Khi bonus ngắt nhóm, tướng đã thả không bị chọn lại như một lần triển khai mới.
- **Warden và cả đội bật sau** (`warden_ability_delay`, mặc định 10 giây) tính từ lúc xác nhận thả Warden. Khi đến hạn, hoặc Warden bị nhận diện máu thấp trong hai ảnh liên tiếp, bot gửi nhóm kỹ năng cho các hero đã thả. Danh sách đang làm được giữ tới khi nhóm hoàn tất; sau bonus bot gửi lại nhóm bị ngắt (kỹ năng đã dùng không thể kích hoạt lần hai). Khi không dùng Warden, thời gian tính từ hero đầu tiên được xác nhận.
- Cache tọa độ thanh quân được dùng suốt phiên; bộ nhận diện hero dùng lại kết quả quét ô khi hiệu chuẩn. Số lượng và trạng thái ô chỉ được đọc một lần trên cùng ảnh. Cache điểm thả chỉ sống trong một trận, còn dữ liệu nhận dạng ảnh bị xóa khi ảnh thay đổi hoặc game reload.
- Bot nhận diện từng loại spell từ ảnh trên thanh quân. Rage, Haste, Heal và các spell hỗ trợ bám theo đường tiến quân; Freeze, Lightning, Earthquake và các spell tác động công trình dùng những vùng công trình ước lượng từ ảnh base. Lightning và Earthquake có thể cùng nhắm một vùng để phối hợp. Mỗi lần thả đều chọn lại ô phép để tiếp tục đúng sau khi bật kỹ năng hero. Bot ưu tiên xác nhận số phép giảm, chờ tối đa ba ảnh mới nếu số chưa cập nhật, và tiếp tục từng phép cho tới khi hết. Khi không đọc rõ số lượng, bot kiểm tra thay đổi vùng số và trạng thái ô phép. Spell không nhận diện chắc chắn được giữ lại để tránh ném sai.
- Nếu chưa xác nhận được một lần thả phép, bot đọc thêm tối đa ba ảnh mới và dùng hai số liên tiếp khớp nhau để đối soát. Số đã giảm thì tiếp tục mục tiêu kế tiếp; số giữ nguyên thì chọn lại và thử tối đa ba lần. Khi số vẫn chưa rõ, bot giữ ảnh mốc và phần phép chưa hoàn tất, chờ hai giây rồi phục hồi trong `BATTLE_WAIT`, tối đa ba lượt liên tiếp chưa tiến triển. Bot hoàn tất việc phục hồi trước khi rút theo số sao, vẫn giữ giới hạn thời gian trận và hủy phép chờ khi trận kết thúc hoặc game reload. Log lỗi gồm số trước/sau và ảnh ô phép tại `diagnostics/spell_failures/`.

## Nâng tường qua danh sách thợ

- `upgrade_walls=false` khi mục tiêu là train sự kiện hoặc giữ tài nguyên. Khi bật, bot đọc kho và nhận diện biểu tượng thợ thường đang rảnh ở Home, mở danh sách thợ, cuộn tối đa 9 lần để tìm `Wall x`, rồi chọn `Upgrade More`.
- Vùng tìm `Wall x` bao gồm cột chữ khi danh sách mở rộng vì tên nâng cấp dài và dòng cuối sát đáy. Bot kiểm tra lại chữ `Wall` ngay tại dòng vừa tìm được, rồi bấm vào dòng đó trước khi cuộn tiếp.
- Khi nút `Add Wall +10` biến mất do còn ít tường, bot tìm lại vị trí các nút trên thanh thao tác. Nút `+1` được xác định theo nút nâng bằng vàng, còn vùng đọc giá đi theo biểu tượng tài nguyên của từng nút. Bot đọc số viên còn lại trên dòng `Wall x…` để giới hạn đợt nâng; nếu chỉ còn một viên thì nâng trực tiếp viên đó.
- Bot dựa vào chân dung thợ thường, không trừ cố định từ bộ đếm `1/5` hay `1/6`. Nếu biểu tượng chuyển thành thợ Goblin có thể thuê, bot bỏ qua nâng tường và không bấm lựa chọn dùng Gems hay Wall Rings.
- `wall_type` là `gold`, `elixir` hoặc `both`. Nếu là `both`, chỉ cần **một kho đủ tiền**; bot chọn kho nâng được nhiều viên hơn cho đợt đầu. Sau mỗi đợt được đối soát số dư, bot quét lại cả hai kho và tiếp tục nâng ngay nếu vẫn đủ điều kiện, rồi mới quay về farm/train. `wall_resource` là ngưỡng bắt đầu xét nâng, bao gồm đúng mức đã đặt (ví dụ đặt 9 triệu thì từ 9 triệu trở lên mới nâng). `wall_reserve` là lượng muốn giữ lại, `wall_max_batch` giới hạn số viên mỗi đợt.
- Bot đọc giá một viên và tính `floor((số dư − wall_reserve) / giá)`, sau đó bấm `Add Wall` từng viên. Giá phải tăng đúng theo số viên trên ảnh mới; nếu nhận diện sai, giá thay đổi hoặc xuất hiện hộp thoại Goblin Builder/Gems, bot dừng và đóng bảng. Sau khi bấm xác nhận, bot chờ số dư cập nhật. Nếu OCR chưa đọc được nhưng hộp thoại đã đóng và đã về Home, bot ghi nhận số viên đã xác nhận, nêu rõ việc đối soát số dư còn thiếu trong log và dừng nâng tiếp lượt này để tránh mua lặp.
- Giá nhỏ trên nền nút sáng được đọc bằng nhiều ngưỡng ảnh, kiểm tra đủ các nhóm ba chữ số và chỉ chấp nhận khi các lần đọc khớp nhau. Sau khi mở `Upgrade More` hoặc bấm `Add Wall`, bot chờ tối đa bốn ảnh kiểm tra để giao diện và tổng tiền cập nhật; ảnh kiểm tra này không dùng cache cũ.
- Trong phiên chạy, bot ghi nhớ vị trí chân dung thợ rảnh, nút `Add Wall`, các nút nâng bằng vàng/dầu tím và nút `Okay` xác nhận. Mỗi lần cần dùng, bot nhận diện lại trên ảnh mới quanh vị trí đã lưu; nếu nút di chuyển thì tìm lại trong vùng đầy đủ. Vị trí cũ không được dùng để bấm khi nút hoặc hộp thoại không còn xuất hiện.

Chạy kiểm thử không tương tác với game:

```powershell
python -m unittest discover -s tests -q
python tools/check_assets.py
```

## Thử nghiệm cấp phép

Dịch vụ cấp phép và chương trình admin nằm riêng tại `C:\Users\PC\Documents\admin-key-cocmagic`.
Bản thử hiện **tắt theo mặc định**, nên bot vẫn chạy như trước. Để thử trên máy này:

1. Chạy `RUN_LOCAL_API.bat` trong thư mục admin và giữ cửa sổ đó mở. Lần đầu script tự cài Wrangler, áp dụng schema D1 cục bộ rồi mở API tại `http://127.0.0.1:8787`.
2. Chạy `RUN_ADMIN.bat` để tạo key có hạn hoặc vĩnh viễn, xem máy đã kích hoạt, đặt lại máy hoặc thu hồi key. Key chỉ hiện một lần sau khi tạo.
3. Đổi `"enabled": false` thành `"enabled": true` trong `data/license-config.json`, rồi chạy `CHAY.bat`. Bấm **Nhập key** trong giao diện để dùng key vừa tạo; key lưu bằng Windows DPAPI.
4. Với chế độ không giao diện, dùng `python main.py --activate` để nhập key qua prompt, sau đó chạy `python main.py --port ...` như thường lệ.

Mỗi máy chỉ kiểm tra một key cho tất cả tab giả lập. Giao diện sẽ kiểm tra lại sau 10 phút; mất kết nối tạm thời được ân hạn 30 phút khi bot đang chạy. Key hết hạn hoặc bị thu hồi sẽ dừng các bot đang chạy sau khi hoàn tất thao tác hiện tại. File `data/license-config.json` là cấu hình riêng của máy; mẫu phát hành nằm trong `docs/license-config.example.json`.

**Quay về luồng cũ:** đặt `"enabled": false` trong `data/license-config.json`. Không cần thay đổi cấu hình farm hay từng giả lập. Đây là công tắc dành cho bản thử; trước khi phát hành bot có kiểm soát quyền cho người khác, cần bỏ khả năng tự tắt cấp phép khỏi bản phân phối.

Các công cụ đọc màn hình để chẩn đoán nằm trong `tools/`: chạy `python tools/debug_check.py` hoặc `python tools/debug_extract_digits.py` từ thư mục dự án. Ảnh chúng tạo ra được lưu vào `diagnostics/`.

## Sao, lịch và đội hình

Sao trên nút Attack/Tìm trận của làng đêm nghĩa là còn thưởng; `0/y` vẫn là AVAILABLE. Mẫu số được đọc theo ảnh, không cố định 7 hoặc 8. Bot nhận bảng thưởng rồi đọc lại: còn lượt thưởng tiếp thì đánh tiếp, kể cả cần nhiều trận. COMPLETE cần hai ảnh Home builder mới, ổn định, nhìn rõ nút/vùng sao. Loading, nút bị che, ảnh lỗi hoặc sao bay là UNKNOWN; bot thử lại có giới hạn và báo chưa hoàn thành.

Hybrid luôn kiểm tra lúc khởi động, kể cả trước 15:30. Kiểm tra hợp lệ từ **15:30 UTC+7** thỏa lịch ngày đó; kiểm tra sớm vẫn giữ lượt kiểm tra theo lịch. Mốc 13:00 không tự tạo kết luận thưởng. Đến hạn giữa trận thì giữ pending, hoàn tất trận và hậu xử lý rồi mới chuyển. Ngủ qua lịch kiểm tra bù ngày hiện tại một lượt; restart luôn đọc lại màn hình. Thu xe trước khi về main; không chờ vô hạn lượt phòng thủ chưa xong. UNKNOWN/watchdog không được ghi thành đã hoàn thành; fallback main chỉ sau xác nhận Home và có lỗi/retry hiển thị ở Run.

Builder-only vẫn train khi COMPLETE. Bot xác nhận Rồng con ở nhóm Starting và Reinforcements, chỉ sửa ô sai khi bật tự thiết lập; nếu tắt, đội hình phải đúng sẵn. Around phân bố quanh các cạnh hợp lệ; single_point dùng một điểm đã được game nhận cho mỗi khu. Điểm bị từ chối phải đổi và có receipt trước khi tiếp tục. Có tướng sẵn sàng thì dùng, thiếu/khóa thì vẫn dùng quân; tướng không rõ phải đọc lại. Kỹ năng quân/tướng tự động theo trạng thái thanh quân; không dùng chính sách Warden của main. Khu hai quét lại quân sống, tiếp viện, tướng và kỹ năng, bỏ điểm bản đồ khu trước. 100% khu một chưa chứng minh trận kết thúc. Thiếu/nâng cấp tướng thật và kỹ năng Copter tự động còn thiếu bằng chứng live.

## Camera và giới hạn hỗ trợ

Camera mặc định **tắt**, giữ nguyên giá trị người dùng đã lưu. Công tắc tự chỉnh trận nằm ở Làng đêm và dùng cho cả main/builder; điều hướng tìm thuyền/xe vẫn có thể pan/zoom hữu hạn khi cần. Pan dùng ADB swipe theo serial. Pinch dùng protocol B hai slot chung SYN_REPORT, chỉ mở khi probe đúng Xiaomi Touchscreen raw axes 900×1600, rotation=1, ảnh 1600×900 và quyền sendevent trên MuMu Android 15. Hai swipe độc lập hoặc Ctrl+wheel không phải backend pinch được triển khai. Backend khác trả UNSUPPORTED; không âm thầm đổi mode.

Ảnh mới phải xác nhận camera; plan/điểm thả/spell target cũ bị vô hiệu hóa, HUD không dịch theo bản đồ. Cạnh dưới có thể chỉ lộ một phần do giới hạn pan; chỉ dùng điểm nhìn thấy và được game nhận. Camera đã có bằng chứng Home/Practice/cạnh dưới, nhưng mọi tổ hợp multiplayer/hai serial/hero chưa được nghiệm thu đầy đủ. Không công bố hỗ trợ tiếng Việt hoặc resolution khác từ video tham khảo. Xem [camera](docs/dual-village-camera.md), [builder](docs/dual-village-builder.md), [điều hướng/thưởng/xe](docs/dual-village-navigation.md), [lịch hybrid](docs/dual-village-schedule.md).

## Migration, chẩn đoán và chạy lại

Cấu hình cũ thiếu key mới vẫn chạy main, schema settings lên 2 trong bộ nhớ, giữ key chưa biết và lựa chọn camera đã lưu; wrapper instances vẫn version 1. Chỉ lưu mới ghi file. Runtime lịch riêng từng giả lập trong `data/runtime/`, dùng chung cho alias đã xác minh; không copy runtime trận hay key vào cấu hình ví dụ. [Mẫu settings không có key/tài khoản](docs/dual-village-settings.example.json) dùng main, camera tắt và nâng tường tắt; auto_train cần Saved Recipes Slot 1 đã chuẩn bị.

```powershell
python main.py --settings docs/dual-village-settings.example.json --run-mode main --port 16416
# Chọn builder hoặc hybrid bằng --run-mode; CLI override không sửa file đã tồn tại.
python -m unittest discover -s tests -q
python tools/check_assets.py
python tools/check_dual_village_evidence.py
```

Dừng bot trước khi đổi mode. Để chẩn đoán, chọn Run → Làng chính, đặt `camera_auto_adjust=false`, lưu rồi Bắt đầu; CLI có thể dùng `--run-mode main` với file settings riêng đã tắt camera. Đây là lựa chọn chẩn đoán, không làm nhánh builder/hybrid lỗi thành đã đạt nghiệm thu.

| Hiện tượng | Cách xử lý |
|---|---|
| UNKNOWN, không đọc được sao/đích | Kiểm tra English/1600×900, đóng modal đúng chức năng; xem reason/retry ở Run. Không tự sửa runtime thành COMPLETE. |
| Save Army / không thấy Use Slot 1 | Lưu đội hình main vào Saved Recipes Slot 1 trước khi bật auto_train. |
| Không xác nhận được thuyền/xe/geometry | Kiểm tra đúng làng, popup và backend; Stop, chụp ảnh mới để chẩn đoán. Không nhập tọa độ lấy từ video. |
| Xe còn tiền nhưng Collect xám | Có thể không thu được ở trạng thái hiện tại; bot ghi unavailable, đóng Home, không báo đã thu hay xe trống. |
| Runtime bị khóa | Kiểm tra phiên GUI/CLI/probe khác đang sở hữu cùng giả lập, kể cả qua alias ADB; dừng đúng phiên rồi chạy lại. Không xóa lock khi worker còn chạy. |
| Mất ADB/connection/reload | Guard hủy input cũ và phân loại lại, retry hữu hạn; chỉ instance lỗi dừng. |
| Dừng chưa tức thì | Chờ command ADB đang chạy/timeout và cleanup; batch tối đa 16 tap. Release mất ADB có thể chưa xác nhận. |
| License lỗi/hết hạn | Xem thông báo cấp phép và dịch vụ đã cấu hình; expiry dừng các worker. CLI trả exit 1 khi engine thất bại, exit 2 khi config/license từ chối. |

Kết quả từng ca, lệnh, ảnh/log và phần còn thiếu được ghi tại [dual-village-validation.md](docs/dual-village-validation.md); tiến độ lịch sử ở [dual-village-progress.md](docs/dual-village-progress.md).

Kiểm tra source cho người phát triển: cài `python -m pip install -r requirements-dev.txt`, rồi chạy `python -m ruff check cocmagic tools tests`, `python -m unittest discover -s tests -q`, `python tools/check_assets.py` và `python tools/check_dual_village_evidence.py`. Ruff chỉ thuộc bộ công cụ phát triển. Các probe có gửi input dùng khóa VM chung với engine; runtime thử hybrid vẫn nằm riêng trong thư mục output. File ZIP phát hành, cấu hình máy và diagnostics được giữ ngoài Git.

Bản sửa hybrid mới nhất ngày 11/10/2026 qua **538 test** và các gate source. Live 3 chu kỳ main, camera/auto train bật: kiểm tra xe một lượt lúc startup, không quay lại builder sau các trận. Đã sửa reset thưởng và request startup bị tạo lại khi phục hồi main RESULT; xe tùy chọn không tạo retry thưởng. Đóng rồi mở lại CocMagic để nạp code mới; chi tiết tại [báo cáo sửa vòng lặp hybrid](docs/dual-village-hybrid-repeat-fix-20261011.md). Hồ sơ native reward 529 test tại [báo cáo trước](docs/dual-village-hybrid-fix-20261011.md); hồ sơ 519 test/checkout từ Git index tại [báo cáo kiểm thử và dọn source](docs/dual-village-verification-20261011.md).
