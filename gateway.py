#!/usr/bin/env python3
"""
IoT Gateway for SIM900A GSM Module
Accepts HTTP requests from ESP32+SIM900A, forwards HTTPS to backend
Version: 2.0.0 - With debug endpoint and redirect handling
"""

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

# ============================================
# CONFIGURATION - Read from environment variables
# ============================================

# Port that Render provides (always use this)
PORT = int(os.environ.get("PORT", 10000))

# Your backend URL (set this in Render environment variables)
BACKEND_URL = os.environ.get("BACKEND_URL", "https://pool-table-backend-jukw.onrender.com")

# Gateway name for logging
GATEWAY_NAME = os.environ.get("GATEWAY_NAME", "iot-gateway")

# Enable/disable detailed logging
DEBUG = os.environ.get("DEBUG", "False").lower() == "true"

# ============================================
# LOGGING SETUP
# ============================================

# Configure logging to stdout (Render captures this)
logging.basicConfig(
    level=logging.DEBUG if DEBUG else logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(GATEWAY_NAME)

# Log startup configuration
logger.info("=" * 60)
logger.info(f"🚀 Starting IoT Gateway v2.0.0")
logger.info(f"📡 Listening on port: {PORT}")
logger.info(f"🔄 Forwarding to backend: {BACKEND_URL}")
logger.info(f"🔍 Debug mode: {DEBUG}")
logger.info("=" * 60)

# ============================================
# REQUEST HANDLER
# ============================================

class IoTGatewayHandler(http.server.BaseHTTPRequestHandler):
    """Handles HTTP requests from ESP32 and forwards to backend"""
    
    # Disable DNS lookups (faster, use IPs only)
    def address_string(self):
        return str(self.client_address[0])
    
    def log_message(self, format, *args):
        """Override to use our structured logging"""
        logger.info(f"{self.client_address[0]} - {format % args}")
    
    def do_GET(self):
        """Handle GET requests with special debug endpoint"""
        if self.path == '/debug':
            self.handle_debug()
        elif self.path == '/health':
            self.handle_health()
        else:
            self.handle_request('GET')
    
    def do_POST(self):
        """Handle POST requests (payments, tamper alerts)"""
        self.handle_request('POST')
    
    def do_OPTIONS(self):
        """Handle CORS preflight requests"""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
    
    def handle_debug(self):
        """Debug endpoint to check gateway configuration"""
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain')
        self.end_headers()
        
        # Get local IP
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)
        
        # Build debug info
        debug_info = []
        debug_info.append("=" * 50)
        debug_info.append("IoT GATEWAY DEBUG INFORMATION")
        debug_info.append("=" * 50)
        debug_info.append(f"Timestamp: {datetime.now().isoformat()}")
        debug_info.append(f"Gateway Name: {GATEWAY_NAME}")
        debug_info.append(f"Version: 2.0.0")
        debug_info.append(f"Hostname: {hostname}")
        debug_info.append(f"Local IP: {local_ip}")
        debug_info.append(f"Listening Port: {PORT}")
        debug_info.append(f"Backend URL: {BACKEND_URL}")
        debug_info.append(f"Debug Mode: {DEBUG}")
        debug_info.append("")
        debug_info.append("CLIENT INFORMATION:")
        debug_info.append(f"  Client IP: {self.client_address[0]}")
        debug_info.append(f"  Client Port: {self.client_address[1]}")
        debug_info.append("")
        debug_info.append("REQUEST HEADERS RECEIVED:")
        for key, value in self.headers.items():
            debug_info.append(f"  {key}: {value}")
        debug_info.append("")
        debug_info.append("ENVIRONMENT VARIABLES:")
        debug_info.append(f"  PORT: {PORT}")
        debug_info.append(f"  BACKEND_URL: {BACKEND_URL}")
        debug_info.append(f"  GATEWAY_NAME: {GATEWAY_NAME}")
        debug_info.append(f"  DEBUG: {DEBUG}")
        debug_info.append("")
        debug_info.append("=" * 50)
        debug_info.append("Gateway is ready to forward requests!")
        debug_info.append("=" * 50)
        
        # Send response
        self.wfile.write("\n".join(debug_info).encode())
        logger.info(f"Debug info sent to {self.client_address[0]}")
    
    def handle_health(self):
        """Health check endpoint for Render"""
        try:
            # Test backend connectivity
            test_response = requests.get(f"{BACKEND_URL}/health", timeout=5)
            backend_status = "healthy" if test_response.status_code == 200 else "unhealthy"
            backend_code = test_response.status_code
        except Exception as e:
            backend_status = "unreachable"
            backend_code = str(e)
        
        health_data = {
            "status": "healthy",
            "gateway": GATEWAY_NAME,
            "version": "2.0.0",
            "timestamp": datetime.now().isoformat(),
            "uptime": time.time() - start_time if 'start_time' in globals() else 0,
            "backend": {
                "url": BACKEND_URL,
                "status": backend_status,
                "response": str(backend_code)
            }
        }
        
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(health_data, indent=2).encode())
    
    def handle_request(self, method):
        """Common request handler for all HTTP methods"""
        
        # Start timing the request
        start_time = time.time()
        request_id = f"{int(start_time * 1000)}-{self.client_address[0]}"
        
        try:
            # Read request body for POST/PUT
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length) if content_length > 0 else None
            
            # Log incoming request
            logger.info(f"[{request_id}] → {method} {self.path} from {self.client_address[0]}")
            
            # Construct backend URL
            backend_url = f"{BACKEND_URL}{self.path}"
            
            # Prepare headers to forward
            headers = {
                'Content-Type': self.headers.get('Content-Type', 'application/json'),
                'X-Forwarded-For': self.client_address[0],
                'X-Forwarded-Proto': 'http',
                'X-Forwarded-Host': self.headers.get('Host', ''),
                'X-Gateway-Id': GATEWAY_NAME,
                'X-Request-Id': request_id,
                'User-Agent': 'IoT-Gateway/2.0'
            }
            
            # Add original host if present
            if 'Host' in self.headers:
                headers['X-Original-Host'] = self.headers['Host']
            
            if DEBUG:
                logger.debug(f"[{request_id}]   Forwarding to: {backend_url}")
                if body:
                    try:
                        body_str = body.decode('utf-8', errors='ignore')[:200]
                        logger.debug(f"[{request_id}]   Payload: {body_str}")
                    except:
                        pass
            
            # Forward request to backend
            try:
                # Use a session for connection reuse
                session = requests.Session()
                
                if method == 'GET':
                    response = session.get(
                        backend_url,
                        headers=headers,
                        timeout=30,
                        allow_redirects=False  # Don't follow redirects
                    )
                else:  # POST
                    response = session.post(
                        backend_url,
                        data=body,
                        headers=headers,
                        timeout=30,
                        allow_redirects=False
                    )
                
                # Calculate processing time
                elapsed_ms = int((time.time() - start_time) * 1000)
                
                # Log backend response
                logger.info(f"[{request_id}] ← Backend responded {response.status_code} in {elapsed_ms}ms")
                
                # If we get a redirect from backend, follow it manually
                if response.status_code in [301, 302, 307, 308]:
                    redirect_url = response.headers.get('Location')
                    if redirect_url:
                        logger.info(f"[{request_id}]   Following redirect to: {redirect_url}")
                        
                        # Make new request to redirect URL
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
                        
                        logger.info(f"[{request_id}]   After redirect: {response.status_code}")
                
                # Send response back to client
                self.send_response(response.status_code)
                
                # Forward relevant headers
                for key, value in response.headers.items():
                    if key.lower() in ['content-type', 'content-length', 'location']:
                        self.send_header(key, value)
                
                # Add gateway info headers
                self.send_header('X-Gateway', GATEWAY_NAME)
                self.send_header('X-Request-Time', f'{elapsed_ms}ms')
                self.send_header('X-Request-Id', request_id)
                
                self.end_headers()
                
                # Send response body
                if response.content:
                    self.wfile.write(response.content)
                    if DEBUG:
                        try:
                            content_preview = response.content[:200].decode('utf-8', errors='ignore')
                            logger.debug(f"[{request_id}]   Response body: {content_preview}")
                        except:
                            pass
                
            except requests.exceptions.Timeout:
                logger.error(f"[{request_id}] ❌ Backend timeout")
                self.send_error(504, "Gateway Timeout - Backend not responding")
                
            except requests.exceptions.ConnectionError as e:
                logger.error(f"[{request_id}] ❌ Backend connection error: {e}")
                self.send_error(502, "Bad Gateway - Cannot connect to backend")
                
            except Exception as e:
                logger.error(f"[{request_id}] ❌ Backend error: {e}")
                self.send_error(502, f"Bad Gateway - {str(e)}")
                
        except Exception as e:
            logger.error(f"[{request_id}] ❌ Request handling error: {e}")
            self.send_error(500, f"Gateway error: {str(e)}")
        
        finally:
            # Log request completion
            total_ms = int((time.time() - start_time) * 1000)
            if DEBUG:
                logger.debug(f"[{request_id}] ✓ Request completed in {total_ms}ms")

