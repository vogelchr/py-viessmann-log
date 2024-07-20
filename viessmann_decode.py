#!/usr/bin/python
import binascii
import logging
import struct
import time
from collections import namedtuple

log = logging.getLogger('viessmann_decode')


def bcd(v):
    hi_nibble = (v & 0xf0) >> 4
    lo_nibble = v & 0x0f
    return 10 * hi_nibble + lo_nibble


def decode_systime_to_tuple(payload):
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


def decode_systime_to_str(payload):
    v = decode_systime_to_tuple(payload)
    return time.strftime('%A, %Y-%m-%d %H:%M:%S', v)


datatypes = {
    # generic
    'uint8': [('B', None), '%3u'],  # 8bit unsigned int
    'uint16': [('<H', None), '%5u'],  # 16bit unsigned int
    'uint32': [('<L', None), '%9u'],  # 32bit unsigned int
    # very special
    'systime': [(decode_systime_to_str, 8), '%-26s'],  # current time
    'degC': [('<h', 0.1), '%+6.1f °C'],  # deg Celsius
    'uint8h': [('B', 0.5), '%5.1f'],  # 8bit unsigned int / 2.0
}

VariableListItem = namedtuple('VariableListItem',
                              ['name', 'to_influxdb', 'addr', 'length', 'decoder', 'format'])


def yes_no_to_bool(s):
    s = s.strip().lower()
    if s == 'yes' or s == 'true' or s in 'ty1x✓🗸':
        return True
    if s == 'no' or s == 'false' or s in 'fn0-':
        return False
    raise RuntimeError('Cannot parse \'%s\' as yes/no/true/false.' % s)


def gen_decoder(tag_or_length):
    decode_info = datatypes.get(tag_or_length)

    if decode_info is None:
        # if it's not a predefined type, assume it's a integer
        # corresponding to the number of bytes to read, and we
        # just return a hex presentation
        length = int(tag_or_length, 0)
        def fct_or_struct(v): return binascii.hexlify(v).decode('ascii')
        len_or_factor = length
        fmt = f'%{2*length}s'
    else:
        (fct_or_struct, len_or_factor), fmt = decode_info

    # if first item in fct_or_struct is a string, we assume it's
    # to decode a struct, and the 2nd parameter is either None or
    # a factor to multiply (e.g. 0.1 for tenths-degrees-celsius)
    if type(fct_or_struct) == str:
        def _makefct(fmt, factor):
            def _fct(payload):
                v, = struct.unpack(fmt, payload)
                if factor is not None:
                    return factor * v
                return v

            return _fct

        decode_fct = _makefct(fct_or_struct, len_or_factor)
        length = struct.calcsize(fct_or_struct)
    else:
        decode_fct = fct_or_struct
        length = len_or_factor

    return length, decode_fct, fmt


def load_variable_list(fn):
    ret = list()

    with open(fn, 'rt') as f:
        for lno, line in enumerate(f, 1):
            ix = line.find('#')
            if ix != -1:
                line = line[:ix]
            line = line.strip()

            if not line:
                continue

            arr = line.strip().split()
            if len(arr) < 4:
                raise RuntimeError(
                    '%s:%d not enough columns, need at least 4' % (fn, lno))

            ###
            # parse columns
            ###
            var_name = arr[0]
            to_influxdb = yes_no_to_bool(arr[1])
            addr = int(arr[2], 0)
            tag_or_len = arr[3]

            length, decode_fct, fmt = gen_decoder(tag_or_len)

            it = VariableListItem(
                var_name, to_influxdb, addr, length, decode_fct, fmt)
            ret.append(it)

    return ret


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG,
                        format='%(asctime)-15s %(message)s')

    data = [
        '20c8057200000019',
        '2018111107131316',
        '6d00',
        '6c00',
        '5100',
        '5100',
        '80',
    ]

    l = load_variable_list('viessmann_variables.txt')

    for k, it in enumerate(l):
        if k < len(data):
            p = binascii.unhexlify(data[k])
            v = it.decoder(p)
            print(it.name, it.length, data[k], '-->', it.format % v)
        else:
            print(it.name, it.length, it.format)
