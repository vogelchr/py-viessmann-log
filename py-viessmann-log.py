#!/usr/bin/python

import asyncio
import struct
import time

import serial_asyncio
from influxdb import InfluxDBClient

import vitotronic


def bcd(v):
    hi_nibble = (v & 0xf0) >> 4
    lo_nibble = v & 0x0f
    return 10 * hi_nibble + lo_nibble


def viessmann_decode_systime(payload):
    tm_year = 100 * bcd(payload[0]) + bcd(payload[1])
    tm_mon = bcd(payload[2])
    tm_mday = bcd(payload[3])
    tm_wday = bcd(payload[4] - 1)
    if tm_wday < 0:
        tm_wday += 7
    tm_hour = bcd(payload[5])
    tm_min = bcd(payload[6])
    tm_sec = bcd(payload[7])
    tm_yday = 0
    tm_isdst = 0
    return tm_year, tm_mon, tm_mday, tm_hour, tm_min, tm_sec, tm_wday, \
           tm_yday, tm_isdst


def parse_payload(what, payload):
    if what == 'degC':
        v, = struct.unpack('<h', payload)
        return '%+6.1f', 0.1 * v
    if what == 'uint32':
        v, = struct.unpack('<L', payload)
        return '%9u', v
    if what == 'uint16':
        v, = struct.unpack('<H', payload)
        return '%5d', v
    if what == 'uint8':
        v, = struct.unpack('B', payload)
        return '%3d', v
    if what == 'uint8_half':
        v, = struct.unpack('B', payload)
        return '%3d', v * 0.5
    if what == 'systime':
        v = viessmann_decode_systime(payload)
        return '%-26s', time.strftime('%A, %Y-%m-%d %H:%M:%S', v)

    return '%s', vitotronic.hexlify(payload)


request_data = [
    (0x00f8, 8, 'devid', None),
    (0x088e, 8, 'system_time', 'systime'),  # system time

    (0x0800, 2, 'temp_outdoor', 'degC'),
    (0x0802, 2, 'temp_boiler', 'degC'),
    (0x0804, 2, 'temp_reservoir', 'degC'),
    (0x0808, 2, 'temp_exhaust', 'degC'),
#    (0x080a, 2, 'temp_ret', 'degC'),
    (0x080c, 2, 'temp_flow', 'degC'),
    (0x080e, 2, 'temp_080e', 'degC'),
    (0x081a, 2, 'temp_suppl', 'degC'),

    (0x7663, 1, 'pump_a1', 'uint8'), # Heizkreispumpe A1 
    (0x2906, 1, 'pump_a1m1', 'uint8'), # Heizkreispumpe A1M1
    (0x3906, 1, 'pump_m2', 'uint8'), # Heizkreispumpe M2
    (0x4906, 1, 'pump_m3', 'uint8'), # Heizkreispumpe M3

    (0x0845, 1, 'pump_chrg', 'uint8'),  # storage charge pump
    (0x0846, 1, 'pump_circ', 'uint8'),  # circulation pump


    (0x0a10, 1, 'sw_0a10', 'uint8'),  # switching valve heating/hot_water/...

#    (0x01d4, 2, 'temp_vl2sec', 'degC'),
#    (0x01d8, 2, 'temp_vl3sec', 'degC'),

#   (0x2900, 8, 'raw_2900', None),
#   (0x2900, 2, 'temp_2900', 'degC'),
#   (0x2906, 1, 'pump_2906', 'uint8'), # A1M1
#   (0x3900, 8, 'raw_3900', None),
#   (0x3900, 2, 'temp_3900', 'degC'),
#   (0x3906, 1, 'pump_2906', 'uint8'), # M2
#   (0x4900, 8, 'raw_4900', None),
#   (0x4900, 2, 'temp_4900', 'degC'),
#   (0x4906, 1, 'pump_2906', 'uint8'), # M3

    (0x5525, 2, 'temp_outdoor_lp', 'degC'),  # lowpass
    (0x5527, 2, 'temp_outdoor_sm', 'degC'),  # smooth

    (0x0a90, 1, 'sw_ea1_c0', 'uint8'), # EA1: Kontakt 0
    (0x0a91, 1, 'sw_ea1_c1', 'uint8'), # EA1: Kontakt 1
    (0x0a92, 1, 'sw_ea1_c2', 'uint8'), # EA1: Kontakt 2
    (0x0a95, 1, 'sw_ea1_c2', 'uint8'), # EA1: Relais 0


#    (0x7574, 4, 'cono', 'uint32'),  # "consomption"?

    (0x088a, 4, 'burn_st', 'uint32'),  # starts
    (0x08a7, 4, 'burn_rt', 'uint32'),  # runtime
#    (0x0c24, 2, 'burn_flow', 'uint16'),  # flow in l/h?
    (0xa38f, 1, 'brn_pwr', 'uint8_half'),  # burner power in %
]


async def poll_msg(vito_proto, addr, length):
    vito_proto.clear_rx_queue()
    if vito_proto.request_read(addr, length):
        return None
    for ticks in range(10):
        await asyncio.sleep(0.1)

        if vito_proto.rx_nak_ctr:
            return 'NAK received.'
        if vito_proto.rx_to_ctr:
            return 'Timeout on RX (signalled by protocol).'
        if vito_proto.rx_err_ctr:
            return 'Error: Protocol error on RX.'
        if vito_proto.rx_queue:
            msgtype, method, address, payload = vito_proto.rx_queue.pop(0)
            if address == addr:
                if len(payload) != length:
                    return 'Error: wrong length, expected %d, got %d' % (length, len(payload))
                return msgtype, method, address, payload
    return 'Error: Timeout waiting on answer.'


class PollMainLoop:
    def __init__(self, vito_proto, influxdb):
        self.vito_proto = vito_proto
        self.influxdb = influxdb

    async def tick(self):
        influx_fields = dict()

        while True:
            influx_fields.clear()

            print('==============')
            for addr, length, tag, what in request_data:
                ret = await poll_msg(self.vito_proto, addr, length)
                if ret is None:
                    break  # not in correct rx state, still unsynced, don't even try

                if type(ret) != tuple:
                    print('0x%04x [%d/%s]: %s' % (addr, length, what, ret))
                    continue

                fmt, v = parse_payload(what, ret[3])  # ret[3] == payload
                pfmt = '%%-20s = %s' % fmt
                print(pfmt % (tag, v))

                if type(v) == float or type(v) == int:
                    influx_fields[tag] = v

            if influx_fields:
                js_body = [{
                    'measurement': 'viessmann',
                    'fields': influx_fields
                }]
                self.influxdb.write_points(js_body, database='heating')

            await asyncio.sleep(10.0)


def main():
    import argparse
    import logging

    parser = argparse.ArgumentParser()
    parser.add_argument('-d', '--debug', help='Debug mode.', action='store_true')

    parser.add_argument('-t', '--tty', metavar='DEV', default='/dev/ttyUSB0',
                        help='Serial port, [def: /dev/ttyUSB0]', )

    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO,
                        format='%(asctime)-15s %(message)s')

    loop = asyncio.get_event_loop()

    vito_transp, vito_proto = loop.run_until_complete(
        serial_asyncio.create_serial_connection(
            loop, vitotronic.VitoTronicProtocol, '/dev/ttyUSB0',
            baudrate=4800, bytesize=8, parity='E', stopbits=2
        )
    )

    influxdb = InfluxDBClient('localhost', 8086)

    poll_mainloop = PollMainLoop(vito_proto, influxdb)
    loop.create_task(poll_mainloop.tick())

    loop.run_forever()


if __name__ == '__main__':
    main()
