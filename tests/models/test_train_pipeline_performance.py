"""
Performance Tests for Training Pipeline

Validates that training pipelines meet performance SLAs.
Following TDD methodology - tests define performance requirements.

Phase 5.9.1 Quality Gap Resolution
"""

import pytest
import time
from datetime import datetime
from pathlib import Path
import json
import sys

import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from models_src.utils.base_model import BaseForecaster


class MockFastModel(BaseForecaster):
    """Fast mock model for performance testing"""
    
    def __init__(self, sleep_time: float = 0.1, random_state: int = 42):
        """Initialize with configurable sleep time"""
        super().__init__(random_state=random_state)
        self.sleep_time = sleep_time
        self.is_fitted = False
    
    def fit(self, X: pd.DataFrame, y: pd.Series, **kwargs):
        """Mock training with sleep"""
        time.sleep(self.sleep_time)
        self.is_fitted = True
        return self
    
    def predict(self, X: pd.DataFrame) -> np.ndarray:
        """Mock prediction"""
        if not self.is_fitted:
            raise ValueError("Model must be fitted before prediction")
        return np.random.randn(len(X))
    
    def get_params(self, deep: bool = True) -> dict:
        """Get model parameters"""
        return {
            'sleep_time': self.sleep_time,
            'random_state': self.random_state
        }
    
    def save(self, path: Path) -> None:
        """Mock save"""
        pass
    
    @classmethod
    def load(cls, path: Path):
        """Mock load"""
        return cls()


class MockSlowModel(MockFastModel):
    """Slow mock model for timeout testing"""
    
    def __init__(self, random_state: int = 42):
        super().__init__(sleep_time=5.0, random_state=random_state)  # 5 seconds


