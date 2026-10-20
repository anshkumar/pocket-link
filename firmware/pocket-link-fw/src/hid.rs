//! HID interface: a touch screen, a keyboard and a consumer-control block on one interface,
//! so the Pocket app can tap, swipe and type on the phone through the adapter.
//!
//! The firmware does not compose input itself. The app sends finished HID reports in
//! `0x04 HID` packets (see PROTOCOL.md) and this class hands them to the interrupt endpoint.
//! Nothing else on the board can produce a report, so input only ever comes from the app
//! that holds the vendor data interface.
//!
//! Report IDs:
//!   1  touch screen: `[1, tip|in_range<<1, contact id, x lo, x hi, y lo, y hi, contact count]`, x/y 0..32767
//!   2  keyboard:     `[2, modifiers, 0, k1..k6]` (boot-protocol layout, USB HID usage codes)
//!   3  consumer:     `[3, usage lo, usage hi]`, e.g. AC Home 0x0223, AC Back 0x0224

use usb_device::class_prelude::*;
use usb_device::control::{Recipient, Request, RequestType};

const USB_CLASS_HID: u8 = 0x03;
const DESC_HID: u8 = 0x21;
const DESC_REPORT: u8 = 0x22;
const REQ_GET_REPORT: u8 = 0x01;
const REQ_GET_IDLE: u8 = 0x02;
const REQ_GET_PROTOCOL: u8 = 0x03;
const REQ_SET_REPORT: u8 = 0x09;
const REQ_SET_IDLE: u8 = 0x0A;
const REQ_SET_PROTOCOL: u8 = 0x0B;

pub const MAX_REPORT: usize = 16;

#[rustfmt::skip]
pub const REPORT_DESCRIPTOR: &[u8] = &[
    // ---- Touch screen, report ID 1. Shaped for the kernel's hid-multitouch driver (Contact ID and
    // Contact Count present): that driver marks the device INPUT_PROP_DIRECT, which is what makes
    // Android treat it as a touch screen on its own display rather than a pointer.
    0x05, 0x0D,        // Usage Page (Digitizer)
    0x09, 0x04,        // Usage (Touch Screen)
    0xA1, 0x01,        // Collection (Application)
    0x85, 0x01,        //   Report ID (1)
    0x09, 0x22,        //   Usage (Finger)
    0xA1, 0x02,        //   Collection (Logical)
    0x09, 0x42,        //     Usage (Tip Switch)
    0x09, 0x32,        //     Usage (In Range)
    0x15, 0x00,        //     Logical Minimum (0)
    0x25, 0x01,        //     Logical Maximum (1)
    0x75, 0x01,        //     Report Size (1)
    0x95, 0x02,        //     Report Count (2)
    0x81, 0x02,        //     Input (Data, Var, Abs)
    0x95, 0x06,        //     Report Count (6)
    0x81, 0x03,        //     Input (Const) padding
    0x09, 0x51,        //     Usage (Contact Identifier)
    0x25, 0x7F,        //     Logical Maximum (127)
    0x75, 0x08,        //     Report Size (8)
    0x95, 0x01,        //     Report Count (1)
    0x81, 0x02,        //     Input (Data, Var, Abs)
    0x05, 0x01,        //     Usage Page (Generic Desktop)
    0x09, 0x30,        //     Usage (X)
    0x09, 0x31,        //     Usage (Y)
    0x15, 0x00,        //     Logical Minimum (0)
    0x26, 0xFF, 0x7F,  //     Logical Maximum (32767)
    0x75, 0x10,        //     Report Size (16)
    0x95, 0x02,        //     Report Count (2)
    0x81, 0x02,        //     Input (Data, Var, Abs)
    0xC0,              //   End Collection
    0x05, 0x0D,        //   Usage Page (Digitizer)
    0x09, 0x54,        //   Usage (Contact Count)
    0x15, 0x00,        //   Logical Minimum (0)
    0x25, 0x0A,        //   Logical Maximum (10)
    0x75, 0x08,        //   Report Size (8)
    0x95, 0x01,        //   Report Count (1)
    0x81, 0x02,        //   Input (Data, Var, Abs)
    0xC0,              // End Collection
    // ---- Keyboard, report ID 2
    0x05, 0x01,        // Usage Page (Generic Desktop)
    0x09, 0x06,        // Usage (Keyboard)
    0xA1, 0x01,        // Collection (Application)
    0x85, 0x02,        //   Report ID (2)
    0x05, 0x07,        //   Usage Page (Keyboard)
    0x19, 0xE0,        //   Usage Minimum (Left Control)
    0x29, 0xE7,        //   Usage Maximum (Right GUI)
    0x15, 0x00,        //   Logical Minimum (0)
    0x25, 0x01,        //   Logical Maximum (1)
    0x75, 0x01,        //   Report Size (1)
    0x95, 0x08,        //   Report Count (8)
    0x81, 0x02,        //   Input (Data, Var, Abs) modifiers
    0x95, 0x01,        //   Report Count (1)
    0x75, 0x08,        //   Report Size (8)
    0x81, 0x03,        //   Input (Const) reserved
    0x95, 0x05,        //   Report Count (5)
    0x75, 0x01,        //   Report Size (1)
    0x05, 0x08,        //   Usage Page (LEDs)
    0x19, 0x01,        //   Usage Minimum (Num Lock)
    0x29, 0x05,        //   Usage Maximum (Kana)
    0x91, 0x02,        //   Output (Data, Var, Abs) LEDs
    0x95, 0x01,        //   Report Count (1)
    0x75, 0x03,        //   Report Size (3)
    0x91, 0x03,        //   Output (Const) padding
    0x95, 0x06,        //   Report Count (6)
    0x75, 0x08,        //   Report Size (8)
    0x15, 0x00,        //   Logical Minimum (0)
    0x25, 0x65,        //   Logical Maximum (101)
    0x05, 0x07,        //   Usage Page (Keyboard)
    0x19, 0x00,        //   Usage Minimum (0)
    0x29, 0x65,        //   Usage Maximum (101)
    0x81, 0x00,        //   Input (Data, Array) keys
    0xC0,              // End Collection
    // ---- Consumer control, report ID 3
    0x05, 0x0C,        // Usage Page (Consumer)
    0x09, 0x01,        // Usage (Consumer Control)
    0xA1, 0x01,        // Collection (Application)
    0x85, 0x03,        //   Report ID (3)
    0x15, 0x00,        //   Logical Minimum (0)
    0x26, 0xFF, 0x03,  //   Logical Maximum (1023)
    0x19, 0x00,        //   Usage Minimum (0)
    0x2A, 0xFF, 0x03,  //   Usage Maximum (1023)
    0x75, 0x10,        //   Report Size (16)
    0x95, 0x01,        //   Report Count (1)
    0x81, 0x00,        //   Input (Data, Array)
    0xC0,              // End Collection
];

