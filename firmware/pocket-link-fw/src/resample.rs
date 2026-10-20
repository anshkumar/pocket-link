//! 3:1 polyphase resamplers between the 48 kHz USB audio streams and the 16 kHz data channel.

use crate::fir::{FIR_Q15, TAPS};

/// 48 kHz -> 16 kHz: low-pass then keep every third sample.
pub struct Decimator3 {
    hist: [i32; TAPS],
    pos: usize,
    phase: u8,
}

impl Decimator3 {
    pub const fn new() -> Self {
        Self { hist: [0; TAPS], pos: 0, phase: 0 }
    }

    /// Feed one 48 kHz sample; returns a 16 kHz sample every third call.
    pub fn push(&mut self, x: i16) -> Option<i16> {
        self.hist[self.pos] = x as i32;
        self.pos = (self.pos + 1) % TAPS;
        self.phase += 1;
        if self.phase < 3 {
            return None;
        }
        self.phase = 0;
        let mut acc: i32 = 0;
        let mut idx = self.pos; // oldest sample
        for k in (0..TAPS).rev() {
            acc += self.hist[idx] * FIR_Q15[k];
            idx += 1;
            if idx == TAPS {
                idx = 0;
            }
        }
        Some(sat16(acc >> 15))
    }
}

/// 16 kHz -> 48 kHz: zero-stuff by three and low-pass (gain x3), polyphase form.
pub struct Interpolator3 {
    hist: [i32; TAPS / 3],
    pos: usize,
}

impl Interpolator3 {
    pub const fn new() -> Self {
        Self { hist: [0; TAPS / 3], pos: 0 }
    }

    /// Feed one 16 kHz sample, get three 48 kHz samples.
    pub fn push(&mut self, x: i16) -> [i16; 3] {
        const P: usize = TAPS / 3;
        self.hist[self.pos] = x as i32;
        let newest = self.pos;
        self.pos = (self.pos + 1) % P;
        let mut out = [0i16; 3];
        for (ph, o) in out.iter_mut().enumerate() {
            let mut acc: i32 = 0;
            let mut idx = newest;
            let mut k = ph;
            while k < TAPS {
                acc += self.hist[idx] * FIR_Q15[k];
                idx = if idx == 0 { P - 1 } else { idx - 1 };
                k += 3;
            }
            *o = sat16((acc * 3) >> 15);
        }
        out
    }
}

#[inline]
fn sat16(v: i32) -> i16 {
    if v > i16::MAX as i32 {
        i16::MAX
    } else if v < i16::MIN as i32 {
        i16::MIN
    } else {
        v as i16
    }
}
