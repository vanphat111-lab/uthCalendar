# TÀI LIỆU ĐẶC TẢ VÀ KIẾN THỨC TOÀN BỘ HỆ THỐNG API ĐH GIAO THÔNG VẬN TẢI TP.HCM (UTH)

> **Cập nhật mới nhất:** 15/11/2026  
> **Nguồn phân tích:** Reverse Engineering từ SPA Bundle (`portal.ut.edu.vn`) & Moodle LMS Service (`courses.ut.edu.vn`, `thnn.ut.edu.vn`)  
> **Dự án:** UTH_Calendar  

---

## 1. TỔNG QUAN KIẾN TRÚC HỆ THỐNG TRƯỜNG

Hệ thống thông tin quản lý sinh viên của Trường Đại học Giao thông vận tải TP.HCM (UTH) vận hành dựa trên 2 nền tảng máy chủ chính:

```
                            ┌───────────────────────────────────────────────┐
                            │           SINH VIÊN / BOT CLIENT              │
                            └───────┬───────────────────────────────┬───────┘
                                    │                               │
                       RESTful JSON │ Bearer JWT      Session Cookie│ AJAX Service
                                    ▼                               ▼
                 ┌───────────────────────────────────┐ ┌───────────────────────────────────┐
                 │       PORTAL ĐÀO TẠO UTH          │ │        MOODLE E-LEARNING          │
                 │   https://portal.ut.edu.vn/api/v1 │ │ https://courses.ut.edu.vn         │
                 │                                   │ │ https://thnn.ut.edu.vn            │
                 └───────────────────────────────────┘ └───────────────────────────────────┘
```

1. **Portal Đào tạo (`https://portal.ut.edu.vn`)**:
   - Kiến trúc: Frontend Single Page Application (React + Vite) kết nối Backend RESTful API JSON.
   - Base URL: `https://portal.ut.edu.vn/api/v1`
   - Xác thực: JWT Token (đặt trong header `Authorization: Bearer {token}`).
   - Cơ chế Captcha: Sử dụng query param `g-recaptcha-response`. Hiện tại chấp nhận mã giả lập chuỗi ngẫu nhiên dài 30 ký tự (`[a-zA-Z0-9_-]`).

2. **Moodle E-learning LMS (`courses.ut.edu.vn` & `thnn.ut.edu.vn`)**:
   - Nền tảng: Moodle LMS PHP.
   - Xác thực: Cookie phiên `MoodleSession` và token chống CSRF form `logintoken`.
   - Giao diện API: Moodle Web AJAX Service (`/lib/ajax/service.php?sesskey={sesskey}`).

---

## 2. CHI TIẾT TOÀN BỘ API PORTAL ĐÀO TẠO (`portal.ut.edu.vn/api/v1`)

### 2.1. Phân hệ Xác thực & Tài khoản (`/user`)

#### [POST] `/api/v1/user/login?g-recaptcha-response={captcha}`
* **Mục đích:** Đăng nhập lấy JWT Bearer Token.
* **Headers:**
  ```http
  Content-Type: application/json
  Accept: application/json, text/plain, */*
  Origin: https://portal.ut.edu.vn
  Referer: https://portal.ut.edu.vn/login
  ```
* **Payload:**
  ```json
  {
    "username": "{MSSV}",
    "password": "{MẬT_KHẨU}"
  }
  ```
* **Response Thành công (`200 OK`):**
  ```json
  {
    "success": true,
    "status": 200,
    "message": "Đăng nhập thành công",
    "body": "sv",
    "token": "eyJhbGciOiJIUzI1NiJ9...",
    "timestamp": "2026-11-15T10:00:00.000+00:00"
  }
  ```
* **Response Thất bại (`200 OK` - Đặc thù máy chủ trường không trả 401 khi sai pass):**
  ```json
  {
    "success": false,
    "status": 404,
    "message": "Sai thông tin đăng nhập",
    "body": null,
    "token": null
  }
  ```

#### [GET] `/api/v1/user/profile`
* **Mục đích:** Lấy thông tin cá nhân chi tiết của sinh viên.
* **Headers:** `Authorization: Bearer {token}`
* **Dữ liệu trả về tiêu biểu:**
  * MSSV, Họ và tên lót, Tên.
  * Lớp sinh hoạt, Ngành đào tạo, Khoa quản lý, Niên khóa.
  * Giới tính, Ngày sinh, Nơi sinh, Số CCCD/CMND.
  * Số điện thoại cá nhân, Email cá nhân, Địa chỉ thường trú / tạm trú.

