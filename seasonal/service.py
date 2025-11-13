"""
X-13 Seasonal Adjustment HTTP Service

Microservice that provides HTTP API for X-13ARIMA-SEATS seasonal adjustment.
Runs inside the X-13 Docker container.

Usage:
    python -m seasonal.service

Endpoints:
    POST /adjust - Run seasonal adjustment
    GET /health - Health check
"""

import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Dict, Any

import pandas as pd
from loguru import logger

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from seasonal.x13_service import X13Service


class X13Handler(BaseHTTPRequestHandler):
    """HTTP request handler for X-13 seasonal adjustment"""
    
    def __init__(self, *args, x13_service: X13Service = None, **kwargs):
        self.x13_service = x13_service or X13Service()
        super().__init__(*args, **kwargs)
    
    def do_GET(self):
        """Handle GET requests"""
        if self.path == "/health":
            self._handle_health()
        else:
            self._send_error(404, "Not Found")
    
    def do_POST(self):
        """Handle POST requests"""
        if self.path == "/adjust":
            self._handle_adjust()
        else:
            self._send_error(404, "Not Found")
    
    def _handle_health(self):
        """Health check endpoint"""
        response = {
            "status": "healthy",
            "service": "x13-seasonal-adjustment",
            "version": "1.0.0"
        }
        self._send_json(200, response)
    
    def _handle_adjust(self):
        """Seasonal adjustment endpoint"""
        try:
            # Read request body
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            request_data = json.loads(body.decode('utf-8'))
            
            # Extract parameters
            series_data = request_data.get("series")
            series_name = request_data.get("series_name", "series")
            spec_content = request_data.get("spec")
            regressors_data = request_data.get("regressors")
            save_output = request_data.get("save_output", True)
            
            if not series_data:
                self._send_error(400, "Missing 'series' in request")
                return
            
            if not spec_content:
                self._send_error(400, "Missing 'spec' in request")
                return
            
            # Convert series data to pandas Series
            if isinstance(series_data, dict):
                series = pd.Series(series_data)
                # If keys are date strings, convert to datetime index
                try:
                    series.index = pd.to_datetime(series.index)
                except:
                    pass
            else:
                series = pd.Series(series_data)
            
            # Convert regressors if provided
            regressors = None
            if regressors_data:
                try:
                    regressors = pd.DataFrame(regressors_data)
                    # Convert index to datetime if possible
                    try:
                        regressors.index = pd.to_datetime(regressors.index)
                    except:
                        pass
                    logger.info(f"Loaded {len(regressors.columns)} regressors")
                except Exception as e:
                    logger.warning(f"Failed to parse regressors: {e}")
            
            logger.info(f"Processing seasonal adjustment request for: {series_name}")
            logger.info(f"Series length: {len(series)}")
            
            # Run seasonal adjustment
            result = self.x13_service.run_seasonal_adjustment(
                series=series,
                series_name=series_name,
                spec_content=spec_content,
                regressors=regressors,
                save_output=save_output
            )
            
            # Convert Series/arrays to lists for JSON serialization
            json_result = {}
            for key, value in result.items():
                if isinstance(value, pd.Series):
                    json_result[key] = {
                        "values": value.tolist(),
                        "index": value.index.astype(str).tolist()
                    }
                elif isinstance(value, dict):
                    json_result[key] = value
                else:
                    json_result[key] = value
            
            logger.info(f"✅ Seasonal adjustment completed for: {series_name}")
            
            self._send_json(200, json_result)
            
        except Exception as e:
            logger.error(f"Error in seasonal adjustment: {e}")
            logger.exception(e)
            self._send_error(500, f"Internal Server Error: {str(e)}")
    
    def _send_json(self, status_code: int, data: Dict[str, Any]):
        """Send JSON response"""
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))
    
    def _send_error(self, status_code: int, message: str):
        """Send error response"""
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        error_response = {
            "error": message,
            "status_code": status_code
        }
        self.wfile.write(json.dumps(error_response).encode('utf-8'))
    
    def log_message(self, format, *args):
        """Override to use loguru instead of print"""
        logger.info(f"{self.address_string()} - {format % args}")


def create_handler(x13_service: X13Service):
    """Create handler with injected X13Service"""
    def handler(*args, **kwargs):
        X13Handler(*args, x13_service=x13_service, **kwargs)
    return handler


def main():
    """Main entry point"""
    # Configuration
    host = "0.0.0.0"
    port = 8000
    
    logger.info("=" * 60)
    logger.info("X-13 Seasonal Adjustment Service")
    logger.info("=" * 60)
    logger.info(f"Starting server on {host}:{port}")
    
    # Initialize X-13 service
    try:
        x13_service = X13Service()
        logger.info("✅ X-13 service initialized")
    except Exception as e:
        logger.error(f"❌ Failed to initialize X-13 service: {e}")
        sys.exit(1)
    
    # Create HTTP server
    handler = create_handler(x13_service)
    server = HTTPServer((host, port), handler)
    
    logger.info(f"🚀 Server ready at http://{host}:{port}")
    logger.info("Endpoints:")
    logger.info("  GET  /health  - Health check")
    logger.info("  POST /adjust  - Seasonal adjustment")
    logger.info("=" * 60)
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down server...")
        server.shutdown()
        logger.info("✅ Server stopped")


if __name__ == "__main__":
    main()

