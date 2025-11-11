"""
Infrastructure Health Check Script

Verifies all Docker services are running and healthy.

Usage:
    python scripts/check_infrastructure_health.py
"""

import sys
import time
from typing import List, Dict, Any

import requests
from loguru import logger


SERVICES = {
    "postgres": {
        "name": "PostgreSQL",
        "port": 5432,
        "health_check": "connection"
    },
    "minio": {
        "name": "MinIO",
        "port": 9000,
        "health_endpoint": "http://localhost:9000/minio/health/live"
    },
    "mlflow": {
        "name": "MLflow",
        "port": 5000,
        "health_endpoint": "http://localhost:5000/health"
    },
    "prefect": {
        "name": "Prefect",
        "port": 4200,
        "health_endpoint": "http://localhost:4200/api/health"
    }
}


def check_service_http(service_name: str, endpoint: str, timeout: int = 5) -> bool:
    """
    Check service health via HTTP endpoint.
    
    Args:
        service_name: Name of service
        endpoint: HTTP endpoint to check
        timeout: Request timeout in seconds
        
    Returns:
        True if healthy
    """
    try:
        response = requests.get(endpoint, timeout=timeout)
        
        if response.status_code == 200:
            logger.info(f"✅ {service_name}: Healthy")
            return True
        else:
            logger.error(f"❌ {service_name}: Unhealthy (status {response.status_code})")
            return False
            
    except requests.exceptions.ConnectionError:
        logger.error(f"❌ {service_name}: Connection failed")
        return False
    except requests.exceptions.Timeout:
        logger.error(f"❌ {service_name}: Timeout")
        return False
    except Exception as e:
        logger.error(f"❌ {service_name}: Error - {e}")
        return False


def check_postgres(timeout: int = 5) -> bool:
    """Check PostgreSQL connection"""
    try:
        import psycopg2
        
        conn = psycopg2.connect(
            host="localhost",
            port=5432,
            database="forecast_labor",
            user="forecast_user",
            password="forecast_password",
            connect_timeout=timeout
        )
        conn.close()
        
        logger.info("✅ PostgreSQL: Healthy")
        return True
        
    except Exception as e:
        logger.error(f"❌ PostgreSQL: {e}")
        return False


def check_all_services() -> Dict[str, bool]:
    """
    Check all infrastructure services.
    
    Returns:
        Dictionary of service -> health status
    """
    results = {}
    
    logger.info("Checking infrastructure health...")
    
    # Check PostgreSQL
    results["postgres"] = check_postgres()
    
    # Check HTTP services
    for service_id, config in SERVICES.items():
        if service_id == "postgres":
            continue  # Already checked
        
        if "health_endpoint" in config:
            results[service_id] = check_service_http(
                config["name"],
                config["health_endpoint"]
            )
    
    return results


def main():
    """Main entry point"""
    logger.info("=" * 60)
    logger.info("Infrastructure Health Check")
    logger.info("=" * 60)
    
    results = check_all_services()
    
    # Summary
    total = len(results)
    healthy = sum(1 for v in results.values() if v)
    unhealthy = total - healthy
    
    logger.info("=" * 60)
    logger.info(f"Health Check Summary: {healthy}/{total} services healthy")
    logger.info("=" * 60)
    
    if unhealthy > 0:
        logger.error(f"❌ {unhealthy} service(s) unhealthy")
        logger.error("Run 'make up' to start services")
        sys.exit(1)
    else:
        logger.info("✅ All services healthy")
        sys.exit(0)


if __name__ == "__main__":
    main()