#### [GET] `/api/v1/user/getSchoolEmail`
* **Mục đích:** Lấy email định danh trường cấp cho sinh viên (`...@ut.edu.vn`).

#### [GET] `/api/v1/user/image`
* **Mục đích:** Lấy URL hoặc dữ liệu ảnh thẻ sinh viên lưu trên hồ sơ trường.

#### [GET] `/api/v1/user/checkBHYT`
* **Mục đích:** Kiểm tra mã thẻ BHYT và tình trạng đăng ký/gia hạn BHYT qua trường.

#### [PUT] `/api/v1/user/updatePhone` / `/api/v1/user/updateEmail`
* **Mục đích:** Cập nhật thông tin liên lạc cá nhân (yêu cầu xác thực OTP qua `/api/v1/user/sendOTPUpdate`).

#### [POST] `/api/v1/user/change_password`
* **Mục đích:** Đổi mật khẩu tài khoản Portal.
* **Payload:** `{"oldPassword": "...", "newPassword": "...", "confirmPassword": "..."}`

#### [GET] `/api/v1/user/logout`
* **Mục đích:** Đăng xuất và vô hiệu hóa phiên làm việc trên cổng trường.

---

### 2.2. Phân hệ Lịch học & Thời khóa biểu (`/lichhoc`)

Mọi request đều yêu cầu Header: `Authorization: Bearer {token}`.

#### [GET] `/api/v1/lichhoc/lichTuan?date={YYYY-MM-DD}`
* **Mục đích:** Lấy toàn bộ thời khóa biểu của 1 tuần chứa ngày chỉ định (từ Thứ 2 đến Chủ nhật).
* **Cấu trúc trường trong mảng `body`:**
  * `id`: ID phiên học / lịch học.
  * `ngayBatDauHoc`: Ngày diễn ra buổi học (`DD/MM/YYYY`).
  * `thu`: Thứ trong tuần (2 -> Chủ nhật = 8 / CN).
  * `tuTiet`, `denTiet`: Tiết bắt đầu - tiết kết thúc (VD: `1` -> `3`).
  * `tuGio`, `denGio`, `timeToDisplay`: Giờ học hiển thị (VD: `"06:45"`, `"09:15"`).
  * `tenMonHoc`, `maMonHoc`, `maLopHocPhan`: Thông tin môn học & lớp học phần.
  * `tenPhong`, `coSoToDisplay`: Phòng học và cơ sở (CS1, CS2, CS3, CS Đồng Nai...).
  * `giangVien`: Giảng viên phụ trách.
  * `isTamNgung`: Trạng thái tạm ngưng/báo nghỉ (`true`/`false`).
  * `link`: Đường dẫn liên kết trực tiếp sang Moodle E-learning của môn học.
  * `haveOutlineFile`: Đã có file đề cương môn học hay chưa (`true`/`false`).

#### [GET] `/api/v1/lichhoc/lichNgay?date={YYYY-MM-DD}`
* **Mục đích:** Lấy thời khóa biểu cụ thể của duy nhất 1 ngày chỉ định.

#### [GET] `/api/v1/lichhoc/thang?date={YYYY-MM-DD}`
* **Mục đích:** Lấy lịch học bao quát cả tháng.

#### [GET] `/api/v1/lichhoc/downloadDeCuong?idLichHoc={id}`
* **Mục đích:** Tải file đề cương chi tiết học phần định dạng PDF/DOCX.

#### [GET] `/api/v1/lichhoc/songayhoc`
* **Mục đích:** Thống kê tổng số ngày học trong học kỳ hiện tại.

---

### 2.3. Phân hệ Học tập & Bảng điểm (`/hoctap`)

#### [GET] `/api/v1/hoctap/hocky`
* **Mục đích:** Lấy danh mục các học kỳ sinh viên đã và đang học (kèm `id` học kỳ để truyền vào các API tra cứu điểm).

#### [GET] `/api/v1/hoctap/montheoky/{idHocKy}`
* **Mục đích:** Tra cứu điểm chi tiết từng môn trong một học kỳ.
* **Dữ liệu trả về gồm:**
  * Mã môn học, tên môn học, số tín chỉ.
  * Điểm chuyên cần / quá trình, điểm bài tập, điểm giữa kỳ, điểm thực hành.
  * Điểm thi kết thúc học phần.
  * Điểm tổng kết hệ 10, điểm hệ 4, điểm chữ (A, B+, B, C+, C, D+, D, F).
  * Kết quả đạt / không đạt (`pass`/`fail`).

