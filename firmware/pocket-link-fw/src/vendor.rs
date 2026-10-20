//! Vendor-specific data interface (class 0xFF) with one bulk IN and one bulk OUT endpoint.
//! The Pocket app claims this interface through the Android USB host API.

use usb_device::class_prelude::*;

pub const IFACE_CLASS: u8 = 0xFF;
pub const IFACE_SUBCLASS: u8 = 0x50; // 'P'
pub const IFACE_PROTOCOL: u8 = 0x01; // protocol version 1
pub const MAX_PACKET: u16 = 64;

pub struct VendorData<'a, B: UsbBus> {
    iface: InterfaceNumber,
    name: StringIndex,
    ep_in: EndpointIn<'a, B>,
    ep_out: EndpointOut<'a, B>,
}

impl<'a, B: UsbBus> VendorData<'a, B> {
    pub fn new(alloc: &'a UsbBusAllocator<B>) -> Self {
        Self {
            iface: alloc.interface(),
            name: alloc.string(),
            ep_in: alloc.bulk(MAX_PACKET),
            ep_out: alloc.bulk(MAX_PACKET),
        }
    }

    /// Queue one packet (<= 64 bytes) to the app. WouldBlock if the previous one is still pending.
    pub fn write(&self, data: &[u8]) -> usb_device::Result<usize> {
        self.ep_in.write(data)
    }

    pub fn read(&self, data: &mut [u8]) -> usb_device::Result<usize> {
        self.ep_out.read(data)
    }
}

impl<B: UsbBus> UsbClass<B> for VendorData<'_, B> {
    fn get_configuration_descriptors(&self, writer: &mut DescriptorWriter) -> usb_device::Result<()> {
        writer.interface_alt(self.iface, 0, IFACE_CLASS, IFACE_SUBCLASS, IFACE_PROTOCOL, Some(self.name))?;
        writer.endpoint(&self.ep_in)?;
        writer.endpoint(&self.ep_out)?;
        Ok(())
    }

    fn get_string(&self, index: StringIndex, _lang_id: LangID) -> Option<&str> {
        if index == self.name {
            Some("Pocket Link Data")
        } else {
            None
        }
    }
}
