# IoT Gateway for SIM900A GSM Module

This gateway solves the problem where SIM900A GSM modules cannot handle HTTPS connections. It acts as a simple HTTP-to-HTTPS proxy between your ESP32+SIM900A devices and your HTTPS-only backend.

## 🚀 Quick Deploy on Render

1. **Fork this repository** to your GitHub account

2. **Deploy on Render**:
   - Go to [dashboard.render.com](https://dashboard.render.com)
   - Click "New +" → "Web Service"
   - Connect your GitHub repository
   - Use these settings:
     - **Name**: `iot-gateway`
     - **Environment**: Python 3
     - **Build Command**: `pip install -r requirements.txt`
     - **Start Command**: `python gateway.py`
     - **Plan**: Free

3. **Add Environment Variable**:
   - `BACKEND_URL` = `https://your-backend.onrender.com`

4. **Deploy** and note your gateway URL: `https://iot-gateway.onrender.com`

## 📱 Configure Your ESP32

In your ESP32 code, point to this gateway instead of your backend:

```cpp
// In config.h
const char* serverURL = "iot-gateway.onrender.com";  // Your gateway URL
const int serverPort = 80;  // Gateway accepts HTTP