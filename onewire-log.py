#!/usr/bin/python

import influxdb_client
from pathlib import Path
import sys
import os
import os.path
import time
import datetime
import argparse


def read_sensor_list(fn):
    ret = list()
    lineno = 0

    try:
        with open(fn) as f:
            for line in f:
                lineno += 1
                line = line.strip()
                ix = line.find('#')
                if ix != -1:
                    line = line[:ix]
                if not line:
                    continue

                arr = line.split()
                if len(arr) < 2:
                    raise RuntimeError('Not enough fields in line.')

                w1_id = arr[0]
                sensor_name = arr[1]
                ret.append((w1_id, sensor_name))

    except Exception as e:
        raise RuntimeError(f'Exception raised reading {fn}:{lineno}.') from e

    return ret


parser = argparse.ArgumentParser()
parser.add_argument('sensors',
                    help='Sensor list.')
parser.add_argument('-i', '--influxdb-url', help='Influxdb host. [def: %(default)s]',
                    metavar='host', type=str, default='http://127.0.0.1:8086/')
parser.add_argument('-o', '--influxdb-org', help='Influxdb org. [def: %(default)s]',
                    metavar='org', type=str, default='vogel.cx')
parser.add_argument('-b', '--influxdb-bucket', help='Influxdb bucket. [def: %(default)s]',
                    metavar='db', type=str, default='heating/autogen')
parser.add_argument('-m', '--influxdb-measurement', help='Measurement. [def: %(default)s]',
                    metavar='txt', type=str, default='onewire')
parser.add_argument('-T', '--influxdb-token-file', help='Token file [def: %(default)s]',
                    metavar='file', type=Path)
parser.add_argument('-B', '--batchsize', help='Batch insert every N measurements. [def: %(default)d]',
                    metavar='N', type=int, default=10)
parser.add_argument('-s', '--sleep', help='Sleep N seconds between polls [def: %(default)d]',
                    metavar='SEC', type=int, default=15)
parser.add_argument('-d', '--debug', help='Be very verbose.',
                    action='store_true')

args = parser.parse_args()

sensors = read_sensor_list(args.sensors)

token = args.influxdb_token_file.open().readline().strip()
influx_client = influxdb_client.InfluxDBClient(
    url=args.influxdb_url, token=token)

datapoints = list()
poll_ctr = 0

while True:
    poll_ctr += 1
    influx_fields = dict()
    now = datetime.datetime.now(datetime.timezone.utc)
    for ow_id, sensorname in sensors:
        try:
            hwmondir = os.path.join('/sys/bus/w1/devices', ow_id, 'hwmon')
            if not os.path.isdir(hwmondir):
                continue

            hwmon_entries = [fn for fn in os.listdir(
                hwmondir) if fn.startswith('hwmon')]
            if not hwmon_entries:
                print(f'{ow_id}: no hmonX subdirs below {hwmondir}?')
                sys.stdout.flush()
                continue

            hwmonXdir = os.path.join(hwmondir, hwmon_entries[0])
            if not os.path.isdir(hwmonXdir):
                print(f'{ow_id}: {hwmonXdir} is not a directory?')
                sys.stdout.flush()
                continue

            temp_input_fn = os.path.join(hwmonXdir, 'temp1_input')
            if not os.path.isfile(temp_input_fn):
                print(f'{ow_id}: {hwmonXdir} has no temp1_input entry?')
                sys.stdout.flush()
                continue

            temp_mil_degC = int(open(temp_input_fn).read())
            if temp_mil_degC == 85000:
                print(f'{ow_id}: {sensorname} returned T=85000 mdegC: ignoring')
                sys.stdout.flush()
                continue

            if args.debug:
                print(f'{sensorname} {temp_mil_degC}')
                sys.stdout.flush()

            influx_fields[sensorname] = 0.001 * temp_mil_degC

        except Exception as e:
            e_str = str(e)
            print(f'{ow_id} {sensorname}: Exception {e_str} caught.')
            sys.stdout.flush()

    if influx_fields:
        js_body = {
            'measurement': args.influxdb_measurement,
            'time': datetime.datetime.utcnow(),
            'fields': influx_fields
        }
        datapoints.append(influxdb_client.Point.from_dict(
            js_body, influxdb_client.WritePrecision.NS))
    else:
        print(f'Not a single sensor had data???')
        sys.stdout.flush()

    if poll_ctr >= args.batchsize:
        try:
            wr_opts = influxdb_client.client.write_api.SYNCHRONOUS
            write_api = influx_client.write_api(wr_opts)
            ret = write_api.write(args.influxdb_bucket,
                                  args.influxdb_org, datapoints)
            datapoints.clear()
        except Exception as e:
            print(f'Exception occured writing points to influxdb.')
            print(e)
        poll_ctr = 0

    time.sleep(args.sleep)
