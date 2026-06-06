"""
Setup configuration for forecast-labor package.
Makes the project properly installable for testing and development.
"""

from setuptools import setup, find_packages

setup(
    name="forecast-labor",
    version="0.1.0",
    description="Real-time U.S. Labor Market Forecasting Engine for Bittensor",
    author="Forecast Labor Team",
    python_requires=">=3.9",
    packages=find_packages(
        include=[
            "etl*",
            "seasonal*",
            "features*",
            "models_src*",
            "backtests*",
            "app*",
            "subnets*",
            "recon*",
        ]
    ),
    install_requires=[
        # Core dependencies are in requirements.txt
        # This is minimal for package structure
    ],
    extras_require={
        "dev": [
            "pytest>=7.4.0",
            "pytest-cov>=4.1.0",
            "pytest-mock>=3.11.1",
            "pytest-xdist>=3.3.1",
            "pytest-timeout>=2.1.0",
        ]
    },
    zip_safe=False,
)
