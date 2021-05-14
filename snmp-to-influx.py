#!/usr/bin/python
import influxdb_client
import asyncio
import datetime
import pysnmp.hlapi
import pysnmp.hlapi.asyncio
import pysnmp.smi
import sys
import json
import argparse
from pathlib import Path


async def mainloop(cfg, args, clt):

    snmpengine = pysnmp.hlapi.SnmpEngine()
    ctx = pysnmp.hlapi.ContextData()

    mibbuilder = pysnmp.smi.builder.MibBuilder()
    mibctrl = pysnmp.smi.view.MibViewController(mibbuilder)

    name_oid_list = [
        ('temp', '1.3.6.1.4.1.22626.1.2.1.1.0'),
        ('rh', '1.3.6.1.4.1.22626.1.2.1.2.0'),
    ]

    objid_list = []
    for name, oid in name_oid_list:
        objid = pysnmp.hlapi.ObjectIdentity(oid)
        objid.resolveWithMib(mibctrl)
        objid_list.append(objid)

    while True:
        for sensorcfg in cfg:
            host = sensorcfg['host']
            community = sensorcfg.get('community', 'public')

            # mpModel=0 -> SNMPv1
            commdata = pysnmp.hlapi.CommunityData(community, mpModel=0)

            try:
                udptgt = pysnmp.hlapi.asyncio.UdpTransportTarget((host, 161))
            except Exception as exc:
                print(f'{host}: cannot get address, exception {repr(exc)}.')
                continue

            mmt_values = list()
            for (name, oid), vb in zip(name_oid_list, objid_list):
                # for whatever reason, this only works one at a time
                resp = await pysnmp.hlapi.asyncio.getCmd(
                    snmpengine,  # snmpEngine
                    commdata,  # authData
                    udptgt,  # transportTarget
                    ctx,  # contextData
                    [vb]  # varBinds
                )
                errorIndication, errorStatus, errorIndex, varBinds = resp

                if errorIndication is not None or errorStatus:
                    continue

                mmt_values.append((name, float(varBinds[0][1])))

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

    asyncio.get_event_loop().run_until_complete(mainloop(cfg, args, clt))