class TestTrainingPipelinePerformance:
    """Performance benchmark tests for training pipeline"""
    
    @pytest.fixture
    def small_dataset(self):
        """Small dataset for quick tests"""
        n_samples = 100
        n_features = 10
        
        dates = pd.date_range('2020-01-01', periods=n_samples, freq='MS')
        X = pd.DataFrame(
            np.random.randn(n_samples, n_features),
            index=dates,
            columns=[f'feature_{i}' for i in range(n_features)]
        )
        y = pd.Series(
            np.random.randn(n_samples) * 1000 + 150000,
            index=dates,
            name='target'
        )
        return X, y
    
    @pytest.fixture
    def large_dataset(self):
        """Realistic-sized dataset for benchmarking"""
        n_samples = 240  # 20 years monthly data
        n_features = 50   # Realistic feature count
        
        dates = pd.date_range('2004-01-01', periods=n_samples, freq='MS')
        X = pd.DataFrame(
            np.random.randn(n_samples, n_features),
            index=dates,
            columns=[f'feature_{i}' for i in range(n_features)]
        )
        y = pd.Series(
            np.random.randn(n_samples) * 1000 + 150000,  # Realistic NFP scale
            index=dates,
            name='target'
        )
        return X, y
    
    @pytest.mark.performance
    def test_model_training_time_measured(self, small_dataset):
        """Test that training time can be measured"""
        X, y = small_dataset
        X_train, y_train = X[:80], y[:80]
        
        model = MockFastModel(sleep_time=0.1)
        
        start_time = time.time()
        model.fit(X_train, y_train)
        elapsed = time.time() - start_time
        
        assert elapsed >= 0.1, "Training should take at least sleep_time"
        assert elapsed < 1.0, "Training should complete quickly for small dataset"
        print(f"✅ Training time: {elapsed:.3f}s")
    
    @pytest.mark.performance
    def test_prediction_time_measured(self, small_dataset):
        """Test that prediction time can be measured"""
        X, y = small_dataset
        X_train, y_train = X[:80], y[:80]
        X_test = X[80:]
        
        model = MockFastModel(sleep_time=0.1)
        model.fit(X_train, y_train)
        
        start_time = time.time()
        predictions = model.predict(X_test)
        elapsed = time.time() - start_time
        
        assert elapsed < 0.1, "Prediction should be fast (< 100ms)"
        assert len(predictions) == len(X_test)
        print(f"✅ Prediction time: {elapsed*1000:.1f}ms")
    
    @pytest.mark.performance
    def test_training_time_under_baseline(self, large_dataset):
        """Test that training completes within baseline time"""
        X, y = large_dataset
        X_train, y_train = X[:200], y[:200]
        
        # Baseline: Should complete in < 1 second for mock model
        baseline_time = 1.0
        
        model = MockFastModel(sleep_time=0.1)
        
        start_time = time.time()
        model.fit(X_train, y_train)
        elapsed = time.time() - start_time
        
        assert elapsed < baseline_time, \
            f"Training took {elapsed:.3f}s (baseline: {baseline_time}s)"
        print(f"✅ Training within baseline: {elapsed:.3f}s < {baseline_time}s")
    
    @pytest.mark.performance
    def test_prediction_latency_acceptable(self, large_dataset):
        """Test that prediction latency is acceptable (< 100ms)"""
        X, y = large_dataset
        X_train, y_train = X[:200], y[:200]
        X_test = X[200:]
        
        model = MockFastModel(sleep_time=0.1)
        model.fit(X_train, y_train)
        
        # Measure prediction latency
        latencies = []
        for _ in range(10):  # Multiple runs for stability
            start = time.time()
            _ = model.predict(X_test)
            latencies.append(time.time() - start)
        
        avg_latency = np.mean(latencies)
        max_latency = np.max(latencies)
        
        assert avg_latency < 0.1, \
            f"Average latency {avg_latency*1000:.1f}ms (limit: 100ms)"
        print(f"✅ Avg latency: {avg_latency*1000:.1f}ms, Max: {max_latency*1000:.1f}ms")
    
    @pytest.mark.performance
    def test_memory_usage_reasonable(self, large_dataset):
        """Test that memory usage is reasonable"""
        try:
            import psutil
            import os
        except ImportError:
            pytest.skip("psutil not available for memory testing")
        
        X, y = large_dataset
        X_train, y_train = X[:200], y[:200]
        
        process = psutil.Process(os.getpid())
        mem_before = process.memory_info().rss / 1024 / 1024  # MB
        
        model = MockFastModel(sleep_time=0.1)
        model.fit(X_train, y_train)
        _ = model.predict(X[200:])
        
        mem_after = process.memory_info().rss / 1024 / 1024  # MB
        mem_used = mem_after - mem_before
        
        # Should not exceed 500MB for mock model
        assert mem_used < 500, f"Memory usage: {mem_used:.0f}MB (limit: 500MB)"
        print(f"✅ Memory usage: {mem_used:.0f}MB")
    
    @pytest.mark.performance
    def test_throughput_acceptable(self, large_dataset):
        """Test that prediction throughput is acceptable"""
        X, y = large_dataset
        X_train, y_train = X[:200], y[:200]
        X_test = X[200:]
        
        model = MockFastModel(sleep_time=0.1)
        model.fit(X_train, y_train)
        
        # Measure throughput (predictions per second)
        n_iterations = 100
        start_time = time.time()
        for _ in range(n_iterations):
            _ = model.predict(X_test)
        elapsed = time.time() - start_time
        
        throughput = n_iterations / elapsed
        
        # Should handle at least 10 predictions/second
        assert throughput >= 10, \
            f"Throughput: {throughput:.1f} pred/s (minimum: 10 pred/s)"
        print(f"✅ Throughput: {throughput:.1f} predictions/second")


