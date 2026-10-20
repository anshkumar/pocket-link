//! Host-side checks for the Pocket Link firmware:
//!  1. USB descriptors: enumerate the real class code against a mock bus and dump the
//!     device + configuration descriptors (parsed/validated by check_descriptors.py)
//!  2. Resampler: frequency response / round-trip of the 48k<->16k path
#[path = "../../pocket-link-fw/src/fir.rs"] mod fir;
#[path = "../../pocket-link-fw/src/resample.rs"] mod resample;
#[path = "../../pocket-link-fw/src/ring.rs"] mod ring;
#[path = "../../pocket-link-fw/src/vendor.rs"] mod vendor;

use std::cell::RefCell;
use usb_device::bus::PollResult;
use usb_device::class_prelude::*;
use usb_device::prelude::*;
use usb_device::endpoint::{EndpointAddress, EndpointType};
use usb_device::{Result as UResult, UsbDirection};
use usbd_audio::{AudioClassBuilder, Format, StreamConfig, TerminalType};

#[derive(Default)]
struct St { setup: Option<[u8; 8]>, ep0_in: Vec<u8>, in_done: bool, next_ep: u8, status_out: bool }
struct MockBus { st: RefCell<St> }
unsafe impl Sync for MockBus {}

impl UsbBus for MockBus {
    fn alloc_ep(&mut self, dir: UsbDirection, addr: Option<EndpointAddress>, _t: EndpointType, _m: u16, _i: u8) -> UResult<EndpointAddress> {
        if let Some(a) = addr { return Ok(a); }
        let mut st = self.st.borrow_mut();
        st.next_ep += 1;
        Ok(EndpointAddress::from_parts((st.next_ep as usize + 1) / 2, dir))
    }
    fn enable(&mut self) {}
    fn reset(&self) {}
    fn set_device_address(&self, _a: u8) {}
    fn write(&self, ep: EndpointAddress, buf: &[u8]) -> UResult<usize> {
        if ep.index() == 0 { let mut st = self.st.borrow_mut(); st.ep0_in.extend_from_slice(buf); st.in_done = true; }
        Ok(buf.len())
    }
    fn read(&self, ep: EndpointAddress, buf: &mut [u8]) -> UResult<usize> {
        let mut st = self.st.borrow_mut();
        if ep.index() == 0 {
            if let Some(s) = st.setup.take() { buf[..8].copy_from_slice(&s); return Ok(8); }
            if st.status_out { st.status_out = false; return Ok(0); }
        }
        Err(UsbError::WouldBlock)
    }
    fn set_stalled(&self, _e: EndpointAddress, _s: bool) {}
    fn is_stalled(&self, _e: EndpointAddress) -> bool { false }
    fn suspend(&self) {}
    fn resume(&self) {}
    fn poll(&self) -> PollResult {
        let mut st = self.st.borrow_mut();
        if st.setup.is_some() { return PollResult::Data { ep_out: 0, ep_in_complete: 0, ep_setup: 1 }; }
        if st.in_done { st.in_done = false; return PollResult::Data { ep_out: 0, ep_in_complete: 1, ep_setup: 0 }; }
        if st.status_out { return PollResult::Data { ep_out: 1, ep_in_complete: 0, ep_setup: 0 }; }
        PollResult::None
    }
}

fn get_descriptor(dev: &mut UsbDevice<MockBus>, classes: &mut [&mut dyn UsbClass<MockBus>], bus: &MockBus, dtype: u8, idx: u8) -> Vec<u8> {
    bus.st.borrow_mut().ep0_in.clear();
    bus.st.borrow_mut().setup = Some([0x80, 0x06, idx, dtype, 0x09, 0x04, 0x00, 0x04]); // wLength 1024
    for _ in 0..200 { dev.poll(classes); }
    bus.st.borrow_mut().status_out = true;
    for _ in 0..5 { dev.poll(classes); }
    bus.st.borrow().ep0_in.clone()
}

fn main() {
    let alloc = UsbBusAllocator::new(MockBus { st: RefCell::new(St::default()) });
    // --- identical to firmware main.rs ---
    let mut audio = AudioClassBuilder::new()
        .input(StreamConfig::new_discrete(Format::S16le, 1, &[48000], TerminalType::InMicrophone).unwrap())
        .output(StreamConfig::new_discrete(Format::S16le, 1, &[48000], TerminalType::OutHeadphones).unwrap())
        .build(&alloc).unwrap();
    let mut data = vendor::VendorData::new(&alloc);
    let mut dev = UsbDeviceBuilder::new(&alloc, UsbVidPid(0x1209, 0x0001))
        .strings(&[StringDescriptors::default().manufacturer("Pocket").product("Pocket Link").serial_number("PL-REVA")]).unwrap()
        .composite_with_iads().max_packet_size_0(64).unwrap().max_power(100).unwrap().build();
    // ---
    let bus: &MockBus = unsafe { &*(dev.bus() as *const MockBus) };
    let d = get_descriptor(&mut dev, &mut [&mut audio, &mut data], bus, 1, 0);
    let c = get_descriptor(&mut dev, &mut [&mut audio, &mut data], bus, 2, 0);
    std::fs::write("device.bin", &d).unwrap();
    std::fs::write("config.bin", &c).unwrap();
    println!("device descriptor {} bytes, configuration {} bytes", d.len(), c.len());

    // --- resampler checks
    use resample::{Decimator3, Interpolator3};
    for &f in &[300.0f64, 1000.0, 3400.0, 6000.0, 7000.0, 10000.0, 14000.0] {
        let mut dec = Decimator3::new();
        let mut out = vec![];
        for n in 0..48000 {
            let x = (8000.0 * (2.0 * std::f64::consts::PI * f * n as f64 / 48000.0).sin()) as i16;
            if let Some(y) = dec.push(x) { out.push(y as f64); }
        }
        let rms = (out[2000..].iter().map(|v| v * v).sum::<f64>() / (out.len() - 2000) as f64).sqrt();
        println!("decimate {:>6.0} Hz -> gain {:>6.1} dB", f, 20.0 * (rms / (8000.0 / 2f64.sqrt())).log10());
    }
    for &f in &[300.0f64, 1000.0, 3400.0, 7000.0] {
        let mut it = Interpolator3::new();
        let mut out = vec![];
        for n in 0..16000 {
            let x = (8000.0 * (2.0 * std::f64::consts::PI * f * n as f64 / 16000.0).sin()) as i16;
            out.extend(it.push(x).iter().map(|&v| v as f64));
        }
        let rms = (out[6000..].iter().map(|v| v * v).sum::<f64>() / (out.len() - 6000) as f64).sqrt();
        // image at 16k - f should be suppressed: estimate by comparing to ideal sine
        println!("interpolate {:>6.0} Hz -> gain {:>6.1} dB", f, 20.0 * (rms / (8000.0 / 2f64.sqrt())).log10());
    }
    let mut r: ring::Ring<8> = ring::Ring::new();
    for i in 0..10 { r.push(i); }
    assert_eq!(r.len(), 8); assert_eq!(r.pop(), Some(2)); assert_eq!(r.overflows, 2);
    println!("ring ok");
}
