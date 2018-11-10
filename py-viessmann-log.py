#!/usr/bin/python

import asyncio
import struct

import serial_asyncio

import vitotronic


def parse_degC(b):
    v, = struct.unpack('<h', b)
    return 0.1 * v


def parse_uint32(b):
    v, = struct.unpack('<L', b)
    return v


def parse_uint8(b):
    v, = struct.unpack('<B', b)
    return v


PARSE_BYTES = ('%s', vitotronic.hexlify)
PARSE_DEGC = ('%+6.1f', parse_degC)
PARSE_UINT4 = ('%u', parse_uint32)
PARSE_PCT = ('%u %%', parse_uint8)

request_data = [
    (0x00f8, 4, 'devid', PARSE_BYTES),
    (0x0800, 2, 'outdoor', PARSE_DEGC),
    (0x5525, 2, 'outdoor lp', PARSE_DEGC),
    (0x5527, 2, 'outdoor smooth', PARSE_DEGC),
    (0x0802, 2, 'boiler', PARSE_DEGC),
    (0x0810, 2, 'boiler lp', PARSE_DEGC),
    (0x0804, 2, 'hotwater', PARSE_DEGC),
    (0x080C, 2, 'flow', PARSE_DEGC),
    (0x080a, 2, 'ret', PARSE_DEGC),
    (0x2544, 2, 'circuit', PARSE_DEGC),
    (0x088a, 4, 'starts', PARSE_UINT4),
    (0x08a7, 4, 'runtime', PARSE_UINT4),
    (0x0a3c, 1, 'pwr_pump', PARSE_PCT),
    (0xa38f, 1, 'pwr_burn', PARSE_PCT),
    (0x0c24, 2, 'flow', PARSE_BYTES),
    (0x0808, 2, 'exhaust', PARSE_DEGC)
]


class TickTimer:
    def __init__(self, vito_proto):
        self.vito_proto = vito_proto

    async def poll_msg(self, addr, payload_len):
        self.vito_proto.clear_rx_queue()
        if self.vito_proto.request_read(addr, payload_len):
            return
        for ticks in range(10):  # wait max. 10 seconds for answer
            await asyncio.sleep(0.1)
            msg = self.vito_proto.pop_rx_queue()
            if msg is None:
                continue
            msgtype, method, rx_addr, payload = msg
            if msgtype == 1 and method == 1 and rx_addr == addr and len(payload) == payload_len:
                return payload
        return None

    async def tick(self):
        while True:
            for addr, payload_len, tag, (fmt, parser) in request_data:

                payload = await self.poll_msg(addr, payload_len)
                if payload is None:
                    continue

                val = parser(payload)
                pfmt = '%%s = %s' % fmt
                print(pfmt % (tag, val))

            await asyncio.sleep(5.0)


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

    tick_timer = TickTimer(vito_proto)
    loop.create_task(tick_timer.tick())

    loop.run_forever()


if __name__ == '__main__':
    main()
