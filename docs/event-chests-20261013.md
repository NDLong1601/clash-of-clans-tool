# Tự nhận và mở rương sau trận — 13/10/2026

Bot nhận diện **Claim Reward** thay nút trở về, chờ rương xuất hiện, bấm theo số búa còn lại rồi nhận thưởng bằng **Continue**. Luồng bình thường có bốn lần bấm rương. Nếu không có rương, kết quả trận đi theo luồng cũ. Tính năng luôn hoạt động, không cần bật `event_mode` hoặc thêm cấu hình.

Vị trí rương được cache trong bộ nhớ riêng của module trên từng giả lập. Lượt sau đối chiếu ảnh quanh vị trí cache trước; nếu không khớp thì tìm lại. Cache giữ qua phục hồi trận, bị xóa khi đổi kích thước ảnh hoặc khởi động lại bot. Không dùng tọa độ cache để bấm khi chưa nhận diện phòng rương và rương thật; bệ trống dù có bốn búa vẫn phải chờ.

Mỗi lần bấm chờ số búa giảm. Nếu game không nhận click, bot thử lại có giới hạn; tối đa ba lần cho cùng số búa, tám lần tổng cộng, giới hạn 25 giây/120 vòng quan sát. Claim và Continue mỗi nút chỉ gửi một lần trong giao dịch. Stop/mất ADB đi qua cơ chế dừng và phục hồi hiện có. Hết giới hạn bot báo lỗi, không click tiếp vô hạn. Bộ điều phối không chuyển làng trong lúc mở rương.

## Phạm vi triển khai

- [Bộ nhận diện và mở rương](../cocmagic/event_chests.py): ảnh mẫu nút, phòng, khóa rương và số búa; cache có đối chiếu ảnh mới.
- [Farm làng chính](../cocmagic/modules/farm_module.py): nhận diện rương như kết quả trận, hủy input chiến đấu còn chờ, mở rương trước hậu xử lý.
- [Farm làng đêm](../cocmagic/modules/builder_farm_module.py): xử lý cùng giao diện rương trước chuyển làng/thu xe. Chưa quan sát trực tiếp một rương phát sinh ở làng đêm; giao diện Claim riêng khác mẫu cần bổ sung ảnh.
- [Engine](../cocmagic/bot_engine.py): tránh để cơ chế popup chung can thiệp vào màn rương.
- [30 test mới](../tests/test_event_chests.py) và manifest ảnh trong assets/fixtures, bổ sung vào gate kiểm asset và provenance.

Mẫu chuẩn được lấy từ video người dùng ngày 11/10, hiệu chỉnh với ảnh ADB English 1600×900 trên MuMu Android 15. Nhánh nhận diện yêu cầu ảnh landscape gần 16:9; chưa kiểm chứng ngôn ngữ/giao diện sự kiện khác.

## Kiểm chứng

Trước hiệu chỉnh Sour Elixir: **566 test / 377.671 giây / OK**, gồm 28 test mới. Lint, compileall, kiểm asset/import, CLI help và kiểm provenance đều exit 0; không thay source trong lúc chạy. Evidence gate trước hiệu chỉnh: 11 manifest, 197 file công bố, 180 nguồn riêng, không lỗi. Test mô phỏng xác nhận đúng Claim + 4 click + Continue, cache lượt sau, di chuyển rương, đổi độ phân giải, không có rương, animation chậm, bệ trống, Stop, lỗi ADB, giới hạn retry và quyền xử lý của module.

Các phiên hiệu chỉnh ngày 11/10 được giữ nguyên, không gọi là PASS toàn luồng: lần đầu cần giảm ngưỡng chữ phụ tại Claim cho ảnh ADB; lần sau đã gửi Claim và đúng bốn click vào rương nhưng dừng ở Continue do ngưỡng ảnh khác video. Sau hiệu chỉnh Continue, phiên tiếp theo đã nhận thưởng Shiny Ore và về Home nhưng bị gián đoạn ở trận sau. Một probe khác mất ADB; không có receipt chứng minh cache tái sử dụng trực tiếp từ các phiên đó.