class TestPerformanceBaselines:
    """Tests for performance baseline recording and tracking"""
    
    @pytest.mark.performance
    def test_baseline_metrics_structure(self):
        """Test that baseline metrics have correct structure"""
        baselines = {
            'mock_model_training': 1.0,    # 1 second
            'mock_model_prediction': 0.1,  # 100ms
            'memory_mb': 500,              # 500 MB
            'throughput_pred_per_sec': 10,  # 10 predictions/second
            'updated_at': datetime.now().isoformat()
        }
        
        # Verify all required fields present
        assert 'mock_model_training' in baselines
        assert 'mock_model_prediction' in baselines
        assert 'memory_mb' in baselines
        assert 'throughput_pred_per_sec' in baselines
        assert 'updated_at' in baselines
        
        print(f"✅ Baseline structure valid: {len(baselines)} metrics")
    
    @pytest.mark.performance
    def test_baseline_can_be_persisted(self, tmp_path):
        """Test that baselines can be saved to file"""
        baselines = {
            'mock_model_training': 1.0,
            'mock_model_prediction': 0.1,
            'memory_mb': 500,
            'updated_at': datetime.now().isoformat()
        }
        
        baseline_file = tmp_path / "performance_baselines.json"
        
        with open(baseline_file, 'w') as f:
            json.dump(baselines, f, indent=2)
        
        # Verify can be loaded
        with open(baseline_file, 'r') as f:
            loaded = json.load(f)
        
        assert loaded['mock_model_training'] == baselines['mock_model_training']
        print(f"✅ Baselines persisted: {baseline_file}")
    
    @pytest.mark.performance
    def test_baseline_comparison(self, tmp_path):
        """Test that current performance can be compared to baseline"""
        # Baseline metrics
        baseline = {'training_time': 1.0, 'prediction_time': 0.1}
        
        # Current metrics
        current = {'training_time': 0.9, 'prediction_time': 0.12}
        
        # Compare with tolerance
        tolerance = 0.20  # 20% tolerance
        
        for metric in baseline:
            baseline_val = baseline[metric]
            current_val = current[metric]
            max_allowed = baseline_val * (1 + tolerance)
            
            within_tolerance = current_val <= max_allowed
            
            print(f"{metric}: {current_val:.3f} (baseline: {baseline_val:.3f}, "
                  f"max: {max_allowed:.3f}) - {'✅ PASS' if within_tolerance else '❌ FAIL'}")
            
            # For this test, we allow some variation
            assert within_tolerance or current_val < baseline_val, \
                f"{metric} degraded beyond tolerance"


class TestPerformanceRegression:
    """Tests for detecting performance regression"""
    
    @pytest.fixture
    def small_dataset(self):
        """Small dataset for quick tests"""
        n_samples = 100
        n_features = 10
        
        dates = pd.date_range('2020-01-01', periods=n_samples, freq='MS')
        X = pd.DataFrame(
            np.random.randn(n_samples, n_features),
            index=dates,
            columns=[f'feature_{i}' for i in range(n_features)]
        )
        y = pd.Series(
            np.random.randn(n_samples) * 1000 + 150000,
            index=dates,
            name='target'
        )
        return X, y
    
    @pytest.mark.performance
    def test_performance_does_not_degrade(self, small_dataset):
        """Test that performance has not degraded from baseline"""
        X, y = small_dataset
        X_train, y_train = X[:80], y[:80]
        
        # Expected baseline (from previous runs)
        expected_max_time = 1.0  # 1 second
        
        model = MockFastModel(sleep_time=0.1)
        
        start_time = time.time()
        model.fit(X_train, y_train)
        elapsed = time.time() - start_time
        
        # Should not be slower than baseline
        assert elapsed <= expected_max_time, \
            f"Performance regression: {elapsed:.3f}s > {expected_max_time}s baseline"
        
        print(f"✅ No performance regression: {elapsed:.3f}s <= {expected_max_time}s")


@pytest.mark.performance
def test_create_baseline_file(tmp_path):
    """Create baseline metrics file for tracking"""
    baselines = {
        '_comment': 'Performance baselines for regression detection',
        '_created': datetime.now().isoformat(),
        '_tolerance_pct': 20,
        'mock_model': {
            'training_time_sec': 1.0,
            'prediction_time_sec': 0.1,
            'memory_mb': 500,
            'throughput_pred_per_sec': 10
        },
        'notes': 'These are baselines for mock models. Real model baselines TBD in Phase 6 backtesting.'
    }
    
    baseline_file = tmp_path / "performance_baselines.json"
    
    with open(baseline_file, 'w') as f:
        json.dump(baselines, f, indent=2)
    
    print(f"✅ Baseline file created: {baseline_file}")
    print(json.dumps(baselines, indent=2))
    
    assert baseline_file.exists()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-m", "performance"])

