#!/usr/bin/python

import asyncio
import logging

import serial_asyncio
from aiohttp import web

import viessmann_decode
import vitotronic

log = logging.getLogger('py-viessmann-log')


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
            msgtype, method, rx_addr, payload = vito_proto.rx_queue.pop(0)
            if rx_addr == addr:
                if len(payload) != length:
                    return 'Error: wrong length, expected %d, got %d' % (length, len(payload))
                return msgtype, method, rx_addr, payload
            else:
                return 'Error: wrong address, expected %d, got %d' % (addr, rx_addr)
    return 'Error: Timeout waiting on answer.'


class PollMainLoop:
    def __init__(self, vito_proto, influx_client, varlist, args):
        self.vito_proto = vito_proto
        self.influx_client = influx_client
        self.varlist = varlist
        self.args = args

        self.vito_lock = asyncio.Lock()

    async def handle_web_query(self, request):
        try:
            addr = int(request.match_info['addr'], 16)
            if addr < 0 or addr > 0xffff:
                raise RuntimeError('address not in range 0000 .. ffff')

            tag_or_len = request.match_info['tag_or_len']
            length, decode_fct, fmt = viessmann_decode.gen_decoder(tag_or_len)
        except Exception as e:
            log.error('Exception while parsing URL, match_info=%s',
                      request.match_info, exc_info=True)
            return web.Response(status=500, text='Exception while parsing URL.')

        async with self.vito_lock:
            ret = await poll_msg(self.vito_proto, addr, length)

        if ret is None:
            return web.Response(status=500, text='Serial port not ready.')

        if type(ret) != tuple:  # error message
            return web.Response(status=500, text=ret)

        # unpack result, format return string to user
        try:
            cmd, method, addr, payload = ret
            pl_fmt = fmt % decode_fct(payload)
            text = '%04x/%d = %s\n' % (addr, length, pl_fmt)
        except Exception as e:
            log.error('Exception while formatting result.', exc_info=True)
            return web.Response(status=500, text='Exception while formatting result.')

        return web.Response(status=200, text=text)

    async def perform_regular_query(self):
        influx_fields = dict()

        for item in self.varlist:
            async with self.vito_lock:
                ret = await poll_msg(self.vito_proto, item.addr, item.length)
            if ret is None:
                log.info('Controller is not ready. Skipping.')
                break  # not in correct rx state, still unsynced, don't even try

            if type(ret) != tuple:
                log.error('%s [%04x/%d] error %s while talking to controller',
                          item.name, item.addr, item.length)
                continue

            msgtype, method, rx_addr, payload = ret

            try:
                v = item.decoder(payload)
            except Exception as e:
                log.error('%-12s ERR, raw=%s, exception=%s', item.name, vitotronic.hexlify(payload), e)

            log.info('%-12s ' + item.format, item.name, v)

            if item.to_influxdb:
                influx_fields[item.name] = v
        return influx_fields

    async def tick(self):
        influx_fields = dict()

        while True:
            log.info('=== Poll controller ===')
            influx_fields = await self.perform_regular_query()
            if influx_fields and self.influx_client:
                js_body = [{
                    'measurement': self.args.measurement,
                    'fields': influx_fields
                }]
                try :
                    self.influx_client.write_points(js_body, database=self.args.influxdb)
                except Exception as e :
                    log.error('Error writing to influxdb!', exc_info=True)

            await asyncio.sleep(self.args.sleep)


def main():
    import argparse

    ###
    # parse command-line arguments
    ###
    parser = argparse.ArgumentParser()
    parser.add_argument('-d', '--debug', help='Debug mode.', action='store_true')
    parser.add_argument('-q', '--quiet', help='Quiet mode, less output.', action='store_true')

    parser.add_argument('-t', '--tty', metavar='DEV', default='/dev/ttyUSB0',
                        help='Serial port, [def: /dev/ttyUSB0]', )

    parser.add_argument('-s', '--sleep', metavar='SEC', default=15, type=int,
                        help='Time to sleep between queries.')

    grp = parser.add_argument_group('InfluxDB Related')
    grp.add_argument('-i', '--influxdb', metavar='DBNAME', default=None, type=str,
                     help='Influxdb database to use [def: None, inactive]')
    grp.add_argument('-m', '--measurement', metavar='MEASNAME', default='optolink',
                     help='Influxdb measurement name to use [def: optolink]')
    grp.add_argument('-a', '--influx-server', metavar='HOST', default='127.0.0.1',
                     help='Influxdb server address [def: 127.0.0.1]')
    grp.add_argument('-p', '--influx-port', metavar='PORT', default=8086, type=int,
                     help='Influxdb server port [def: 8086]')

    grp.add_argument('-w', '--webserver', metavar='PORT', default=None, type=int,
                     help='''Run webserver to submit queries on
http://localhost:PORT/query/address/length_or_tag where length may be one
of the allowed data types (e.g. degC, uint8, ...) or number of bytes to read.
[def: off]''')

    parser.add_argument('variablelist',
                        help='''File with variables to query regularly.''')

    args = parser.parse_args()

    lvl = logging.INFO
    if args.quiet:
        lvl = logging.WARNING
    if args.debug:
        lvl = logging.DEBUG

    logging.basicConfig(level=lvl, format='%(asctime)-15s %(message)s')

    loop = asyncio.get_event_loop()

    ###
    # read list of measurements
    ###
    variablelist = viessmann_decode.load_variable_list(args.variablelist)

    ###
    # serial interface
    ###
    vito_transp, vito_proto = loop.run_until_complete(
        serial_asyncio.create_serial_connection(
            loop, vitotronic.VitoTronicProtocol, '/dev/ttyUSB0',
            baudrate=4800, bytesize=8, parity='E', stopbits=2
        )
    )

    ###
    # influxdb
    ###
    influx_client = None
    if args.influxdb:
        from influxdb import InfluxDBClient
        influx_client = InfluxDBClient(args.influx_server, args.influx_port)

    poll_mainloop = PollMainLoop(vito_proto, influx_client, variablelist, args)
    loop.create_task(poll_mainloop.tick())

    if args.webserver :
        webapp = web.Application()
        webapp.add_routes([
            web.get('/query/{addr}/{tag_or_len}', poll_mainloop.handle_web_query),
        ])

        web.run_app(webapp, port=args.webserver)  # includes loop.run_forever()
    else :
        loop.run_forever()


if __name__ == '__main__':
    main()
