# MAVAP Chatbot Frontend

Giao diện chat đơn giản cho MAVAP Bot sử dụng HTML/CSS/JavaScript thuần.

## Tính năng

✅ **Giao diện chat hiện đại**
- Theme sáng/tối (Dark/Light Mode)
- Animations mượt mà
- Responsive design
- Markdown rendering cho câu trả lời

✅ **Thinking Process Box**
- Hiển thị quá trình suy nghĩ của AI
- Có thể thu gọn/mở rộng
- Lưu trạng thái vào localStorage

✅ **Session Management**
- Tự động tạo session ID
- Lưu lịch sử chat vào localStorage
- Nút xóa hội thoại để tạo session mới

✅ **Real-time Streaming**
- SSE (Server-Sent Events) streaming từ backend
- Hiển thị typing indicator
- Stream text theo thời gian thực

## Cấu trúc thư mục

```
frontend/
├── index.html          # Giao diện chính
├── css/
│   └── style.css       # Styling với theme đen trắng
├── js/
│   └── app.js          # Logic xử lý chat và events
└── README.md           # File này
```

## Cách sử dụng

### 1. Chạy Backend API

Đảm bảo backend API đang chạy trên `http://localhost:9998`:

```bash
cd /path/to/MAVAPBot
python src/api. py
```

### 2. Mở giao diện

Có 2 cách: 

**Cách 1: Mở trực tiếp file HTML**
```bash
# Trên Linux/Mac
open frontend/index.html

# Hoặc dùng Python HTTP server
cd frontend
python -m http.server 8000
# Sau đó mở http://localhost:8000
```

**Cách 2: Sử dụng Live Server (VS Code)**
- Cài extension "Live Server" trong VS Code
- Right-click vào `frontend/index.html`
- Chọn "Open with Live Server"

### 3. Cấu hình API URL

Nếu backend API chạy ở địa chỉ khác, sửa trong `js/app.js`:

```javascript
const CONFIG = {
    API_BASE_URL: 'http://localhost:9998/mavap/api',  // Thay đổi URL ở đây
    // ... 
};
```

## Sử dụng giao diện

### Gửi tin nhắn
- Nhập tin nhắn vào ô input
- Nhấn nút 📤 hoặc Enter để gửi
- Shift + Enter để xuống dòng

### Theme Toggle
- Nhấn nút 🌙/☀️ để chuyển đổi Dark/Light mode
- Theme được lưu tự động

### Thinking Box
- Click vào header "💭 Thinking Process" để thu gọn/mở rộng
- Trạng thái được lưu tự động

### Clear Conversation
- Nhấn nút 🗑️ để xóa toàn bộ hội thoại
- Sẽ tạo session ID mới

## Xử lý Events từ Backend

Frontend xử lý các loại events sau từ LangGraph:

### Custom Events
- `on_think_event`: Hiển thị trong Thinking Box
- `on_answer_event`: Hiển thị câu trả lời chính
- `on_blocked_event`: Hiển thị cảnh báo nội dung bị chặn
- `on_passed_event`: Nội dung đã được kiểm duyệt (không hiển thị)
- `on_terminated_event`: Kết thúc stream

### Chat Model Events
- `on_chat_model_stream`: Stream text từ LLM

### Node-specific Events
- Events từ các nodes:  `ask_user`, `gather_user_information_agent`, `general_agent`, `answer_agent`

## Troubleshooting

### CORS Error
Nếu gặp lỗi CORS, đảm bảo backend đã cấu hình CORS middleware:

```python
# Trong src/api.py
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Hoặc chỉ định origins cụ thể
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### Không kết nối được API
- Kiểm tra backend đang chạy:  `curl http://localhost:9998/mavap/api/healthz`
- Kiểm tra URL trong `js/app.js`
- Mở Console (F12) để xem lỗi chi tiết

### Markdown không render
- Đảm bảo marked.js được load từ CDN trong `index.html`
- Kiểm tra console có lỗi không

## Browser Support

- Chrome/Edge: ✅
- Firefox: ✅  
- Safari: ✅
- Opera: ✅

## Dependencies

- [Marked.js](https://marked.js.org/) - Markdown parser (CDN)
- Không cần dependencies khác, thuần HTML/CSS/JS

## License

MIT
