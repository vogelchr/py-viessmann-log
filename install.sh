#!/bin/sh

# vim: noet:ts=8:sw=8


libdir=/usr/local/lib/py-viessmann-log
install -v -m755 -o0 -g0 -d $libdir

virtualenv $libdir/venv
$libdir/venv/bin/pip install aiohttp pyserial-asyncio influxdb-client pysnmp

install -v -m644 -o0 -g0 snmp_sensors.json $libdir
install -v -m755 -o0 -g0 snmp-to-influx.py $libdir

install -v -m644 -o0 -g0 ow_temp_sensors.txt $libdir
install -v -m755 -o0 -g0 onewire-log.py $libdir

install -v -m644 -o0 -g0 viessmann_variables.txt $libdir
install -v -m755 -o0 -g0 py-viessmann-log.py $libdir
install -v -m644 -o0 -g0 ascii_tbl.py viessmann_decode.py vitotronic.py \
	$libdir/venv/lib/python3.9/site-packages/

if [ -d /etc/systemd/system ] ; then
	do_reload=0
	if [ -f "/etc/systemd/system/viessmann_log.service" ] ; then
		do_reload=1
		systemctl stop viessmann_log
		systemctl stop snmp_to_influx
		systemctl stop onewire_log
	fi

	install -v -m644 -o0 -g0 snmp_to_influx.service /etc/systemd/system/snmp_to_influx.service
	install -v -m644 -o0 -g0 viessmann_log.service /etc/systemd/system/viessmann_log.service
	install -v -m644 -o0 -g0 onewire_log.service /etc/systemd/system/onewire_log.service

	if [ "$do_reload" = 1 ] ; then
		systemctl daemon-reload
	fi

	systemctl enable viessmann_log
	systemctl start viessmann_log

	systemctl enable onewire_log
	systemctl start onewire_log

	systemctl enable snmp_to_influx
	systemctl start snmp_to_influx
fi
