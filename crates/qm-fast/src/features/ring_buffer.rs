//! O(1) rolling statistics buffer for historical feature cache.
//!
//! Pre-allocated ring buffer that computes mean, std, min, max
//! incrementally as new values are pushed. Zero allocation after init.

use pyo3::prelude::*;

/// Fixed-capacity ring buffer with O(1) rolling statistics.
#[pyclass]
pub struct RingBuffer {
    data: Vec<f64>,
    capacity: usize,
    head: usize,
    count: usize,
    sum: f64,
    sum_sq: f64,
    min_val: f64,
    max_val: f64,
}

#[pymethods]
impl RingBuffer {
    #[new]
    fn new(capacity: usize) -> Self {
        Self {
            data: vec![0.0; capacity],
            capacity,
            head: 0,
            count: 0,
            sum: 0.0,
            sum_sq: 0.0,
            min_val: f64::INFINITY,
            max_val: f64::NEG_INFINITY,
        }
    }

    /// Push a new value, evicting the oldest if at capacity.
    fn push(&mut self, value: f64) {
        if self.count == self.capacity {
            // Evict oldest
            let old = self.data[self.head];
            self.sum -= old;
            self.sum_sq -= old * old;
        } else {
            self.count += 1;
        }

        self.data[self.head] = value;
        self.sum += value;
        self.sum_sq += value * value;
        self.head = (self.head + 1) % self.capacity;

        // Min/max need full scan after eviction (O(n) worst case).
        // For small windows (10-20) this is acceptable.
        self.min_val = f64::INFINITY;
        self.max_val = f64::NEG_INFINITY;
        let start = if self.count == self.capacity {
            0
        } else {
            self.capacity - self.count
        };
        for i in 0..self.count {
            let idx = (start + i) % self.capacity;
            let v = self.data[idx];
            if v < self.min_val {
                self.min_val = v;
            }
            if v > self.max_val {
                self.max_val = v;
            }
        }
    }

    /// Rolling mean.
    fn mean(&self) -> f64 {
        if self.count == 0 {
            return 0.0;
        }
        self.sum / self.count as f64
    }

    /// Rolling standard deviation (population).
    fn std(&self) -> f64 {
        if self.count < 2 {
            return 0.0;
        }
        let n = self.count as f64;
        let variance = (self.sum_sq / n) - (self.sum / n).powi(2);
        if variance <= 0.0 {
            0.0
        } else {
            variance.sqrt()
        }
    }

    /// Rolling minimum.
    fn min(&self) -> f64 {
        self.min_val
    }

    /// Rolling maximum.
    fn max(&self) -> f64 {
        self.max_val
    }

    /// Number of values currently stored.
    fn len(&self) -> usize {
        self.count
    }

    /// Whether the buffer is empty.
    fn is_empty(&self) -> bool {
        self.count == 0
    }
}
