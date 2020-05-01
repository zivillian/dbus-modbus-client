from functools import partial
import logging

import device
from register import *

log = logging.getLogger()

# CT Type Identifier register to type name mapping
CT_TYPES = [
    'SCT01-50A/100A/200A',
    'SCT01-400A/800A',
    'Rogowski coil 600A-100mV',
    'SCT02-50A',
    'SCT02-100A',
    'SCT02-200A',
    'SCT02-400A',
    'SCT02-800A',
    'SCT03-50A',
    'SCT03-100A',
    'SCT03-200A',
    'Rogowski coil 400A-100mV',
    'Closed CT',
]

# CT Associated Voltage register to phase number mapping
CT_PHASE = {
    1:  0,                      # L1 forward
    16: 0,                      # L1 reverse
    2:  1,                      # L2 forward
    32: 1,                      # L2 reverse
    4:  2,                      # L3 forward
    64: 2,                      # L3 reverse
};

MAX_BUS_DEVICES = 10
MAX_CT_SLOTS    = 28

class Reg_cttype(Reg_uint16):
    def __str__(self):
        if self.value < len(CT_TYPES):
            return CT_TYPES[self.value]
        return str(self.value)

class Reg_ser(Reg_text):
    def __init__(self, base, *args):
        Reg.__init__(self, base, 4, *args)

    def decode(self, values):
        v = '%04d%06d' % (values[0], values[3] << 16 | values[2])
        return self.update(v)

class Reg_ver(Reg, int):
    def __new__(cls, *args):
        return int.__new__(cls)

    def __init__(self, base, *args):
        Reg.__init__(self, base, 2, *args)

    def __int__(self):
        v = self.value
        return v[0] << 16 | v[1]

    def __str__(self):
        return '%d.%d' % self.value

    def decode(self, values):
        return self.update((values[1], values[0]))

class PowerBox(device.EnergyMeter):
    productid = 0xb018
    productname = 'Smappee Power Box'
    min_fwver = (1, 44)

    def __init__(self, *args):
        super(PowerBox, self).__init__(*args)
        fw = Reg_ver(0x1624)
        self.read_register(fw)
        if fw.value < self.min_fwver:
            log.info('%s firmware %s is too old', self.productname, fw)
            raise Exception()

    def probe_device(self, n):
        base = 0x1480 + 0x20 * n

        regs = [
            Reg_uint16(base + 0x00, '/Device/%d/Type' % n),
            Reg_uint16(base + 0x01, '/Device/%d/Slots' % n),
            Reg_ser(   base + 0x00, '/Device/%d/Serial' % n),
            Reg_ver(   base + 0x04, '/Device/%d/FirmwareVersion' % n),
        ]

        if self.read_register(regs[0]) == 0:
            return

        slots = self.read_register(regs[1])

        for s in range(slots):
            addr = base + 0x0a + s + (s > 7)
            chan = chr(ord('A') + s)
            sreg = Reg_uint16(addr, '/Device/%d/Channel/%s/Slot' % (n, chan))
            self.slots.append(self.read_register(sreg))
            regs.append(sreg)

        self.info_regs += regs

    def probe_ct(self, n):
        regs = [
            Reg_uint16(0x1000 + n, '/CT/%d/Phase' % n, write=True),
            Reg_cttype(0x1100 + n, '/CT/%d/Type' % n),
            Reg_uint16(0x1140 + n, '/CT/%d/Slot' % n),
        ]

        if self.read_register(regs[2]) not in self.slots:
            return

        phase = CT_PHASE.get(self.read_register(regs[0]), 3)
        self.ct_phase[phase].append(n)

        self.info_regs += regs

    def add_phase(self, ph, ct):
        n = ph + 1

        self.voltage_regs += [
            Reg_float(0x0000 + 4 * ph, '/Ac/L%d/Voltage' % n, 1, '%.1f V'),
        ]

        self.current_regs += [
            Reg_float(0x0080 + 4 * ct, '/Ac/L%d/Current' % n, 1, '%.1f A'),
        ]

        self.power_regs += [
            Reg_float(0x0380 + 2 * ct, '/Ac/L%d/Power' % n, 1, '%.1f W'),
        ]

        self.energy_regs += [
            Reg_int32(0x3000 + 4 * ct, '/Ac/L%d/Energy/Forward' % n, 1000, '%.1f kWh'),
            Reg_int32(0x3002 + 4 * ct, '/Ac/L%d/Energy/Reverse' % n, 1000, '%.1f kWh')
        ]

    def init_virtual(self):
        mask = 0

        for n in range(3):
            if self.ct_phase[n]:
                mask |= 1 << self.ct_phase[n][0]

        self.write_register(Reg_int32(0x1400), mask)

        if not mask:
            return

        self.data_regs += [
            Reg_float(0x03c0, '/Ac/Power', 1, '%.1f W'),
            Reg_int32(0x3100, '/Ac/Energy/Forward', 1000, '%.1f kWh'),
            Reg_int32(0x3102, '/Ac/Energy/Reverse', 1000, '%.1f kWh'),
        ]

    def device_init(self):
        self.info_regs = [
            Reg_ser(  0x1620, '/Serial'),
            Reg_ver(  0x1624, '/FirmwareVersion'),
            Reg_float(0x03f6, '/Ac/FrequencyNominal', 1, '%.0f Hz'),
            Reg_uint16(0x1180, '/PhaseConfig', write=True),
        ]

        self.data_regs = [
            Reg_float(0x03f8, '/Ac/Frequency', 1, '%.1f Hz'),
        ]

        self.slots = []

        for n in range(MAX_BUS_DEVICES):
            self.probe_device(n)

        self.ct_phase = [[], [], [], []]
        self.voltage_regs = []
        self.current_regs = []
        self.power_regs = []
        self.energy_regs = []

        for n in range(MAX_CT_SLOTS):
            self.probe_ct(n)

        for n in range(3):
            if self.ct_phase[n]:
                self.add_phase(n, self.ct_phase[n][0])

        self.current_regs.sort(key=lambda r: r.base)
        self.power_regs.sort(key=lambda r: r.base)
        self.energy_regs.sort(key=lambda r: r.base)

        self.data_regs += [
            self.voltage_regs,
            self.current_regs,
            self.power_regs,
            self.energy_regs,
        ]

        self.init_virtual()

        # save settings to Power Box flash
        self.write_register(Reg_uint16(0xfde8), 1)

    def ct_identify(self, ct, path, val):
        self.write_register(Reg_uint16(0x0900 + ct), val)
        return False

    def device_init_late(self):
        for ct in self.ct_phase:
            for n in ct:
                cb = partial(self.ct_identify, n)
                self.dbus.add_path('/CT/%d/Identify' % n, None,
                                   writeable=True, onchangecallback=cb)

    def dbus_write_register(self, reg, path, val):
        super(PowerBox, self).dbus_write_register(reg, path, val)
        self.reinit()

    def get_ident(self):
        return 'smappee_%s' % self.info['/Serial']

models = {
    5400: {
        'model':    'MOD-VAC-1',
        'handler':  PowerBox,
    },
}

device.add_handler(device.ModelRegister(0x1620, models))