#### [GET] `/api/v1/hoctap/kqtheoky/{idHocKy}`
* **Mục đích:** Tra cứu kết quả xếp loại học tập và rèn luyện tổng hợp của học kỳ.
* **Dữ liệu trả về gồm:**
  * Điểm trung bình học kỳ (thang 10 & thang 4).
  * Điểm trung bình tích lũy (GPA tích lũy toàn khóa).
  * Số tín chỉ đạt trong kỳ, số tín chỉ tích lũy.
  * Xếp loại học lực (Xuất sắc, Giỏi, Khá, Trung bình, Yếu).
  * Điểm rèn luyện học kỳ và xếp loại rèn luyện.

#### [GET] `/api/v1/hoctap/bangdiem`
* **Mục đích:** Bảng điểm toàn khóa học tính đến thời điểm hiện tại.

#### [GET] `/api/v1/hoctap/tiendo`
* **Mục đích:** Kiểm tra tiến độ hoàn thành chương trình đào tạo.
* **Dữ liệu trả về:** Tỷ lệ % hoàn thành, tổng số tín chỉ bắt buộc đã đạt / cần tích lũy, tín chỉ tự chọn.

#### [GET] `/api/v1/hoctap/chuongtrinhkhung`
* **Mục đích:** Cây chương trình đào tạo chuẩn của ngành học theo từng kỳ định hướng.

#### [GET] `/api/v1/hoctap/getChungChi`
* **Mục đích:** Danh sách chứng chỉ chuẩn đầu ra đã nộp và được phòng đào tạo công nhận (TOEIC, IELTS, MOS, GDQP, GDTC...).

---

### 2.4. Phân hệ Tài chính & Học phí (`/hocphi`)

#### [GET] `/api/v1/hocphi?idDot={idDot}`
* **Mục đích:** Tra cứu học phí cần đóng, các khoản miễn giảm, nợ cũ và số tiền thực tế phải nộp của đợt thu học phí.

#### [GET] `/api/v1/hocphi/phieuthu`
* **Mục đích:** Lịch sử toàn bộ các phiếu thu/biên lai học phí sinh viên đã nộp thành công qua ngân hàng hoặc cổng thanh toán.

#### [GET] `/api/v1/hocphi/phieuthuchitiet/{idPhieuThu}`
* **Mục đích:** Chi tiết danh mục môn học và số tiền tương ứng được khấu trừ trong một phiếu thu cụ thể.

#### [GET] `/api/v1/hocphi/khoanthukhac`
* **Mục đích:** Danh sách các khoản phí phát sinh ngoài học phí chính khóa (phí thẻ, bảo hiểm, thi lại...).

---

### 2.5. Phân hệ Đăng ký học phần (`/dkhp`)

#### [GET] `/api/v1/dkhp/getDot`
* **Mục đích:** Lấy thông tin đợt đăng ký học phần đang mở (thời gian mở cổng, thời gian đóng cổng, loại đợt).

#### [GET] `/api/v1/dkhp/getHocPhanHocMoi?idDot={idDot}`
* **Mục đích:** Danh sách các học phần mở mới theo tiến độ kỳ này.

#### [GET] `/api/v1/dkhp/getHocPhanHocLai?idDot={idDot}` / `getHocPhanCaiThien?idDot={idDot}`
* **Mục đích:** Danh sách các môn học sinh viên chưa đạt cần học lại hoặc có điểm thấp muốn học cải thiện.

#### [GET] `/api/v1/dkhp/getLopHocPhanChoDangKy?idDot={idDot}&maHocPhan={maHocPhan}&isLocTrung={bool}&isLocTrungWithoutElearning={bool}`
* **Mục đích:** Lấy danh sách các lớp học phần mở cho một môn học cụ thể (kèm bộ lọc trùng lịch).

#### [GET] `/api/v1/dkhp/getLopHocPhanDetail?idLopHocPhan={id}`
* **Mục đích:** Xem chi tiết lớp học phần: Giảng viên, sĩ số hiện tại / tối đa, phòng học, lịch học từng buổi.

