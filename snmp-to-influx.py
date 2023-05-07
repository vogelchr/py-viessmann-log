#!/usr/bin/python
import influxdb_client
import asyncio
import datetime
import json
import argparse
import easysnmp
from pathlib import Path

async def mainloop(cfg, args, clt):
    sessions = dict()

    name_oid_list = [
        ('temp', '1.3.6.1.4.1.22626.1.2.1.1.0'),
        ('rh', '1.3.6.1.4.1.22626.1.2.1.2.0'),
    ]

    while True:
        for sensorcfg in cfg:
            host = sensorcfg['host']
            community = sensorcfg.get('community', 'public')

            try :
                if host not in sessions :
                    sessions[host] = easysnmp.Session(hostname=host, community=community, version=1)
            except Exception as exc :
                print(f'Exception {repr(exc)} trying to create snmp session to {host}!')
                continue

            mmt_values = list()
            for name, oid in name_oid_list:
                try :
                    resp = sessions[host].get(oid)
                    mmt_values.append((name, float(resp.value)))
                except Exception as exc :
                    print(f'Exception {repr(exc)} trying to get {name} from {host}!')
                    continue

            if mmt_values:
                # one measurement
                js_body = {
                    'measurement': args.influxdb_measurement,
                    'time': datetime.datetime.utcnow(),
                    'fields': dict(mmt_values),
                    'tags': {'sensor': sensorcfg.get('tag', host)}
                }
                # datapoints
                dpts = [influxdb_client.Point.from_dict(
                    js_body, influxdb_client.WritePrecision.NS)]
                try:
                    wr_opts = influxdb_client.client.write_api.SYNCHRONOUS
                    write_api = clt.write_api(wr_opts)
                    ret = write_api.write(
                        args.influxdb_bucket, args.influxdb_org, dpts)
                except Exception as exc:
                    print(f'Exception {repr(exc)} writing to influxdb!')

        await asyncio.sleep(args.sleep)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('configjson', type=Path)

    parser.add_argument('-i', '--influxdb-url', help='Influxdb host. [def: %(default)s]',
                        metavar='host', type=str, default='http://127.0.0.1:8086/')
    parser.add_argument('-o', '--influxdb-org', help='Influxdb org. [def: %(default)s]',
                        metavar='org', type=str, default='vogel.cx')
    parser.add_argument('-b', '--influxdb-bucket', help='Influxdb bucket. [def: %(default)s]',
                        metavar='db', type=str, default='heating/autogen')
    parser.add_argument('-m', '--influxdb-measurement', help='Measurement. [def: %(default)s]',
                        metavar='txt', type=str, default='indoors')
    parser.add_argument('-T', '--influxdb-token-file', help='Token file',
                        metavar='file', type=Path)
    parser.add_argument('-s', '--sleep', help='Sleep between collections [def: %(default)d]',
                        metavar='SEC', type=int, default=60)

    args = parser.parse_args()

    cfg = json.load(args.configjson.open())

    token = args.influxdb_token_file.open().readline().strip()
    clt = influxdb_client.InfluxDBClient(url=args.influxdb_url, token=token)

    event_loop = asyncio.new_event_loop()
    event_loop.run_until_complete(mainloop(cfg, args, clt))
