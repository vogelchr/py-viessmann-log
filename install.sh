#!/bin/sh


libdir=/usr/local/lib/py-viessmann-log
install -v -m755 -o0 -g0 -d $libdir

virtualenv $libdir/venv
$libdir/venv/bin/pip install aiohttp pyserial-asyncio influxdb-client

install -v -m644 -o0 -g0 viessmann_variables.txt $libdir
install -v -m755 -o0 -g0 py-viessmann-log.py $libdir
install -v -m644 -o0 -g0 ascii_tbl.py viessmann_decode.py vitotronic.py \
	$libdir/venv/lib/python3.9/site-packages/

if [ -d /etc/systemd/system ] ; then
	do_reload=0
	if [ -f "/etc/systemd/system/viessmann_log.service" ] ; then
		do_reload=1
		systemctl stop viessmann_log.service
	fi
	install -v -m644 -o0 -g0 viessmann_log.service /etc/systemd/system/viessmann_log.service

	if [ "$do_reload" = 1 ] ; then
		systemctl daemon-reload
	fi

	systemctl enable viessmann_log
	systemctl start viessmann_log
fi
