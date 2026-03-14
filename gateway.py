#!/usr/bin/env python3
"""
IoT Gateway for SIM900A GSM Module
Accepts HTTP requests from ESP32+SIM900A, forwards HTTPS to backend

This gateway solves the problem where SIM900A cannot handle HTTPS.
It acts as a simple HTTP-to-HTTPS proxy.

Deploy this as a separate service on Render.com
"""

import http.server
import socketserver
import requests
import logging
import os
import sys
import json
import time
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
logger.info(f"🚀 Starting IoT Gateway v1.0.0")
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
        """Handle GET requests (heartbeats, status checks)"""
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
    
    def handle_request(self, method):
        """Common request handler for all HTTP methods"""
        
        # Start timing the request
        start_time = time.time()
        request_id = f"{int(start_time * 1000)}-{self.client_address[0]}"
        
        try:
            # Read request body for POST/PUT
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length) if content_length > 0 else None
            
            # Parse body for logging
            body_str = ""
            if body:
                try:
                    body_str = body.decode('utf-8', errors='ignore')
                except:
                    body_str = "[binary data]"
            
            # Log incoming request
            logger.info(f"[{request_id}] → {method} {self.path} from {self.client_address[0]}")
            if body and DEBUG:
                logger.debug(f"[{request_id}]   Payload: {body_str[:200]}")
            
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
                'User-Agent': 'IoT-Gateway/1.0'
            }
            
            if DEBUG:
                logger.debug(f"[{request_id}]   Forwarding to: {backend_url}")
            
            # Forward request to backend
            try:
                if method == 'GET':
                    response = requests.get(
                        backend_url,
                        headers=headers,
                        timeout=30,
                        allow_redirects=False  # Don't follow redirects, let caller handle
                    )
                else:  # POST
                    response = requests.post(
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
                
                # Send response back to client
                self.send_response(response.status_code)
                
                # Forward relevant headers
                for key, value in response.headers.items():
                    if key.lower() in ['content-type', 'content-length', 'location']:
                        self.send_header(key, value)
                
                # Add gateway info headers
                self.send_header('X-Gateway', GATEWAY_NAME)
                self.send_header('X-Request-Time', f'{elapsed_ms}ms')
                
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
            logger.debug(f"[{request_id}] ✓ Request completed in {total_ms}ms")

# ============================================
# HEALTH CHECK ENDPOINT (for Render)
# ============================================

def health_check():
    """Simple health check that Render can use"""
    try:
        # Test backend connectivity
        test_response = requests.get(f"{BACKEND_URL}/health", timeout=5)
        backend_status = "healthy" if test_response.status_code == 200 else "unhealthy"
    except:
        backend_status = "unreachable"
    
    return {
        "status": "healthy",
        "gateway": GATEWAY_NAME,
        "version": "1.0.0",
        "timestamp": datetime.now().isoformat(),
        "backend": {
            "url": BACKEND_URL,
            "status": backend_status
        },
        "uptime": time.time() - start_time if 'start_time' in globals() else 0
    }

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