# ============================================
# CUSTOM SERVER WITH HEALTH CHECK
# ============================================

class GatewayServer(socketserver.TCPServer):
    """Custom server that allows address reuse"""
    allow_reuse_address = True

def run_gateway():
    """Start the gateway server"""
    global start_time
    start_time = time.time()
    
    try:
        # Create server
        server = GatewayServer(("0.0.0.0", PORT), IoTGatewayHandler)
        
        logger.info(f"✅ Gateway is ready and accepting connections")
        logger.info(f"🌍 Public URL: http://localhost:{PORT} (or your Render URL)")
        logger.info(f"📝 Debug endpoint: http://localhost:{PORT}/debug")
        logger.info(f"📝 Health endpoint: http://localhost:{PORT}/health")
        logger.info(f"📝 Test with: curl http://localhost:{PORT}/ping/test")
        logger.info("Press Ctrl+C to stop\n")
        
        # Start server
        server.serve_forever()
        
    except PermissionError:
        logger.error(f"❌ Permission denied for port {PORT}. Try using a port > 1024.")
        sys.exit(1)
    except OSError as e:
        logger.error(f"❌ Failed to start server: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("\n👋 Shutting down gateway...")
        server.shutdown()
        logger.info("Gateway stopped")

# ============================================
# MAIN ENTRY POINT
# ============================================

if __name__ == "__main__":
    run_gateway()