//! Pocket Link firmware (RP2040).
//!
//! The phone (USB host) sees a composite device:
//!   * USB Audio Class 1.0 headset: 48 kHz stereo S16LE "headphones" (phone -> us, mixed to mono) and
//!     "microphone" (us -> phone). Android routes call audio to it like any USB-C headset.
//!   * Vendor data interface (class 0xFF, bulk IN/OUT, 64-byte packets): the Pocket app
//!     receives the caller's audio and sends back the agent's voice, both as 16 kHz mono S16LE.
//!
//! There is no microphone or speaker on the board: audio is looped between the two interfaces.
//! See PROTOCOL.md for the packet format.
#![no_std]
#![no_main]

mod fir;
mod resample;
mod ring;
mod vendor;

use panic_halt as _;
use rp2040_hal as hal;

use embedded_hal::digital::OutputPin;
use fugit::ExtU32;
use hal::{clocks::init_clocks_and_plls, pac, usb::UsbBus, Clock, Sio, Watchdog};
use usb_device::{class_prelude::*, prelude::*};
use usbd_audio::{AudioClassBuilder, Format, StreamConfig, TerminalType};

use resample::{Decimator3, Interpolator3};
use ring::Ring;
use vendor::VendorData;

#[link_section = ".boot2"]
#[used]
pub static BOOT2_FIRMWARE: [u8; 256] = rp2040_boot2::BOOT_LOADER_W25Q080;

const XTAL_HZ: u32 = 12_000_000;
const FW_MAJOR: u8 = 0;
const FW_MINOR: u8 = 1;

// USB identity. 0x1209/0x0001 is the pid.codes *test* ID: fine for development,
// register a real PID (https://pid.codes) before shipping units.
const USB_VID: u16 = 0x1209;
const USB_PID: u16 = 0x0001;

// Data-channel packet format: [MAGIC, type, payload_len, seq] + payload (<= 60 bytes)
const MAGIC: u8 = 0x50;
const T_PCM: u8 = 0x01;
const T_STATUS: u8 = 0x02;
const T_CTRL: u8 = 0x03;
const CTRL_FLUSH_MIC: u8 = 0x01;
const CTRL_BOOTLOADER: u8 = 0x02;
const CTRL_STATUS: u8 = 0x03;
const PCM_SAMPLES_PER_PKT: usize = 30;

const MIC_PREBUFFER: usize = 320; // 20 ms @ 16 kHz before (re)starting playback
const MIC_MAX: usize = 3200; // 200 ms latency cap
const SPK_MAX: usize = 3200;

static mut USB_ALLOC: Option<UsbBusAllocator<UsbBus>> = None;
static mut MIC16: Ring<4096> = Ring::new(); // agent voice from the app (16 kHz)
static mut SPK16: Ring<4096> = Ring::new(); // caller voice to the app (16 kHz)

