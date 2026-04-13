# 🎬 Video Sản Phẩm Manager - Telegram Bot

Bot Telegram giúp quản lý quy trình làm video sản phẩm theo 5 bước.

## Quy trình

```
📹 Quay Video → 📝 Viết Nội Dung → 🎙️ Lồng Tiếng → ✂️ Chỉnh Sửa → 📤 Đăng Video
```

### Chi tiết từng bước:
- **Bước 1 - Quay Video**: Bấm ✅ khi quay xong
- **Bước 2 - Viết Nội Dung**: Thêm nhiều mục nội dung, tick từng cái khi viết xong
- **Bước 3 - Lồng Tiếng**: Thêm bản lồng tiếng, tick khi lồng xong, có thể xóa
- **Bước 4 - Chỉnh Sửa**: Tự động copy từ lồng tiếng sang, tick khi sửa xong
- **Bước 5 - Đăng Video**: Tick YouTube / Shopee / TikTok → tick hết 3 cái = hoàn thành & xóa khỏi danh sách

## Cài đặt

### 1. Cài Python (3.10+)

### 2. Cài thư viện
```bash
pip install -r requirements.txt
```

### 3. Thay token bot
Mở file `bot.py`, tìm dòng:
```python
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
```
Thay `YOUR_BOT_TOKEN_HERE` bằng token từ BotFather.

Hoặc set biến môi trường:
```bash
export BOT_TOKEN="8752391971:AAH-Z3SL0RtyF0Tvwg9Dh1QBIEcm-1iFyT4"
```

### 4. Chạy bot
```bash
python bot.py
```

## Các lệnh bot

| Lệnh | Mô tả |
|-------|--------|
| `/start` | Khởi động bot |
| `/new` | Tạo video mới |
| `/list` | Xem video đang làm |
| `/done` | Xem video đã hoàn thành |
| `/remind` | Nhắc việc tổng quan |
| `/delete` | Xóa video |
| `/help` | Hướng dẫn |

## Lưu trữ
Data được lưu trong file `data.json` cùng thư mục. Không cần database.
