# Fixture GĐ0 hai làng

Đọc `manifest.json` và `docs/dual-village-baseline.md` trước khi dùng. Nhãn là chú giải thủ công; chưa có reader builder mới được triển khai/kiểm thử ở GĐ0.

- `video_crop`: 14 crop PNG lossless từ hai video được chỉ định, giữ pixel/scale video. Không phải screenshot Android 1600×900.
- `transformed_test`: `synthetic_bonus_occluded.png` tô hình chữ nhật lên parent `bonus_0_of_7`; chỉ để kiểm thử vùng bị che phải UNKNOWN. Không giả làm modal game thật.
- `adb_native`: chưa có ảnh; tất cả yêu cầu capture nằm trong `missing` với `path=null`.
- `*_evidence.jpg`: thumbnail có nhãn và nén JPEG, chỉ xem đối chiếu, không làm input matcher.

Đường dẫn trong `fixtures`/`inspection_sheets` tính từ thư mục này. `observations[].path` tính từ gốc repo, thuộc diagnostics đã gitignore, chỉ có tại máy khảo sát. Đường dẫn video là nguồn ngoài repo. Không tự coi path thiếu là fixture đã tồn tại.

Mỗi frame có `frame_index_zero_based`, `pts`, `time_base`, `timestamp_seconds`, dimensions và SHA-256. Crop dùng `[left,top,right,bottom]` **exclusive** theo pixel video. Tuyệt đối không dùng crop box/điểm video làm tọa độ ADB. Không tự kéo giãn crop lên 1600×900 để gọi là ảnh ADB; nếu tạo ảnh resize/padding thì khai báo `transformed_test`, parent và phép biến đổi.

Để trích lại một quan sát khi không còn diagnostics, kiểm tra hash video trong `sources`, rồi giải mã tuần tự từ đầu. Ví dụ Python (PyAV là tool khảo sát tại máy này, chưa thêm vào requirements của bot):

```python
from fractions import Fraction
from pathlib import Path
import json
import av

manifest = json.loads(Path("tests/fixtures/dual_village/manifest.json").read_text(encoding="utf-8"))
observation = next(x for x in manifest["observations"] if x["id"] == "train_148.20")
source = next(x for x in manifest["sources"] if x["id"] == observation["source"])
with av.open(source["path"]) as container:
    for index, frame in enumerate(container.decode(video=0)):
        if index == observation["frame_index_zero_based"]:
            assert frame.pts == observation["pts"]
            assert frame.time_base == Fraction(observation["time_base"])
            frame.to_image().save("stage2.png")
            break
    else:
        raise RuntimeError("Không thấy frame đã khai báo")
```

Hai video có average fps khác 30; không tính timestamp bằng `index/30`, không dùng seek chưa đối chiếu. Muốn tái tạo crop, lấy parent frame đúng PTS rồi `Image.crop(crop_xyxy_exclusive)`. Hash PNG mã hóa lại có thể khác theo phiên bản encoder; đối chiếu pixel và ghi phiên bản nếu dùng encoder khác. Thông số `pts/time_base` là mốc thời gian chuẩn.

`expected_roi_observation` chỉ nói nội dung ROI. Reader phải xác nhận full Home builder, Attack rõ, không loading/modal và hai ảnh độc lập ổn định trước COMPLETE. Mẫu video không sao là ứng viên quan sát, chưa phải ca COMPLETE native đã nghiệm thu. Các frame 173–174s có bảng thưởng; 176–177s còn `4/8`, nên đóng bảng thưởng chưa kết thúc chuỗi.

Ưu tiên lấy thật các mẫu âm P0 trong manifest: loading không sao, nút bị che, main Attack có sao, result có sao, builder nền tối đối chiếu inactivity; kèm cặp native COMPLETE. Không thay các khoảng trống này bằng bản sao nhân tạo rồi đánh dấu live PASS.
