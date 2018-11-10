#!/usr/bin/python

NUL = b'x00'
NUL_i = 0
SOH = b'x01'
SOH_i = 1
STX = b'x02'
STX_i = 2
ETX = b'x03'
ETX_i = 3
EOT = b'x04'
EOT_i = 4
ENQ = b'x05'
ENQ_i = 5
ACK = b'x06'
ACK_i = 6
BEL = b'x07'
BEL_i = 7
BS = b'x08'
BS_i = 8
HT = b'x09'
HT_i = 9
LF = b'x0a'
LF_i = 10
VT = b'x0b'
VT_i = 11
FF = b'x0c'
FF_i = 12
CR = b'x0d'
CR_i = 13
SO = b'x0e'
SO_i = 14
SI = b'x0f'
SI_i = 15
DLE = b'x10'
DLE_i = 16
DC1 = b'x11'
DC1_i = 17
DC2 = b'x12'
DC2_i = 18
DC3 = b'x13'
DC3_i = 19
DC4 = b'x14'
DC4_i = 20
NAK = b'x15'
NAK_i = 21
SYN = b'x16'
SYN_i = 22
ETB = b'x17'
ETB_i = 23
CAN = b'x18'
CAN_i = 24
EM = b'x19'
EM_i = 25
SUB = b'x1a'
SUB_i = 26
ESC = b'x1b'
ESC_i = 27
FS = b'x1c'
FS_i = 28
GS = b'x1d'
GS_i = 29
RS = b'x1e'
RS_i = 30
US = b'x1f'
US_i = 31
Space = b'x20'
Space_i = 32
DEL = b'x7f'
DEL_i = 127

_ord_to_name = {
    0: 'NUL',
    1: 'SOH',
    2: 'STX',
    3: 'ETX',
    4: 'EOT',
    5: 'ENQ',
    6: 'ACK',
    7: 'BEL',
    8: 'BS',
    9: 'HT',
    10: 'LF',
    11: 'VT',
    12: 'FF',
    13: 'CR',
    14: 'SO',
    15: 'SI',
    16: 'DLE',
    17: 'DC1',
    18: 'DC2',
    19: 'DC3',
    20: 'DC4',
    21: 'NAK',
    22: 'SYN',
    23: 'ETB',
    24: 'CAN',
    25: 'EM',
    26: 'SUB',
    27: 'ESC',
    28: 'FS',
    29: 'GS',
    30: 'RS',
    31: 'US',
    32: 'Space',
    127: 'DEL',
}


def whatchar(c):
    if c in _ord_to_name:
        return '%s (%d)' % (_ord_to_name[c], c)
    return 'char #%d' % c
