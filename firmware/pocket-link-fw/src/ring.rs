//! Fixed-size single-producer/single-consumer ring of i16 samples (single-threaded use).

pub struct Ring<const N: usize> {
    buf: [i16; N],
    head: usize, // next write
    tail: usize, // next read
    len: usize,
    pub overflows: u32,
    pub underflows: u32,
}

impl<const N: usize> Ring<N> {
    pub const fn new() -> Self {
        Self { buf: [0; N], head: 0, tail: 0, len: 0, overflows: 0, underflows: 0 }
    }

    pub fn len(&self) -> usize {
        self.len
    }

    pub fn clear(&mut self) {
        self.head = 0;
        self.tail = 0;
        self.len = 0;
    }

    /// Push one sample; on overflow the oldest sample is dropped (keeps latency bounded).
    pub fn push(&mut self, s: i16) {
        if self.len == N {
            self.tail = (self.tail + 1) % N;
            self.len -= 1;
            self.overflows = self.overflows.wrapping_add(1);
        }
        self.buf[self.head] = s;
        self.head = (self.head + 1) % N;
        self.len += 1;
    }

    pub fn pop(&mut self) -> Option<i16> {
        if self.len == 0 {
            return None;
        }
        let s = self.buf[self.tail];
        self.tail = (self.tail + 1) % N;
        self.len -= 1;
        Some(s)
    }

    /// Drop samples until at most `keep` remain (latency trim).
    pub fn trim_to(&mut self, keep: usize) {
        while self.len > keep {
            self.tail = (self.tail + 1) % N;
            self.len -= 1;
        }
    }
}
