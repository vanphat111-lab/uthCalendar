# TÀI LIỆU ĐẶC TẢ VÀ KIẾN THỨC API HỆ THỐNG TRƯỜNG ĐH GIAO THÔNG VẬN TẢI TP.HCM (UTH)

> **Cập nhật lúc:** 06/11/2026  
> **Tác giả:** vanphat111 / UTH_Calendar project  

---

## 1. TỔNG QUAN HỆ THỐNG

Hệ thống thông tin học tập của UTH gồm 2 nền tảng chính:

| Nền tảng | Domain | Giao thức / Cơ chế | Mục đích sử dụng trong Bot |
| :--- | :--- | :--- | :--- |
| **Portal Đào tạo** | `https://portal.ut.edu.vn` | RESTful API (JSON) + JWT Bearer Token | Tra cứu thời khóa biểu, lịch học theo ngày/tuần, thông tin sinh viên, link phòng học |
| **Moodle E-learning** | `https://courses.ut.edu.vn`<br>`https://thnn.ut.edu.vn` | Cookie Session + Web Scraping + Moodle AJAX Service (`service.php`) | Quét hạn chót bài tập (deadlines), bài tập nộp trễ, trạng thái bài tập |

---

## 2. CHI TIẾT API PORTAL UTH (`portal.ut.edu.vn`)

### 2.1. Đăng nhập / Xác thực (`/api/v1/user/login`)

* **Endpoint:** `POST https://portal.ut.edu.vn/api/v1/user/login?g-recaptcha-response={fake_or_real_captcha}`
* **Headers yêu cầu:**
  ```http
  Content-Type: application/json
  Accept: application/json, text/plain, */*
  User-Agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36
  Origin: https://portal.ut.edu.vn
  Referer: https://portal.ut.edu.vn/login
  ```
* **Payload (Body JSON):**
  ```json
  {
    "username": "xxxxx",
    "password": "xxxxx"
  }
  ```
  *(Lưu ý: Captcha hiện tại chấp nhận chuỗi ngẫu nhiên dài ~30 ký tự `[a-zA-Z0-9_-]` qua tham số query `g-recaptcha-response`)*

#### Kết quả thực tế khi Đăng nhập THÀNH CÔNG:
* **HTTP Status Code:** `200 OK`
* **Response Body:**
  ```json
  {
    "success": true,
    "status": 200,
    "message": "Đăng nhập thành công",
    "body": "sv",
    "token": "eyJhbGciOiJIUzI1NiJ9.eyJkYXRhIjp7ImlkIjo5MjcyOCwiaW...",
    "timestamp": "2026-11-06T11:54:56.876+00:00"
  }
  ```
* **Dữ liệu cần trích xuất:**
  * `token`: Chuỗi JWT (độ dài ~493 ký tự), dùng làm Bearer token cho các request tiếp theo. Cache Redis mặc định 2 giờ (7200s).

#### Kết quả thực tế khi Đăng nhập THẤT BẠI (Sai mật khẩu hoặc MSSV):
* **HTTP Status Code:** `200 OK` *(Đặc biệt: Server trả HTTP 200 chứ không phải 400 hay 401)*
* **Response Body:**
  ```json
  {
    "success": false,
    "status": 404,
    "message": "Sai thông tin đăng nhập",
    "body": null,
    "token": null,
    "timestamp": "2026-11-06T11:54:56.776+00:00"
  }
  ```
* **Dữ liệu báo lỗi:**
  * Trích xuất trực tiếp giá trị `data.get("message")` (ví dụ: `"Sai thông tin đăng nhập"`).

---

### 2.2. Lấy Thời khóa biểu tuần (`/api/v1/lichhoc/lichTuan`)

* **Endpoint:** `GET https://portal.ut.edu.vn/api/v1/lichhoc/lichTuan?date={YYYY-MM-DD}`
* **Headers:**
  ```http
  Authorization: Bearer {token}
  Accept: application/json, text/plain, */*
  Referer: https://portal.ut.edu.vn/calendar
  User-Agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36
  ```