pub struct Hid<'a, B: UsbBus> {
    iface: InterfaceNumber,
    name: StringIndex,
    ep_in: EndpointIn<'a, B>,
    protocol: u8,
    idle: u8,
}

impl<'a, B: UsbBus> Hid<'a, B> {
    pub fn new(alloc: &'a UsbBusAllocator<B>) -> Self {
        Self {
            iface: alloc.interface(),
            name: alloc.string(),
            ep_in: alloc.interrupt(MAX_REPORT as u16, 1),
            protocol: 1,
            idle: 0,
        }
    }

    /// Send one report (first byte = report ID). WouldBlock while the previous one is in flight.
    pub fn write(&self, report: &[u8]) -> usb_device::Result<usize> {
        self.ep_in.write(report)
    }

    fn is_mine(&self, req: &Request) -> bool {
        req.recipient == Recipient::Interface && req.index == u8::from(self.iface) as u16
    }
}

impl<B: UsbBus> UsbClass<B> for Hid<'_, B> {
    fn get_configuration_descriptors(&self, writer: &mut DescriptorWriter) -> usb_device::Result<()> {
        writer.interface_alt(self.iface, 0, USB_CLASS_HID, 0, 0, Some(self.name))?;
        let len = REPORT_DESCRIPTOR.len() as u16;
        writer.write(DESC_HID, &[0x11, 0x01, 0x00, 0x01, DESC_REPORT, len as u8, (len >> 8) as u8])?;
        writer.endpoint(&self.ep_in)?;
        Ok(())
    }

    fn get_string(&self, index: StringIndex, _lang_id: LangID) -> Option<&str> {
        if index == self.name {
            Some("Pocket Link Input")
        } else {
            None
        }
    }

    fn control_in(&mut self, xfer: ControlIn<B>) {
        let req = *xfer.request();
        if !self.is_mine(&req) {
            return;
        }
        match (req.request_type, req.request) {
            (RequestType::Standard, Request::GET_DESCRIPTOR) => {
                let (dtype, _) = req.descriptor_type_index();
                let len = REPORT_DESCRIPTOR.len() as u16;
                match dtype {
                    DESC_REPORT => {
                        xfer.accept_with_static(REPORT_DESCRIPTOR).ok();
                    }
                    DESC_HID => {
                        xfer.accept_with(&[9, DESC_HID, 0x11, 0x01, 0x00, 0x01, DESC_REPORT, len as u8, (len >> 8) as u8]).ok();
                    }
                    _ => {}
                }
            }
            (RequestType::Class, REQ_GET_REPORT) => {
                // Nothing is pressed unless the app says so.
                let id = req.value as u8;
                xfer.accept_with(&[id, 0, 0, 0, 0, 0, 0, 0, 0]).ok();
            }
            (RequestType::Class, REQ_GET_IDLE) => {
                xfer.accept_with(&[self.idle]).ok();
            }
            (RequestType::Class, REQ_GET_PROTOCOL) => {
                xfer.accept_with(&[self.protocol]).ok();
            }
            _ => {}
        }
    }

    fn control_out(&mut self, xfer: ControlOut<B>) {
        let req = *xfer.request();
        if !self.is_mine(&req) || req.request_type != RequestType::Class {
            return;
        }
        match req.request {
            REQ_SET_IDLE => {
                self.idle = (req.value >> 8) as u8;
                xfer.accept().ok();
            }
            REQ_SET_PROTOCOL => {
                self.protocol = req.value as u8;
                xfer.accept().ok();
            }
            REQ_SET_REPORT => {
                // Keyboard LEDs: there are none.
                xfer.accept().ok();
            }
            _ => {}
        }
    }
}
