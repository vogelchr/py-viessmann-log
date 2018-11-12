#!/usr/bin/python

import argparse

import influxdb
import matplotlib
import numpy as np

matplotlib.use('Agg')
import matplotlib.pyplot as plt


def linspace_min_max_grow(ndarr, grow):
    x1 = np.amin(ndarr)
    x2 = np.amax(ndarr)
    w = x2 - x1
    x1 -= grow * w
    x2 += grow * w
    return np.linspace(x1, x2, 100)


def query_to_np(clt, query):
    print(f'Runing query "{query}".')
    res = clt.query(query)

    # will contain one dataframe per measurement
    measurement = sorted(res.keys())[0]
    df = res[measurement]

    ndarr = df.to_records()
    column = ndarr.dtype.names[1]

    t = ndarr['index']
    y = ndarr[column]

    return t, y


parser = argparse.ArgumentParser()
parser.add_argument('--start', metavar='TIMESTAMP', help='Start time.')
parser.add_argument('--end', metavar='TIMESTAMP', help='End time.')
parser.add_argument('-d', '--influx-db', default='heating', metavar='DB',
                    help='Influx database [heating]')
parser.add_argument('-i', '--influx-host', default='127.0.0.1', metavar='HOST',
                    help='Influx host [127.0.0.1]')
parser.add_argument('-u', '--unit', dest='unit', metavar='UNIT', default='arb',
                    help='Unit of measurement, e.g. volt, degC, ... [def: arb]')
parser.add_argument(metavar='measurement1:column1', dest='mc1')
parser.add_argument(metavar='measurement2:column2', dest='mc2')

args = parser.parse_args()

clt = influxdb.DataFrameClient(host=args.influx_host, port=8086)
clt.switch_database(args.influx_db)

m1, col1 = args.mc1.split(':')
m2, col2 = args.mc2.split(':')

query = f"SELECT {col1} FROM {m1}"
if args.start:
    query += f" WHERE time >= '{args.start}'"
if args.end:
    if args.start:
        query += f" AND time <= '{args.end}'"
    else:
        query += f" WHERE time <= '{args.end}'"

t1, val1 = query_to_np(clt, query)
t1_rel = (t1 - t1[0]).astype('f') / 1e9

t_min_str = str(np.amin(t1)) + 'Z'
t_max_str = str(np.amax(t1)) + 'Z'

t2, val2 = query_to_np(clt, f"SELECT {col2} FROM {m2} WHERE time >= '{t_min_str}' AND time <= '{t_max_str}'")
t2_rel = (t2 - t1[0]).astype('f') / 1e9

print('Minimum timestamp:', np.amin(t1), np.amin(t2))
print('Maximum timestamp:', np.amax(t1), np.amax(t2))

val2_on_t1 = np.interp(t1_rel, t2_rel, val2)
poly = np.polyfit(val1, val2_on_t1, 1)
print('Polyfit:', poly)

v1_lin = linspace_min_max_grow(val1, 0.1)
v2_fit = np.polyval(poly, v1_lin)

fig, ax = plt.subplots()
ax.set_xlabel('Time [s]')
ax.set_ylabel('Temp [degC]')
ax.plot(t1_rel, val1, label=col1)
ax.plot(t2_rel, val2, label=col2)
ax.legend()
fig.savefig('time_series.png')

fig, ax = plt.subplots()
ax.set_xlabel(f'{col1} [{args.unit}]')
ax.set_ylabel(f'{col2} [{args.unit}]')
ax.plot(val1, val2_on_t1, '*', label='Fit')
ax.plot(v1_lin, v2_fit, '-', label='Fit')
ax.legend()
fig.savefig('t_vs_t.png')