#### [GET] `/api/v1/dkhp/getLichTrung?idLopHocPhan={id}`
* **Mục đích:** Kiểm tra xem lớp học phần dự định chọn có bị xung đột thời khóa biểu với các môn đã đăng ký trước đó hay không.

#### [POST] `/api/v1/dkhp/dangKyLopHocPhan?idLopHocPhan={id}&g-recaptcha-response={captcha}`
* **Mục đích:** Gửi lệnh đăng ký vào lớp học phần.
* **Payload:** `{}` (Body rỗng).
* **Lưu ý:** Chấp nhận chuỗi captcha giả lập sinh bởi `generateFakeCaptcha()`.

#### [GET] `/api/v1/dkhp/getLHPDaDangKy?idDot={idDot}`
* **Mục đích:** Lấy danh sách các lớp học phần sinh viên đã đăng ký thành công trong đợt.

#### [DELETE] `/api/v1/dkhp/huyDangKy?idDangKy={idDangKy}`
* **Mục đích:** Hủy lớp học phần đã đăng ký (chỉ khả dụng trong thời gian cổng ĐKHP mở).

---

### 2.6. Phân hệ Thông báo & Tin tức (`/notification`)

#### [GET] `/api/v1/notification`
* **Mục đích:** Danh sách thông báo mới nhất từ các phòng ban nhà trường (Phòng Đào tạo, Khảo thí, CTSV, KHTC...).

#### [GET] `/api/v1/notification/{id}`
* **Mục đích:** Đọc nội dung chi tiết thông báo (HTML format, danh sách file đính kèm nếu có).

#### [GET] `/api/v1/notification/getPopup`
* **Mục đích:** Lấy thông báo khẩn cấp dạng modal popup khi sinh viên vừa đăng nhập.

---

### 2.7. Các Phân hệ Phụ trợ khác

| Phân hệ | API Endpoints tiêu biểu | Mô tả chức năng |
| :--- | :--- | :--- |
| **Dịch vụ Một cửa** (`/dichVu`) | `GET /dichVu/getAll`<br>`POST /dichVu/dangKy`<br>`DELETE /dichVu/huy/{id}` | Cấp giấy xác nhận sinh viên, bảng điểm in giấy, xác nhận vay vốn ngân hàng chính sách. |
| **Sự kiện & Phong trào** (`/eventWeb`) | `GET /eventWeb/getAll`<br>`POST /eventWeb/register?eventId={id}` | Đăng ký tham gia hội thảo, workshop, tình nguyện, tính điểm rèn luyện. |
| **Ký túc xá** (`/dorm`) | `GET /dorm/getCampus`<br>`GET /dorm/getRoom?campusId={id}`<br>`POST /dorm/register` | Xem cơ sở, danh sách phòng còn trống và nộp hồ sơ nội trú KTX. |
| **Khảo sát giảng viên** (`/survey`) | `GET /survey/checkSurvey`<br>`GET /survey/getAll`<br>`POST /survey/doSurvey` | Đánh giá môn học và giảng viên cuối kỳ (điều kiện bắt buộc để mở khóa xem điểm). |
| **Xét tốt nghiệp** (`/hoctap/xetTotNghiep`) | `GET /hoctap/getDotXetTotNghiep`<br>`POST /hoctap/xetTotNghiep?idDot={id}` | Nộp hồ sơ và tra cứu kết quả xét công nhận tốt nghiệp ra trường. |

---

## 3. CHI TIẾT HỆ THỐNG MOODLE E-LEARNING (`courses.ut.edu.vn` & `thnn.ut.edu.vn`)

### 3.1. Cơ chế Xác thực 2 bước của Moodle

Moodle không dùng JWT mà quản lý phiên qua Cookie Session PHP và token phòng chống tấn công CSRF.

1. **Bước 1 - Lấy `logintoken`:**
   * Gửi `GET https://courses.ut.edu.vn/login/index.php`.
   * Regex trích xuất token trong HTML:
     ```python
     re.search(r'name=["\']logintoken["\'][^>]*value=["\']([^"\']+)["\']', html).group(1)
     ```

2. **Bước 2 - Đăng nhập:**
   * Gửi `POST https://courses.ut.edu.vn/login/index.php` với form data:
     * `anchor`: `""`
     * `logintoken`: Giá trị lấy từ Bước 1
     * `username`: MSSV
     * `password`: Mật khẩu
   * Nhận `MoodleSession` cookie được lưu vào CookieJar.

