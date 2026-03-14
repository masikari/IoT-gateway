import http.server
import socketserver
import requests
import logging
import os
import sys
import json
import time
import socket
from urllib.parse import urlparse
from datetime import datetime

# CONFIGURATION
PORT = int(os.environ.get("PORT", 10000))
BACKEND_URL = os.environ.get("BACKEND_URL", "https://pool-table-backend-jukw.onrender.com")
GATEWAY_NAME = os.environ.get("GATEWAY_NAME", "iot-gateway")
DEBUG = os.environ.get("DEBUG", "True").lower() == "true"  # Enable debug by default

# Logging setup
logging.basicConfig(
    level=logging.DEBUG if DEBUG else logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(GATEWAY_NAME)

logger.info("=" * 60)
logger.info(f"🚀 Starting IoT Gateway v2.1.0")
logger.info(f"📡 Listening on port: {PORT}")
logger.info(f"🔄 Forwarding to backend: {BACKEND_URL}")
logger.info(f"🔍 Debug mode: {DEBUG}")
logger.info("=" * 60)

class IoTGatewayHandler(http.server.BaseHTTPRequestHandler):
    def address_string(self):
        return str(self.client_address[0])
    
    def do_GET(self):
        if self.path == '/debug':
            self.handle_debug()
        elif self.path == '/health':
            self.handle_health()
        elif self.path.startswith('/ping/'):
            self.handle_ping()
        else:
            self.handle_request('GET')
    
    def do_POST(self):
        self.handle_request('POST')
    
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
    
    def handle_debug(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain')
        self.end_headers()
        
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)
        
        debug_info = [
            "=" * 50,
            "IoT GATEWAY DEBUG INFORMATION",
            "=" * 50,
            f"Timestamp: {datetime.now().isoformat()}",
            f"Gateway Name: {GATEWAY_NAME}",
            f"Version: 2.1.0",
            f"Hostname: {hostname}",
            f"Local IP: {local_ip}",
            f"Listening Port: {PORT}",
            f"Backend URL: {BACKEND_URL}",
            f"Debug Mode: {DEBUG}",
            "",
            "CLIENT INFORMATION:",
            f"  Client IP: {self.client_address[0]}",
            f"  Client Port: {self.client_address[1]}",
            "",
            "=" * 50,
            "Gateway is ready!",
            "=" * 50
        ]
        
        self.wfile.write("\n".join(debug_info).encode())
        logger.info(f"Debug info sent to {self.client_address[0]}")
    
    def handle_health(self):
        health_data = {
            "status": "healthy",
            "gateway": GATEWAY_NAME,
            "version": "2.1.0",
            "timestamp": datetime.now().isoformat()
        }
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(health_data).encode())
    
    def handle_ping(self):
        """Special handler for ping requests - returns 200 directly"""
        device_id = self.path.split('/')[-1]
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        response = {
            "status": "ok",
            "device": device_id,
            "timestamp": datetime.now().isoformat(),
            "gateway": GATEWAY_NAME
        }
        self.wfile.write(json.dumps(response).encode())
        logger.info(f"Ping response sent to device: {device_id}")
    
    def handle_request(self, method):
        start_time = time.time()
        request_id = f"{int(start_time * 1000)}-{self.client_address[0]}"
        
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length) if content_length > 0 else None
            
            logger.info(f"[{request_id}] → {method} {self.path} from {self.client_address[0]}")
            
            # If it's a ping request, handle it directly
            if self.path.startswith('/ping/'):
                self.handle_ping()
                return
            
            # Forward to backend
            backend_url = f"{BACKEND_URL}{self.path}"
            
            headers = {
                'Content-Type': self.headers.get('Content-Type', 'application/json'),
                'X-Forwarded-For': self.client_address[0],
                'X-Gateway-Id': GATEWAY_NAME,
                'X-Request-Id': request_id,
                'User-Agent': 'IoT-Gateway/2.1',
                'Accept': 'application/json'
            }
            
            if DEBUG:
                logger.debug(f"[{request_id}]   Forwarding to: {backend_url}")
                if body:
                    try:
                        body_str = body.decode('utf-8')[:200]
                        logger.debug(f"[{request_id}]   Payload: {body_str}")
                    except:
                        pass
            
            # IMPORTANT: Disable redirects and handle them manually
            session = requests.Session()
            session.max_redirects = 0  # Don't follow redirects automatically
            
            try:
                if method == 'GET':
                    response = session.get(
                        backend_url,
                        headers=headers,
                        timeout=30,
                        allow_redirects=False  # Don't follow redirects
                    )
                else:
                    response = session.post(
                        backend_url,
                        data=body,
                        headers=headers,
                        timeout=30,
                        allow_redirects=False
                    )
                
                # Handle redirects manually
                if response.status_code in [301, 302, 303, 307, 308]:
                    redirect_url = response.headers.get('Location')
                    if redirect_url:
                        logger.info(f"[{request_id}]   Got redirect to: {redirect_url}")
                        
                        # Make a new request to the redirect URL
                        if method == 'GET':
                            response = session.get(
                                redirect_url,
                                headers=headers,
                                timeout=30,
                                allow_redirects=True
                            )
                        else:
                            response = session.post(
                                redirect_url,
                                data=body,
                                headers=headers,
                                timeout=30,
                                allow_redirects=True
                            )
                
                elapsed_ms = int((time.time() - start_time) * 1000)
                logger.info(f"[{request_id}] ← Backend responded {response.status_code} in {elapsed_ms}ms")
                
                # Send response
                self.send_response(response.status_code)
                
                # Forward important headers
                for key, value in response.headers.items():
                    if key.lower() in ['content-type', 'content-length']:
                        self.send_header(key, value)
                
                self.send_header('X-Gateway', GATEWAY_NAME)
                self.send_header('X-Request-Time', f'{elapsed_ms}ms')
                self.end_headers()
                
                if response.content:
                    self.wfile.write(response.content)
                
            except requests.exceptions.Timeout:
                logger.error(f"[{request_id}] ❌ Backend timeout")
                self.send_error(504, "Gateway Timeout")
            except requests.exceptions.ConnectionError as e:
                logger.error(f"[{request_id}] ❌ Backend connection error: {e}")
                self.send_error(502, "Bad Gateway")
            except Exception as e:
                logger.error(f"[{request_id}] ❌ Backend error: {e}")
                self.send_error(502, f"Bad Gateway")
                
        except Exception as e:
            logger.error(f"[{request_id}] ❌ Request error: {e}")
            self.send_error(500, f"Gateway error")

def run_gateway():
    try:
        server = socketserver.TCPServer(("0.0.0.0", PORT), IoTGatewayHandler)
        server.allow_reuse_address = True
        
        logger.info(f"✅ Gateway ready on port {PORT}")
        logger.info(f"🌍 Debug: http://localhost:{PORT}/debug")
        logger.info(f"🌍 Health: http://localhost:{PORT}/health")
        logger.info(f"🌍 Ping: http://localhost:{PORT}/ping/test")
        
        server.serve_forever()
        
    except KeyboardInterrupt:
        logger.info("\n👋 Shutting down...")
        server.shutdown()
    except Exception as e:
        logger.error(f"❌ Failed to start: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_gateway()