Ngày 13/10 đã chạy hai trận mới trên giả lập thật với production engine/modules/ADB và lease thiết bị, `event_mode=false`, auto train bật, camera và nâng tường tắt trong bản sao settings. Receipt hoàn tất sau **199.444 giây**, hai trận và ảnh cuối xác nhận Home; lỗi null, source không đổi. Có hai lần phục hồi nhận diện lúc chuyển từ trận sang kết quả, đều về làng thành công. **Cả hai trận không có rương**: đây là PASS/live cho nhánh không rương, chưa phải PASS toàn luồng rương trên bản cuối hoặc cache qua hai rương thật. Không tiếp tục farm vô hạn để chờ sự kiện. Bằng chứng riêng: `diagnostics/event_chest_20261011/live-resume-20261013/receipt.json` và `final-home.png`.

## Ba trận bổ sung theo yêu cầu trước push

Lượt đầu dừng khi bộ bảo vệ phát hiện tọa độ map cũ trước khi thả tướng (39.612 giây, 0 trận hoàn tất). Chưa có đủ bằng chứng phân biệt camera thực sự đổi với animation làm bộ đo chuyển động mất tin cậy; không sửa/hạ guard để vượt lỗi này. Đây vẫn là giới hạn độc lập cần theo dõi, không gọi lượt đó là PASS.

Phiên tiếp theo mở trọn rương từ kết quả kế thừa, nhưng trận mới dừng tại Claim có Sour Elixir (206.777 giây). Nguyên nhân tái hiện được: mẫu chữ phụ video chỉ đạt 0.7757, thấp hơn ngưỡng 0.78; nút Claim đạt 0.9482. Đã bổ sung mẫu chữ native với ngưỡng riêng 0.88, giữ điều kiện kép nút Claim + chữ kết quả; thêm ảnh đã che dữ liệu và hai test nhận diện/phục hồi luồng đầy đủ. **30 test rương / 16.112 giây / OK** sau sửa.

Chạy lại trên source đã sửa: **316.941 giây, completed=true, error=null**, kết thúc ở Home. Counter 4 gồm **một kết quả kế thừa + đúng ba trận mới**, không tính thành bốn trận mới. Hai lần Claim, tám click rương (4 + 4), hai lần Continue đều được ADB xác nhận. Rương đầu ở kết quả kế thừa dùng điểm (814,504); rương sau từ trận mới tái xác minh bằng cache rồi dùng điểm (814,492). `chests_opened=2`, `cache_hits=1`. Ba trận mới gồm hai trận không rương và một trận có rương, đều về làng; source không đổi trong lúc chạy. Ba lần mất nhận diện ngắn ở chuyển cảnh kết quả đều phục hồi thành công.

Bằng chứng cục bộ: `diagnostics/event_chest_20261011/live-extra-three-fixed-20261013/receipt.json`, `final-home.png`, ảnh scene và console tương ứng. Các receipt lỗi trước sửa được giữ riêng trong `live-extra-three-20261013` và `live-extra-three-rerun-20261013`. Phiên cuối dùng cùng cấu hình probe như trên; không sửa settings đã lưu. PASS/live này áp dụng làng chính/profile English 1600×900, không mở rộng thành nghiệm thu rương làng đêm hoặc mọi nhánh camera.

Gate cuối sau bản sửa và ba trận bổ sung: **568 test / 295.793 giây / OK**; lint, compileall, assets, evidence và CLI help đều exit 0. Không thay source trong lúc chạy. Evidence cuối: 11 manifest / 199 file công bố / 182 nguồn riêng / 0 lỗi.

Log, ảnh ADB nguyên bản và video giữ trong diagnostics cục bộ; chỉ công bố ảnh mẫu đã cắt/che dữ liệu và manifest. Cấu hình cá nhân, khóa license và archive bản phát hành được giữ nguyên. Bản source mới cần đóng rồi mở lại CocMagic để nạp; không cần thay cấu hình.
