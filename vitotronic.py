#!/usr/bin/python

import asyncio
import binascii
import logging

from ascii_tbl import whatchar, EOT, ACK_i, NAK_i, ENQ_i

SYNC_MSG = b'\x16\0\0'


def hexlify(b):
    return binascii.hexlify(b).decode('ascii')


class PrefixLoggerAdapter(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        return '%s %s' % (self.extra['prefix'], msg), kwargs


#
# VitoTronicProtocol State Machine
#
#             +--------+
#             | Start  |
#             +--------+
#  Timeout:      | immediately
#        TO      V
#   +-------< +--------+ <----------+
#   |         | unsync |            |
#   +-------> +--------+ >--+       |
#   |    tx      | rx ENQ   | rx    | rx
#   |    EOT     V tx EOT   | NAK   | something
#   |         +---------+   |       | else
#   +-------< | startup |   | tx    | than
#   |    TO   +---------+   | SYNC  | ACK, NAK or
#   |            | rx ENQ   |       | 0x41='A'
#   |  tx SYNC   V tx SYNC  |       |
#   |    +--> +---------+ <-+       |
#   |    |    | sync    | >---------+
#   |    +--< +---------+ <>---------<> rx ACK or NAK
#   |   TO   rx  |   ^
#   |        $41 V   | last byte, emit message
#   |    TO   +---------+
#   +-------< | busy    | >----\ rx telegram byte
#             +---------+ <----/
#
#
# timeout is reset upon reception of ACK in sync state or
# reception of message in busy state, timeout is
# 30 seconds in sync state and 2 seconds in every other state

class VitoTronicProtocol(asyncio.Protocol):
    def __init__(self):
        _log = logging.getLogger(self.__class__.__name__)
        self.log = PrefixLoggerAdapter(_log, {'prefix': self.__class__.__name__})
        self.transport = None

        self.rx_state = self._rx_state_start
        self.rx_buf = bytearray()
        self.rx_timeout = 0

        self.rx_queue = list()
        self.rx_ack_ctr = 0
        self.rx_nak_ctr = 0
        self.rx_to_ctr = 0
        self.rx_err_ctr = 0
        self.rx_msg_ctr = 0

    ###
    # state handler
    ###

    def _rx_state_start(self, c):
        pass # dummy

    def _rx_state_unsync(self, c):
        if c == NAK_i:
            self.log.debug('Received NAK, sending sync sequence.')
            self.transport.write(SYNC_MSG)
            return self._rx_state_sync
        if c == ENQ_i:
            self.log.debug('Received ENQ, sending EOT.')
            self.transport.write(EOT)
            return self._rx_state_startup
        else:
            self.log.warning('Received %s while unsynced.', whatchar(c))
            self.rx_err_ctr += 1

    def _rx_state_startup(self, c):
        if c == ENQ_i:
            self.log.debug('Received ENQ, sending sync sequence.')
            self.transport.write(SYNC_MSG)
            return self._rx_state_sync
        else:
            self.log.warning('Unexpected %s in sync start.', whatchar(c))
            self.rx_err_ctr += 1
            return self._rx_state_unsync

    def _rx_state_sync(self, c):
        ###
        # not having received any message, we might receive
        # an ACK, NAK/ERROR, ENQ or start of telegram
        ###
        if c in [NAK_i, ACK_i]:
            if c == ACK_i:
                self.rx_ack_ctr += 1
            else:
                self.rx_nak_ctr += 1
            self.log.debug('Received %s.', whatchar(c))
            self.rx_timeout = 0
        elif c == 0x41:  # start of newly received packet
            self.rx_buf.clear()
            self.rx_buf.append(c)
            return self._rx_state_busy
        else:
            self.log.warning('Unexpected %s received.', whatchar(c))
            self.rx_err_ctr += 1
            return self._rx_state_unsync

    def _rx_state_busy(self, c):
        self.rx_buf.append(c)

        if len(self.rx_buf) == 0 or len(self.rx_buf) < self.rx_buf[1] + 3:
            return

        ###
        # answer for reads
        #  msg[0] = 0x41
        #  msg[1] = pktlen
        #  msg[2] = 1 (answer)
        #  msg[3] = method (read:2, functioncall: 7)
        #  msg[4] = addr MSB
        #  msg[5] = addr LSB
        #  msg[6] = len(payload)
        #  msg[7..] = payload
        #  msg[len+7] = sum(msg[1:-1]) & 0xff
        ###

        telegram_ascii = hexlify(self.rx_buf)
        chksum = sum(self.rx_buf[1:-1]) & 0xff

        if chksum != self.rx_buf[-1]:
            self.log.error('Bad checksum: %s', telegram_ascii)
            self.rx_err_ctr += 1
        elif len(self.rx_buf) != self.rx_buf[6] + 8:
            self.log.error('Bad payload length: %s', telegram_ascii)
            self.rx_err_ctr += 1
        else:

            msgtype = self.rx_buf[2]
            method = self.rx_buf[3]
            address = (self.rx_buf[4] << 8) | self.rx_buf[5]
            payload = self.rx_buf[7:-1]

            self.log.debug('Received %d/%d/0x%04x %s',
                           msgtype, method, address, hexlify(payload))
            self.rx_queue.append((msgtype, method, address, payload))

            self.rx_msg_ctr += 1

        self.rx_timeout = 0
        return self._rx_state_sync

    ###
    # callbacks from transport
    ###
    def connection_made(self, transport):
        self.log.extra['prefix'] = transport._serial.port
        self.log.info('Connection made.')
        self.transport = transport
        self.transport._loop.create_task(self.tick())
        self.transport.write(EOT)

    def connection_lost(self, exc):
        self.log.info('Connection lost.')

    def data_received(self, data):
        # upon start, we might have a lot of junk in the
        # stale RX buffer of the serial interface
        if self.rx_state == self._rx_state_start :
            self.rx_state = self._rx_state_unsync
            if len(data) > 1 :
                return

        for d in data:
            new_state = self.rx_state(d)
            if new_state:
                self.rx_state = new_state

    def eof_received(self):
        self.log.info('EOF received!')
        return False  # should close the transport

    ###
    # task to handle our timeouts
    ###
    async def tick(self):
        while True:
            await asyncio.sleep(0.5)

            if self.rx_state == self._rx_state_sync:
                if self.rx_timeout >= 60:  # 30sec
                    self.transport.write(SYNC_MSG)
                    self.rx_timeout = 0
                continue

            if self.rx_timeout >= 8: # 4 sec
                self.log.error('RX Timeout in state %s.', self.rx_state.__name__)
                self.rx_to_ctr += 1
                self.rx_state = self._rx_state_unsync
                self.transport.write(EOT)
                self.rx_timeout = 0
                continue

            self.rx_timeout += 1

    def clear_rx_queue(self):
        self.rx_ack_ctr = 0
        self.rx_nak_ctr = 0
        self.rx_err_ctr = 0
        self.rx_msg_ctr = 0
        self.rx_to_ctr = 0
        self.rx_queue.clear()

    def request_read(self, addr, exp_len):
        if self.rx_state != self._rx_state_sync:
            if self.rx_state:
                self.log.error('request_read() in state %s', self.rx_state.__name__)
            else:
                self.log.error('request_read() during startup!')
            return True

        self.log.debug('Requesting data at address 0x%04x, len %d.', addr, exp_len)
        msg = bytearray(8)
        msg[0] = 0x41
        msg[1] = 5  # length of telegram (up to, not including checksum)
        msg[2] = 0  # request
        msg[3] = 1  # read_data
        msg[4] = addr >> 8
        msg[5] = addr & 0xff
        msg[6] = exp_len
        msg[7] = sum(msg[1:-1]) & 0xff

        self.transport.write(msg)
        return False
