#!/usr/bin/python

import influxdb
import matplotlib
import numpy as np

matplotlib.use('Agg')
import matplotlib.pyplot as plt


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


clt = influxdb.DataFrameClient(host='localhost', port=8086)
clt.switch_database('heating')

t_opto, degC_opto = query_to_np(clt, 'SELECT t_supply_m2 FROM optolink')
t_opto_rel = (t_opto - t_opto[0]).astype('f') / 1e9

t_min_str = str(np.amin(t_opto)) + 'Z'
t_max_str = str(np.amax(t_opto)) + 'Z'


t_ow, degC_ow = query_to_np(clt, f"SELECT og_sup FROM heating WHERE time >= '{t_min_str}' AND time <= '{t_max_str}'")
t_ow_rel = (t_ow - t_opto[0]).astype('f') / 1e9

print('Minimum timestamp:', np.amin(t_opto), np.amin(t_ow))
print('Maximum timestamp:', np.amax(t_opto), np.amax(t_ow))

degC_ow_on_t_opto = np.interp(t_opto_rel, t_ow_rel, degC_ow)
poly = np.polyfit(degC_opto, degC_ow_on_t_opto, 1)
print('Polyfit:', poly)

degC_x_min = np.amin(degC_opto)
degC_x_max = np.amax(degC_opto)
degC_x_span = degC_x_max - degC_x_min
degC_x_min -= 0.1 * degC_x_span
degC_x_max += 0.1 * degC_x_span

degC_x_lin = np.linspace(degC_x_min, degC_x_max, 100)
degC_y_lin = np.polyval(poly, degC_x_lin)

fig, ax = plt.subplots()
ax.set_xlabel('Time [s]')
ax.set_ylabel('Temp [degC]')
ax.plot(t_opto_rel, degC_opto, label='Opto')
ax.plot(t_ow_rel, degC_ow, label='Onewire')
ax.legend()
fig.savefig('time_series.png')

fig, ax = plt.subplots()
ax.set_xlabel('Temp Optolink [degC]')
ax.set_ylabel('Temp Onewire [degC]')
ax.plot(degC_opto, degC_ow_on_t_opto, '*', label='Fit')
ax.plot(degC_x_lin, degC_y_lin, '-', label='Fit')
ax.legend()
fig.savefig('t_vs_t.png')