#[hal::entry]
fn main() -> ! {
    let mut p = pac::Peripherals::take().unwrap();
    let mut watchdog = Watchdog::new(p.WATCHDOG);
    let clocks = init_clocks_and_plls(
        XTAL_HZ, p.XOSC, p.CLOCKS, p.PLL_SYS, p.PLL_USB, &mut p.RESETS, &mut watchdog,
    )
    .ok()
    .unwrap();
    let timer = hal::Timer::new(p.TIMER, &mut p.RESETS, &clocks);
    let sio = Sio::new(p.SIO);
    let pins = hal::gpio::Pins::new(p.IO_BANK0, p.PADS_BANK0, sio.gpio_bank0, &mut p.RESETS);
    let mut led = pins.gpio25.into_push_pull_output();
    let _ = clocks.system_clock.freq();

    // SAFETY: single-threaded, initialised once before use, never moved.
    #[allow(static_mut_refs)]
    let alloc: &'static UsbBusAllocator<UsbBus> = unsafe {
        USB_ALLOC = Some(UsbBusAllocator::new(UsbBus::new(
            p.USBCTRL_REGS, p.USBCTRL_DPRAM, clocks.usb_clock, true, &mut p.RESETS,
        )));
        USB_ALLOC.as_ref().unwrap()
    };
    #[allow(static_mut_refs)]
    let (mic16, spk16) = unsafe { (&mut MIC16, &mut SPK16) };

    let mut audio = AudioClassBuilder::new()
        .input(StreamConfig::new_discrete(Format::S16le, 1, &[48000], TerminalType::InMicrophone).unwrap())
        // Stereo: Android 16's mixer aborts audioserver on a mono USB output ("HAL channel mask 0x1 not
        // supported for mixed output"). The two channels are averaged back to mono below.
        .output(StreamConfig::new_discrete(Format::S16le, 2, &[48000], TerminalType::OutHeadphones).unwrap())
        .build(alloc)
        .unwrap();
    let mut data = VendorData::new(alloc);

    let mut dev = UsbDeviceBuilder::new(alloc, UsbVidPid(USB_VID, USB_PID))
        .strings(&[StringDescriptors::default()
            .manufacturer("Pocket")
            .product("Pocket Link")
            .serial_number("PL-REVA")])
        .unwrap()
        .composite_with_iads()
        .max_packet_size_0(64)
        .unwrap()
        .max_power(100)
        .unwrap()
        .build();

    watchdog.start(500_000u32.micros());

    let mut dec = Decimator3::new();
    let mut interp = Interpolator3::new();
    let mut mic_frame = [0u8; 96]; // 48 samples @ 48 kHz = 1 ms
    let mut mic_frame_ready = false;
    let mut mic_playing = false;
    let mut spk_pkt = [0u8; 64];
    let mut spk_pkt_pending = false;
    let mut status_pending = false;
    let mut status_pkt = [0u8; 4 + 16];
    let mut seq_out: u8 = 0;
    let mut rx = [0u8; 64];
    let mut iso = [0u8; 256];
    let mut last_status = timer.get_counter();
    let mut last_led = timer.get_counter();
    let mut led_on = false;

    loop {
        watchdog.feed();
        dev.poll(&mut [&mut audio, &mut data]);
        let configured = dev.state() == UsbDeviceState::Configured;
        let spk_active = configured && audio.output_alt_setting().unwrap_or(0) == 1;
        let mic_active = configured && audio.input_alt_setting().unwrap_or(0) == 1;

        // ---- phone -> us (caller's voice, 48 kHz) -> 16 kHz ring for the app
        if let Ok(n) = audio.read(&mut iso) {
            for s in iso[..n & !3].chunks_exact(4) {
                let l = i16::from_le_bytes([s[0], s[1]]) as i32;
                let r = i16::from_le_bytes([s[2], s[3]]) as i32;
                if let Some(y) = dec.push(((l + r) / 2) as i16) {
                    spk16.push(y);
                }
            }
            spk16.trim_to(SPK_MAX);
        }

        // ---- us -> phone (agent's voice): one 1 ms frame per USB frame
        if mic_active {
            if !mic_frame_ready {
                if !mic_playing && mic16.len() >= MIC_PREBUFFER {
                    mic_playing = true;
                }
                for i in 0..16 {
                    let x = if mic_playing {
                        match mic16.pop() {
                            Some(v) => v,
                            None => {
                                mic16.underflows = mic16.underflows.wrapping_add(1);
                                mic_playing = false; // re-prime to avoid crackle
                                0
                            }
                        }
                    } else {
                        0
                    };
                    let y = interp.push(x);
                    for (j, v) in y.iter().enumerate() {
                        let b = v.to_le_bytes();
                        mic_frame[(i * 3 + j) * 2] = b[0];
                        mic_frame[(i * 3 + j) * 2 + 1] = b[1];
                    }
                }
                mic_frame_ready = true;
            }
            if audio.write(&mic_frame).is_ok() {
                mic_frame_ready = false;
            }
        } else {
            mic_playing = false;
        }

        // ---- app -> us: agent PCM and control packets
        if let Ok(n) = data.read(&mut rx) {
            let mut i = 0;
            while i + 4 <= n {
                if rx[i] != MAGIC {
                    break; // resynchronise on the next USB packet
                }
                let t = rx[i + 1];
                let len = rx[i + 2] as usize;
                let end = (i + 4 + len).min(n);
                let payload = &rx[i + 4..end];
                match t {
                    T_PCM => {
                        for s in payload.chunks_exact(2) {
                            mic16.push(i16::from_le_bytes([s[0], s[1]]));
                        }
                        mic16.trim_to(MIC_MAX);
                    }
                    T_CTRL => match payload.first() {
                        Some(&CTRL_FLUSH_MIC) => {
                            mic16.clear();
                            mic_playing = false;
                        }
                        Some(&CTRL_BOOTLOADER) => {
                            hal::rom_data::reset_to_usb_boot(1 << 25, 0);
                        }
                        Some(&CTRL_STATUS) => status_pending = true,
                        _ => {}
                    },
                    _ => {}
                }
                i = end;
            }
        }

        // ---- us -> app: caller PCM in 30-sample packets, plus periodic status
        if configured {
            if !spk_pkt_pending && spk_active && spk16.len() >= PCM_SAMPLES_PER_PKT {
                spk_pkt[0] = MAGIC;
                spk_pkt[1] = T_PCM;
                spk_pkt[2] = (PCM_SAMPLES_PER_PKT * 2) as u8;
                spk_pkt[3] = seq_out;
                seq_out = seq_out.wrapping_add(1);
                for k in 0..PCM_SAMPLES_PER_PKT {
                    let b = spk16.pop().unwrap_or(0).to_le_bytes();
                    spk_pkt[4 + 2 * k] = b[0];
                    spk_pkt[5 + 2 * k] = b[1];
                }
                spk_pkt_pending = true;
            }
            let now = timer.get_counter();
            if (now - last_status).to_millis() >= 500 {
                last_status = now;
                status_pending = true;
            }
            if spk_pkt_pending {
                if data.write(&spk_pkt).is_ok() {
                    spk_pkt_pending = false;
                }
            } else if status_pending {
                let flags = (configured as u8) | ((spk_active as u8) << 1) | ((mic_active as u8) << 2)
                    | ((mic_playing as u8) << 3);
                status_pkt[0] = MAGIC;
                status_pkt[1] = T_STATUS;
                status_pkt[2] = 16;
                status_pkt[3] = seq_out;
                let body: [u8; 16] = {
                    let mut b = [0u8; 16];
                    b[0] = flags;
                    b[1] = FW_MAJOR;
                    b[2] = FW_MINOR;
                    b[4..6].copy_from_slice(&(mic16.len() as u16).to_le_bytes());
                    b[6..8].copy_from_slice(&(spk16.len() as u16).to_le_bytes());
                    b[8..12].copy_from_slice(&mic16.underflows.to_le_bytes());
                    b[12..16].copy_from_slice(&spk16.overflows.to_le_bytes());
                    b
                };
                status_pkt[4..20].copy_from_slice(&body);
                if data.write(&status_pkt).is_ok() {
                    status_pending = false;
                    seq_out = seq_out.wrapping_add(1);
                }
            }
        }

        // ---- LED: off = no USB, solid = connected, blinking = call audio flowing
        let now = timer.get_counter();
        if spk_active || mic_active {
            if (now - last_led).to_millis() >= 250 {
                last_led = now;
                led_on = !led_on;
            }
        } else {
            led_on = configured;
        }
        if led_on {
            led.set_high().ok();
        } else {
            led.set_low().ok();
        }
    }
}