3. **Bước 3 - Lấy `sesskey` để gọi AJAX API:**
   * Sau khi đăng nhập thành công, gửi `GET https://courses.ut.edu.vn/my/courses.php`.
   * Regex trích xuất:
     ```python
     re.search(r'"sesskey"\s*:\s*"([^"]+)"', html).group(1)
     ```

---

### 3.2. Moodle AJAX Service API (`/lib/ajax/service.php`)

* **Endpoint:** `POST https://courses.ut.edu.vn/lib/ajax/service.php?sesskey={sesskey}`
* **Headers:**
  ```http
  Accept: application/json, text/plain, */*
  Content-Type: application/json
  Cookie: MoodleSession={cookie}
  ```

#### Method 1: Lấy lịch Deadline tháng (`core_calendar_get_calendar_monthly_view`)
* **Payload:**
  ```json
  [
    {
      "index": 0,
      "methodname": "core_calendar_get_calendar_monthly_view",
      "args": {
        "year": "2026",
        "month": "11",
        "courseid": 1,
        "day": 1,
        "view": "month"
      }
    }
  ]
  ```
* **Cấu trúc sự kiện trả về (`events`):**
  * `id`: ID định danh duy nhất của bài tập.
  * `name`: Tiêu đề bài tập (VD: `"Thực hành Lab 01 is due"`).
  * `timesort` / `timestart`: Unix timestamp hạn chót nộp bài.
  * `course.fullname`: Tên khóa học chứa bài tập.
  * `url`: Link trực tiếp đến bài tập trên Moodle.
  * `overdue`: Trạng thái quá hạn (`true` / `false`).

#### Method 2: Lấy sự kiện sắp tới (`core_calendar_get_calendar_upcoming_view`)
* **Payload:**
  ```json
  [
    {
      "index": 0,
      "methodname": "core_calendar_get_calendar_upcoming_view",
      "args": {
        "courseid": 1
      }
    }
  ]
  ```

#### Method 3: Lấy danh sách khóa học đang theo học (`core_course_get_enrolled_courses_by_timeline_classification`)
* **Payload:**
  ```json
  [
    {
      "index": 0,
      "methodname": "core_course_get_enrolled_courses_by_timeline_classification",
      "args": {
        "classification": "inprogress",
        "limit": 0,
        "offset": 0,
        "sort": "fullname"
      }
    }
  ]
  ```

---

## 4. MA TRẬN MÃ LỖI & CHIẾN LƯỢC XỬ LÝ (ERROR HANDLING MATRIX)

| Trường hợp | Dấu hiệu kỹ thuật | Hành vi máy chủ UTH | Cơ chế tự phục hồi của Hệ thống |
| :--- | :--- | :--- | :--- |
| **Sai thông tin Portal** | HTTP 200, `token is None`, `status == 404` | Trả JSON `{"message": "Sai thông tin đăng nhập"}` | Báo trực tiếp cho người dùng kiểm tra lại MSSV / Pass. |
| **Token Portal hết hạn** | HTTP `401 Unauthorized`, `Invalid JWT token` | JSON `{"message": "Invalid JWT token"}` | Xóa cache token cũ trong Redis, tự động gọi re-login lấy token mới và retry request. |
| **Sai tài khoản Moodle** | HTTP 200 tại `/login/index.php`, có `<div class="alert-danger">` | HTML chứa thông báo lỗi tiếng Việt | Thông báo mật khẩu Moodle không chính xác. |
| **Moodle Session hết hạn** | HTTP 303 Redirect về `/login/index.php` hoặc AJAX trả lỗi auth | Redirect | Khởi tạo lại Session CookieJar mới và lấy lại `sesskey`. |
| **Server Portal 500** | HTTP `500 Internal Server Error` | Xảy ra khi cổng backend hoặc DB Oracle của trường quá tải | Ghi log `ERROR`, kích hoạt Circuit Breaker tránh spam request. |
| **Bảo trì / Quá tải Gateway** | HTTP `502, 503, 504 Bad Gateway / Gateway Timeout` | Nginx/Cloudflare upstream timeout | Tự động retry tối đa 3 lần với exponential backoff. |
| **Cloudflare Rate Limit** | HTTP `429 Too Many Requests` | IP bị đưa vào danh sách chờ | Tự động chuyển IP qua cơ chế xoay Multi-WARP Proxy Pool. |