#### Kết quả thực tế khi Token HỢP LỆ:
* **HTTP Status Code:** `200 OK`
* **Response Body:**
  ```json
  {
    "success": true,
    "status": 200,
    "message": "Thành công",
    "body": [
      {
        "id": 1463287,
        "ngayBatDauHoc": "02/11/2026",
        "tenPhong": "C108 - CS1 (P.Thạnh Mỹ Tây, TP.HCM)",
        "thu": 2,
        "tuTiet": 1,
        "denTiet": 3,
        "maLopHocPhan": "012012303306",
        "maMonHoc": "123033",
        "tenMonHoc": "An toàn thông tin",
        "giangVien": null,
        "isTamNgung": false,
        "tuGio": "06:45",
        "denGio": "09:15",
        "timeToDisplay": "06:45 - 09:15",
        "coSoToDisplay": "Cơ sở 1",
        "link": "https://courses.ut.edu.vn/course/view.php?idnumber=77012012303306&token=...",
        "haveOutlineFile": true,
        "outLineDescription": "Học phần cung cấp kiến thức nền tảng...",
        "ghiChu": ""
      }
    ]
  }
  ```

#### Kết quả thực tế khi Token HẾT HẠN hoặc KHÔNG HỢP LỆ:
* **HTTP Status Code:** `401 Unauthorized`
* **Response Body:**
  ```json
  {
    "success": false,
    "status": 401,
    "message": "Invalid JWT token",
    "body": null,
    "token": null,
    "timestamp": 1793966096988
  }
  ```
* **Xử lý hệ thống:**
  * Khi nhận mã `401` và `message == "Invalid JWT token"`:
    1. Xoá cache token cũ trong Redis (`auth:portal:{chatId}`).
    2. Tự động gọi lại `/api/v1/user/login` để lấy token mới.
    3. Nếu login làm mới thất bại (do user đổi pass): Báo lỗi với message trường `Sai thông tin đăng nhập`.

---

## 3. CHI TIẾT HỆ THỐNG MOODLE E-LEARNING (`courses.ut.edu.vn` & `thnn.ut.edu.vn`)

### 3.1. Luồng Đăng nhập Moodle

Moodle sử dụng cookie session (`MoodleSession`) và yêu cầu CSRF token `logintoken` được nhúng trong HTML của form đăng nhập:

1. **Bước 1 - Lấy `logintoken`:**
   * `GET https://courses.ut.edu.vn/login/index.php`
   * Regex trích xuất token: `name=["']logintoken["'][^>]*value=["']([^"']+)["']`

2. **Bước 2 - Gửi xác thực:**
   * `POST https://courses.ut.edu.vn/login/index.php`
   * Form Data:
     * `anchor`: `""`
     * `logintoken`: `{logintoken_đã_lấy}`
     * `username`: `{mssv}`
     * `password`: `{mật_khẩu}`
   * Headers:
     ```http
     Origin: https://courses.ut.edu.vn
     Referer: https://courses.ut.edu.vn/login/index.php
     ```

#### Khi Đăng nhập THẤT BẠI:
* **HTTP Status Code:** `200 OK` (Vẫn ở lại URL `https://courses.ut.edu.vn/login/index.php`)
* **HTML Response:** Chứa alert lỗi:
  ```html
  <div class="alert alert-danger" role="alert">Đăng nhập không hợp lệ, vui lòng thử lại</div>
  ```
* **Message mặc định của Moodle:** `"Đăng nhập không hợp lệ, vui lòng thử lại"`.
* **Regex trích xuất:**
  ```python
  re.search(r'<div class="[^"]*alert[^"]*danger[^"]*"[^>]*>(.*?)</div>', html, re.DOTALL | re.IGNORECASE)
  ```

#### Khi Đăng nhập THÀNH CÔNG:
* **HTTP Status Code:** `303 See Other` hoặc `200 OK` redirect tới `https://courses.ut.edu.vn/my/` hoặc `/my/courses.php`.
* Lưu toàn bộ Cookie Jar (`MoodleSession`).

---

### 3.2. Lấy `sesskey` để gọi AJAX API

* `GET https://courses.ut.edu.vn/my/courses.php`
* Regex trích xuất `sesskey`:
  ```python
  re.search(r'"sesskey"\s*:\s*"([^"]+)"', html)
  ```
* Giá trị mẫu: `NQLcyTm4cg` (dùng cho mọi request AJAX vào `service.php`).

---

### 3.3. Lấy Lịch Deadline qua Moodle AJAX Service

* **Endpoint:** `POST https://courses.ut.edu.vn/lib/ajax/service.php?sesskey={sesskey}`
* **Headers:**
  ```http
  Accept: application/json, text/plain, */*
  Content-Type: application/json
  Cookie: MoodleSession=...
  ```
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

#### Cấu trúc sự kiện deadline trả về:
Trong `response[0]["data"]["weeks"][w]["days"][d]["events"]`:
* `id`: ID định danh duy nhất của sự kiện (VD: `485338`).
* `name`: Tiêu đề bài tập (VD: `"Thực hành VLAN và Định tuyến giữa các VLAN is due"`).
* `timesort` / `timestart`: Unix timestamp hạn nộp (VD: `1793525400`).
* `course.fullname`: Tên môn học đầy đủ (VD: `"[HKI2627] - [012012304402] - Mạng máy tính nâng cao - CNS_CS1"`).
* `url`: Đường dẫn nộp bài trực tiếp (VD: `"https://courses.ut.edu.vn/mod/assign/view.php?id=774530"`).
* `overdue`: Trạng thái quá hạn (`true` / `false`).
* `activityname`: Tên bài tập (VD: `"Thực hành VLAN và Định tuyến giữa các VLAN"`).

---

## 4. MA TRẬN MÃ LỖI & THÔNG ĐIỆP BÁO NGƯỜI DÙNG (ERROR MAPPING MATRIX)

| Trường hợp | Nhận diện kỹ thuật | Phản hồi từ trường | Tin nhắn gửi người dùng (UX) |
| :--- | :--- | :--- | :--- |
| **Sai tài khoản / pass Portal** | Status 200, `data.get("token") is None`, `data.get("status") == 404` | `"Sai thông tin đăng nhập"` | ⚠️ **Xác thực thất bại**<br>Phản hồi từ cổng trường:<br><blockquote><i>"Sai thông tin đăng nhập"</i></blockquote><br>👉 Vui lòng kiểm tra lại tài khoản hoặc mật khẩu và bấm /login để cập nhật. |
| **Sai tài khoản / pass Moodle** | URL chứa `/login/index.php`, có `<div class="alert-danger">` | `"Đăng nhập không hợp lệ, vui lòng thử lại"` | ⚠️ **Xác thực Moodle thất bại**<br>Phản hồi từ Moodle:<br><blockquote><i>"Đăng nhập không hợp lệ, vui lòng thử lại"</i></blockquote><br>👉 Bạn hãy kiểm tra lại mật khẩu trên Moodle Courses. |
| **Token hết hạn (Portal)** | HTTP `401 Unauthorized`, `Invalid JWT token` | `"Invalid JWT token"` | Tự động refresh trong background. Nếu refresh thất bại: Báo user /login lại. |
| **Server trường mất kết nối / bảo trì (500, 502, 503)** | HTTP `500` (Thực tế trường trả 500 khi backend/gateway mất kết nối API) hoặc `502, 503, 504` | HTML/JSON lỗi server trường | 🏫 **Máy chủ cổng trường đang gặp sự cố**<br>Hệ thống máy chủ UTH đang mất kết nối hoặc bảo trì (Mã lỗi HTTP: 500). Vui lòng thử lại sau ít phút.<br><i>(Mã tra cứu: #T-xxxx)</i> |
| **Cloudflare Rate Limit (429)** | HTTP `429 Too Many Requests` | N/A | ⚡ **Hệ thống đang tự phục hồi kết nối**<br>Đang làm mới địa chỉ kết nối an toàn (WARP). Yêu cầu của bạn đang được thử lại... |
| **Không có lịch học** | Body mảng rỗng `[]` | N/A | 📅 **Không có lịch học**<br>Bạn không có tiết học nào trong khoảng thời gian này. Hãy nghỉ ngơi nhé! 🎉 |

---
