# -*- coding: latin1 -*-
# Python WiFi -- a library to access wireless card properties via Python
# Copyright (C) 2004 - 2008 R�man Joost
# Copyright (C) 2008 - 2009 Sean Robinson
#
# Contributions from:
#   Mike Auty <m.auty@softhome.net> (Iwscanresult, Iwscan)
#
#    This library is free software; you can redistribute it and/or
#    modify it under the terms of the GNU Lesser General Public License
#    as published by the Free Software Foundation; either version 2.1 of
#    the License, or (at your option) any later version.
#
#    This library is distributed in the hope that it will be useful, but
#    WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
#    Lesser General Public License for more details.
#
#    You should have received a copy of the GNU Lesser General Public
#    License along with this library; if not, write to the Free Software
#    Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA 02111-1307
#    USA 

import struct
import array
import math
import errno
import fcntl
import os
import socket
import time
import re

import pythonwifi.flags
from types import StringType, IntType


KILO = 10**3
MEGA = 10**6
GIGA = 10**9


def getNICnames():
    """ Extract wireless device names of /proc/net/wireless.

        Returns empty list if no devices are present.

        >>> getNICnames()
        ['eth1', 'wifi0']

    """
    device = re.compile('[a-z]{2,4}[0-9]') 
    ifnames = []

    fp = open('/proc/net/wireless', 'r')
    data = fp.readlines()
    for line in data:
        try:
            ifnames.append(device.search(line).group())
        except AttributeError:
            pass 
    # if we couldn't lookup the devices, try to ask the kernel
    if ifnames == []:
        ifnames = getConfiguredNICnames()

    return ifnames

def getConfiguredNICnames():
    """ Get the *configured* ifnames by a systemcall.

       >>> getConfiguredNICnames()
       []

    """
    iwstruct = Iwstruct()
    ifnames = []
    buff = array.array('c', '\0'*1024)
    caddr_t, length = buff.buffer_info()
    datastr = iwstruct.pack('iP', length, caddr_t)
    try:
        result = iwstruct._fcntl(pythonwifi.flags.SIOCGIFCONF, datastr)
    except IOError, (i, error):
        return i, error

    # get the interface names out of the buffer
    for i in range(0, 1024, 32):
        ifname = buff.tostring()[i:i+32]
        ifname = struct.unpack('32s', ifname)[0]
        ifname = ifname.split('\0', 1)[0]
        if ifname:
            # verify if ifnames are really wifi devices
            wifi = Wireless(ifname)
            result = wifi.getAPaddr()
            if result[0] == 0:
                ifnames.append(ifname)

    return ifnames

def makedict(**kwargs):
    return kwargs

def hex2int(hexstring):
    """ Convert hex string to integer. """
    return int(hexstring, 16)


class Wireless(object):
    """ Access to wireless interfaces """

    def __init__(self, ifname):
        self.sockfd = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.ifname = ifname
        self.iwstruct = Iwstruct()

    def getAPaddr(self):
        """ Returns the access point MAC address.

            >>> from iwlibs import Wireless, getNICnames
            >>> ifnames = getNICnames()
            >>> ifnames
            ['eth1', 'wifi0']
            >>> wifi = Wireless(ifnames[0])
            >>> wifi.getAPaddr()
            '00:0D:88:8E:4E:93'

            Test with non-wifi card:
            >>> wifi = Wireless('eth0')
            >>> wifi.getAPaddr()
            (95, 'Operation not supported')

            Test with non-existant card:
            >>> wifi = Wireless('eth2')
            >>> wifi.getAPaddr()
            (19, 'No such device')

        """
        buff, datastr = self.iwstruct.pack_wrq(32)
        status, result = self.iwstruct.iw_get_ext(self.ifname, 
                                                  pythonwifi.flags.SIOCGIWAP,
                                                  data=datastr)
        return self.iwstruct.getMAC(result)

    def setAPaddr(self, addr):
        """ Sets the access point MAC address.

            translated from iwconfig.c

        """
        addr = addr.upper()
        if (addr == "AUTO" or addr == "ANY"):
            mac_addr = "\xFF"*pythonwifi.flags.ETH_ALEN
        elif addr == "OFF":
            mac_addr = '\x00'*pythonwifi.flags.ETH_ALEN
        else:
            if ":" not in addr: return (errno.ENOSYS, os.strerror(errno.ENOSYS))
            mac_addr = "%c%c%c%c%c%c" % tuple(map(hex2int, addr.split(':')))

        iwreq = self.iwstruct.pack("H14s", 1, mac_addr)
        status, result = self.iwstruct.iw_set_ext(self.ifname, 
                                               pythonwifi.flags.SIOCSIWAP, 
                                               iwreq)

    def getBitrate(self):
        """ Returns the device's currently set bit rate.

            >>> from iwlibs import Wireless
            >>> wifi = Wireless('eth1')
            >>> wifi.getBitrate()
            '11 Mb/s'

        """
        status, result = self.iwstruct.iw_get_ext(self.ifname, 
                                            pythonwifi.flags.SIOCGIWRATE)
        iwfreq = Iwfreq(result)
        return iwfreq.getBitrate()

    def getBitrates(self):
        """ Returns the number of bitrates available for the device.

            >>> from iwlibs import Wireless
            >>> wifi = Wireless('eth1')
            >>> num, rates = wifi.getBitrates()
            >>> num == len(rates)
            True

        """
        iwrange = Iwrange(self.ifname)
        if iwrange.errorflag:
            return (iwrange.errorflag, iwrange.error)
        return (iwrange.num_bitrates, iwrange.bitrates)

    def getChannelInfo(self):
        """ Returns the number of channels and available frequency for
           the device.

            >>> from iwlibs import Wireless
            >>> wifi = Wireless('eth1')
            >>> num, rates = wifi.getChannelInfo()
            >>> num == len(rates)
            True

        """
        iwrange = Iwrange(self.ifname)
        if iwrange.errorflag:
            return (iwrange.errorflag, iwrange.error)
        return (iwrange.num_channels, iwrange.frequencies)

    def getEssid(self):
        """ Returns the current ESSID information.

            >>> from iwlibs import Wireless
            >>> wifi = Wireless('eth1')
            >>> wifi.getEssid()
            'romanofski'

        """
        # use an IW_ESSID_MAX_SIZE-cell array of NULLs
        #   as space for ioctl to write ESSID
        iwpoint = Iwpoint('\x00'*pythonwifi.flags.IW_ESSID_MAX_SIZE)
        status, result = self.iwstruct.iw_get_ext(self.ifname, 
                                             pythonwifi.flags.SIOCGIWESSID, 
                                             data=iwpoint.getStruct())
        raw_essid = iwpoint.getData().tostring()
        return raw_essid.strip('\x00')

    def setEssid(self, essid):
        """ Sets the ESSID.

            >>> fromiwlibs import Wireless
            >>> wifi = Wireless('eth1')
            >>> wifi.getEssid()
            'romanofski'
            >>> wifi.setEssid('Joost')
            >>> wifi.getEssid()
            'Joost'

        """
        if len(essid) > pythonwifi.flags.IW_ESSID_MAX_SIZE:
            raise OverflowError(errno.EOVERFLOW, os.strerror(errno.EOVERFLOW))
        iwpoint = Iwpoint(essid, 1)
        status, result = self.iwstruct.iw_set_ext(self.ifname, 
                                             pythonwifi.flags.SIOCSIWESSID, 
                                             data=iwpoint.getStruct())

    def getEncryption(self, symbolic=True):
        """ Get the association mode, which is probably a string of '*',
            'open', 'private', 'off'.

            As a normal user, you will get an 'Operation not permitted'
            error:

            >>> from iwlibs import Wireless
            >>> wifi = Wireless('eth1')
            >>> wifi.getEncryption()
            (1, 'Operation not permitted')

        """
        # use an IW_ENCODING_TOKEN_MAX-cell array of NULLs
        #   as space for ioctl to write encryption info
        iwpoint = Iwpoint('\x00'*pythonwifi.flags.IW_ENCODING_TOKEN_MAX)
        status, result = self.iwstruct.iw_get_ext(self.ifname, 
                                             pythonwifi.flags.SIOCGIWENCODE, 
                                             data=iwpoint.getStruct())
        iwpoint.updateStruct(result)

        flags = iwpoint.getFlags()
        if not symbolic:
            return flags

        if flags & pythonwifi.flags.IW_ENCODE_NOKEY > 0:
            return '**'*iwpoint.getLength()
        elif flags & pythonwifi.flags.IW_ENCODE_OPEN > 0:
            return 'open'
        elif flags & pythonwifi.flags.IW_ENCODE_RESTRICTED > 0:
            return 'restricted'
        elif flags & pythonwifi.flags.IW_ENCODE_DISABLED > 0:
            return 'off'

    def setEncryption(self, mode):
        """ Set the association mode.

            As a normal user, you will get an 'Operation not permitted'
            error:

            >>> from iwlibs import Wireless
            >>> wifi = Wireless('eth1')
            >>> wifi.setEncryption()
            (1, 'Operation not permitted')

        """
        if type(mode) == IntType:
            mode = mode
        else:
            mode = mode.upper()
        numeric_mode = self.getEncryption(symbolic=False)
        # turn off all associate modes, but do not touch other flag bits
        numeric_mode = numeric_mode & ~pythonwifi.flags.IW_ENCODE_OPEN \
                        & ~pythonwifi.flags.IW_ENCODE_RESTRICTED \
                        & ~pythonwifi.flags.IW_ENCODE_DISABLED
        if (mode == 'OPEN') or (mode == pythonwifi.flags.IW_ENCODE_OPEN):
            numeric_mode = numeric_mode | pythonwifi.flags.IW_ENCODE_OPEN
        elif (mode == 'RESTRICTED') or (mode == pythonwifi.flags.IW_ENCODE_RESTRICTED):
            numeric_mode = numeric_mode | pythonwifi.flags.IW_ENCODE_RESTRICTED
        elif (mode == 'OFF') or (mode == pythonwifi.flags.IW_ENCODE_DISABLED):
            numeric_mode = numeric_mode | pythonwifi.flags.IW_ENCODE_DISABLED
        iwpoint = Iwpoint('\x00'*pythonwifi.flags.IW_ENCODING_TOKEN_MAX, numeric_mode)
        status, result = self.iwstruct.iw_get_ext(self.ifname, 
                                             pythonwifi.flags.SIOCSIWENCODE, 
                                             data=iwpoint.getStruct())

    def getKey(self, key=0, formatted=True):
        """ Get an encryption key.

            key 0 is current key, otherwise, retrieve specific key (1-4)

            As a normal user, you will get an 'Operation not permitted'
            error:

            >>> from iwlibs import Wireless
            >>> wifi = Wireless('eth1')
            >>> wifi.getKey()
            ABCD-9512-34

        """
        # use an IW_ENCODING_TOKEN_MAX-cell array of NULLs
        #   as space for ioctl to write encryption info
        iwpoint = Iwpoint('\x00'*pythonwifi.flags.IW_ENCODING_TOKEN_MAX, key)
        status, result = self.iwstruct.iw_get_ext(self.ifname, 
                                             pythonwifi.flags.SIOCGIWENCODE, 
                                             data=iwpoint.getStruct())
        iwpoint.updateStruct(result)

        # build a list of each char in key
        raw_key = map(ord, iwpoint.getData().tolist())[:iwpoint.getLength()]
        if sum(raw_key) == 0: raise ValueError("no key found at index")
        if not formatted: return raw_key

        # format key in standard form
        key = "%.2X" % raw_key[0]
        for i in range(1, iwpoint.getLength()):
            if ( i & 0x1 ) == 0:
                    key = key + '-'
            key = key + "%.2X" % raw_key[i]
        return key

    def setKey(self, key, index=0):
        """ Set an encryption key.

            As a normal user, you will get an 'Operation not permitted'
            error:

            >>> from iwlibs import Wireless
            >>> wifi = Wireless('eth1')
            >>> wifi.setKey()

        """
        if index not in range(1, pythonwifi.flags.IW_ENCODE_INDEX):
            raise IndexError

        if key:
            cooked_key = ''
            for i in range(0, len(key), 2):
                cooked_key = cooked_key + chr(hex2int(key[i:i+2]))
        else:
            raw_key = self.getKey(index, False)
            cooked_key = map(chr, raw_key)

        iwpoint = Iwpoint(cooked_key, 
                    index + pythonwifi.flags.IW_ENCODE_ENABLED)
        status, result = self.iwstruct.iw_get_ext(self.ifname, 
                                             pythonwifi.flags.SIOCSIWENCODE, 
                                             data=iwpoint.getStruct())
    def getKeys(self):
        """ Get all encryption keys.

            As a normal user, you will get a 'Operation not permitted'
            error:

            >>> from iwlibs import Wireless
            >>> wifi = Wireless('eth1')
            >>> wifi.getKeys()
            [(1, '1234-5678-91'), (2, None), (3, 'ABCD-EFAB-CD'), (4, None)]

        """
        iwrange = Iwrange(self.ifname);
        keys = []
        if iwrange.max_encoding_tokens > 0:
            for i in range(1, iwrange.max_encoding_tokens+1):
                try:
                    keys.append((i, self.getKey(i)))
                except ValueError, msg:
                    keys.append((i, None))
        return keys

    def getFragmentation(self):
        """ Returns the fragmentation threshold.

            It depends on what the driver says. If you have fragmentation
            threshold turned on, you'll get an int. If it's turned of
            you'll get a string: 'off'.

            >>> from iwlibs import Wireless
            >>> wifi = Wireless('eth1')
            >>> wifi.getFragmentation()
            'off'

        """
        iwparam = Iwparam(self.ifname, pythonwifi.flags.SIOCGIWFRAG)
        if iwparam.errorflag:
            return (iwparam.errorflag, iwparam.error)
        return iwparam.getValue()

    def getFrequency(self):
        """ Returns currently set frequency of the card.

            >>> from iwlibs import Wireless
            >>> wifi = Wireless('eth1')
            >>> wifi.getFrequency()
            '2.417GHz'

        """
        status, result = self.iwstruct.iw_get_ext(self.ifname, 
                                                  pythonwifi.flags.SIOCGIWFREQ)
        iwfreq = Iwfreq(result)
        freq = iwfreq.getFrequency()
        if freq < KILO:
            # This is probably a channel number
            try:
                return self.getChannelInfo()[1][freq-1]
            except IndexError:
                # probably auto (i.e. -1 (a.k.a. 255))
                return freq
        else:
            return freq

    def setFrequency(self, freq):
        """ Sets the frequency on the card.

           translated from iwconfig.c

        """
        iwstruct = Iwstruct()
        if freq == "auto":
            iwreq = iwstruct.pack("ihBB", -1, 0, 0, pythonwifi.flags.IW_FREQ_AUTO)
        else:
            if freq == "fixed":
                freq = self.getFrequency()
            freq_pattern = re.compile("([\d\.]+)(\w)", re.I|re.M|re.S)
            freq_match = freq_pattern.search(freq)
            freq_num, unit = freq_match.groups()
            if unit == "G": freq_num = float(freq_num) * GIGA
            if unit == "M": freq_num = float(freq_num) * MEGA
            if unit == "k": freq_num = float(freq_num) * KILO
            e = math.floor(math.log10(freq_num))
            if e > 8:
                m = int(math.floor(freq_num / math.pow(10, e - 6))) * 100
                e = e - 8
            else:
                m = int(math.floor(freq_num))
                e = 0
            iwreq = iwstruct.pack("ihBB", m, e, 0, pythonwifi.flags.IW_FREQ_FIXED)
        status, result = iwstruct.iw_set_ext(self.ifname, 
                                               pythonwifi.flags.SIOCSIWFREQ, 
                                               iwreq)

    def getMode(self):
        """ Returns currently set operation mode.

            >>> from iwlibs import Wireless
            >>> wifi = Wireless('eth1')
            >>> wifi.getMode()
            'Managed'

        """
        status, result = self.iwstruct.iw_get_ext(self.ifname, 
                                             pythonwifi.flags.SIOCGIWMODE)
        mode = self.iwstruct.unpack('i', result[:4])[0]
        return pythonwifi.flags.modes[mode]

    def setMode(self, mode):
        """ Sets the operation mode.

        """
        try:
            this_modes = [x.lower() for x in pythonwifi.flags.modes]
            mode = mode.lower()
            wifimode = this_modes.index(mode)
        except ValueError:
            raise ValueError("Invalid operation mode!")

        datastr = self.iwstruct.pack('I', wifimode)
        status, result = self.iwstruct.iw_set_ext(self.ifname, 
                                             pythonwifi.flags.SIOCSIWMODE, 
                                             data=datastr)

    def getWirelessName(self):
        """ Returns the wireless name.

            >>> from iwlibs import Wireless
            >>> wifi = Wireless('eth1')
            >>> wifi.getWirelessName()
            'IEEE 802.11-DS'

        """
        status, result = self.iwstruct.iw_get_ext(self.ifname, 
                                             pythonwifi.flags.SIOCGIWNAME)
        return result.tostring().strip('\x00')

    def getPowermanagement(self):
        """ Returns the power management settings 

            >>> from iwlibs import Wireless
            >>> wifi = Wireless('eth1')
            >>> wifi.getPowermanagement()
            'off'

        """
        iwparam = Iwparam(self.ifname, pythonwifi.flags.SIOCGIWPOWER)
        if iwparam.errorflag:
            return (iwparam.errorflag, iwparam.error)
        return iwparam.getValue()

    def getQualityMax(self):
        """ Returns an Iwquality object with maximum quality information.

            >>> from iwlibs import Wireless
            >>> wifi = Wireless('eth1')
            >>> mq = wifi.getQualityMax()
            >>> print "quality:", mq.quality, "signal:", mq.siglevel, "noise:", mq.nlevel
            quality: 38 signal: 13 noise: 0

        """
        iwrange = Iwrange(self.ifname)
        if iwrange.errorflag:
            return (iwrange.errorflag, iwrange.error)
        return iwrange.max_qual

    def getQualityAvg(self):
        """ Returns an Iwquality object with average quality information.

            >>> from iwlibs import Wireless
            >>> wifi = Wireless('eth1')
            >>> aq = wifi.getQualityAvg()
            >>> print "quality:", aq.quality, "signal:", aq.siglevel, "noise:", aq.nlevel
            quality: 38 signal: 13 noise: 0

        """
        iwrange = Iwrange(self.ifname)
        if iwrange.errorflag:
            return (iwrange.errorflag, iwrange.error)
        return iwrange.avg_qual

    def getRetrylimit(self):
        """ Returns the retry/lifetime limit.

            man iwconfig:
                "Most cards have MAC retransmissions, and some allow to set
                the behaviour of the retry mechanism."

            >>> from iwlibs import Wireless
            >>> wifi = Wireless('eth1')
            >>> wifi.getRetrylimit()
            16

        """
        iwparam = Iwparam(self.ifname, pythonwifi.flags.SIOCGIWRETRY)
        if iwparam.errorflag:
            return (iwparam.errorflag, iwparam.error)
        return iwparam.getValue()

    def getRTS(self):
        """ Returns the RTS threshold, likely to be int, 'auto',
            'fixed', 'off'

            man iwconfig:
                "RTS/CTS adds a handshake before each packet transmission to
                make sure that the channel is clear. This adds overhead, but
                increases performance in case of hidden nodes or a large
                number of active nodes. This parameter sets the size of the
                smallest packet for which the node sends RTS; a value equal
                to the maximum packet size disable the mechanism."

            >>> from iwlibs import Wireless
            >>> wifi = Wireless('eth1')
            >>> wifi.getRTS()
            'off'

        """
        iwparam = Iwparam(self.ifname, pythonwifi.flags.SIOCGIWRTS)
        if iwparam.errorflag:
            return (iwparam.errorflag, iwparam.error)
        return iwparam.getValue()

    def getSensitivity(self):
        """ Returns sensitivity information.

            man iwconfig:
                "This is the lowest signal level for which the hardware
                attempt packet reception, signals weaker than this are
                ignored. This is used to avoid receiving background noise,
                so you should set it according to the average noise
                level. Positive values are assumed to be the raw value used
                by the hardware or a percentage, negative values are
                assumed to be dBm."

            >>> from iwlibs import Wireless
            >>> wifi = Wireless('eth1')
            >>> wifi.getSensitivity()
            'off'

        """
        iwparam = Iwparam(self.ifname, pythonwifi.flags.SIOCGIWSENS)
        if iwparam.errorflag:
            return (iwparam.errorflag, iwparam.error)
        return iwparam.getValue()

    def getTXPower(self):
        """ Returns the transmit power in dBm.

            >>> from iwlibs import Wireless
            >>> wifi = Wireless('eth1')
            >>> wifi.getTXPower()
            '17 dBm'

        """
        status, result = self.iwstruct.iw_get_ext(self.ifname, 
                                                  pythonwifi.flags.SIOCGIWTXPOW)
        iwfreq = Iwfreq(result)
        return iwfreq.getTransmitPower()

    def getStatistics(self):
        """ Returns statistics information which can also be found in
            /proc/net/wireless.
        """
        iwstats = Iwstats(self.ifname)
        if iwstats.errorflag > 0:
            return (iwstats.errorflag, iwstats.error)
        return [iwstats.status, iwstats.qual, iwstats.discard,
            iwstats.missed_beacon]

    def scan(self):
        """ Returns Iwscanresult objects, after a successful scan."""
        iwscan = Iwscan(self.ifname)
        return iwscan.scan()

    def commit(self):
        """ Commit pending changes. """
        status, result = self.iwstruct.iw_set_ext(self.ifname, 
                                                  pythonwifi.flags.SIOCSIWCOMMIT)
        return (status, result)


class Iwstruct(object):
    """ The basic class to handle iwstruct data. """

    def __init__(self):
        self.idx = 0
        self.sockfd = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def parse_data(self, fmt, data):
        """ Unpacks raw C data. """
        size = struct.calcsize(fmt)
        idx = self.idx

        datastr = data[idx:idx + size]
        self.idx = idx+size
        value = struct.unpack(fmt, datastr)

        # take care of a tuple like (int, )
        if len(value) == 1:
            return value[0]
        else:
            return value

    def pack(self, fmt, *args):
        """ Calls struct.pack and returns the result. """
        return struct.pack(fmt, *args)

    def pack_wrq(self, buffsize):
        """ Packs wireless request data for sending it to the kernel. """
        # Prepare a buffer
        # We need the address of our buffer and the size for it. The
        # ioctl itself looks for the pointer to the address in our
        # memory and the size of it.
        # Don't change the order how the structure is packed!!!
        buff = array.array('c', '\0'*buffsize)
        caddr_t, length = buff.buffer_info()
        datastr = struct.pack('Pi', caddr_t, length)
        return buff, datastr

    def pack_test(self, string, buffsize):
        """ Packs wireless request data for sending it to the kernel. """
        buffsize = buffsize - len(string)
        buff = array.array('c', string+'\0'*buffsize)
        caddr_t, length = buff.buffer_info()
        s = struct.pack('PHH', caddr_t, length, 1)
        return buff, s

    def unpack(self, fmt, packed_data):
        """ Unpacks data with given format. """
        return struct.unpack(fmt, packed_data)

    def _fcntl(self, request, args):
        return fcntl.ioctl(self.sockfd.fileno(), request, args, True)

    def iw_get_ext(self, ifname, request, data=None):
        """ Read information from ifname. """
        buff = pythonwifi.flags.IFNAMSIZE-len(ifname)
        ifreq = array.array('c', ifname + '\0'*buff)
        # put some additional data behind the interface name
        if data is not None:
            ifreq.extend(data)
        else:
            buff = 32 # - pythonwifi.flags.IFNAMSIZE
            ifreq.extend('\0'*buff)

        result = self._fcntl(request, ifreq)
        return (result, ifreq[pythonwifi.flags.IFNAMSIZE:])

    def iw_set_ext(self, ifname, operation, data=None):
        """ Set options on ifname. """
        return self.iw_get_ext(ifname, operation, data)

    def getMAC(self, packed_data):
        """ Extracts MAC address from packed data and returns it as a str. """
        mac_addr = struct.unpack('xxBBBBBB', packed_data[:8])
        return "%02X:%02X:%02X:%02X:%02X:%02X" % mac_addr


class Iwparam(object):
    """ Class to hold iwparam data. """

    def __init__(self, ifname, ioctl):
        # (i) value, (b) fixed, (b) disabled, (b) flags
        self.fmt = "ibbH"
        self.value = 0
        self.fixed = 0
        self.disabled = 0
        self.flags = 0
        self.errorflag = 0
        self.error = ""
        self.ioctl = ioctl 
        self.ifname = ifname
        self.update()

    def getValue(self):
        """ Returns the value, if not disabled. """
        if self.disabled:
            return 'off'
        if self.flags & pythonwifi.flags.IW_RETRY_TYPE == 0:
            return self.getRLAttributes()
        else:
            return self.getPMAttributes()

    def getRLAttributes(self):
        """ Returns a string with attributes determined by self.flags."""
        return self.value

    def getPMAttributes(self):
        """ Returns a string with attributes determined by self.flags
           and IW_POWER*.

        """
        result = ""

        # Modifiers
        if self.flags & pythonwifi.flags.IW_POWER_MIN == 0:
            result = " min"
        if self.flags & pythonwifi.flags.IW_POWER_MAX == 0:
            result = " max"

        # Type
        if self.flags & pythonwifi.flags.IW_POWER_TIMEOUT == 0:
            result = " period:" 
        else:
            result = " timeout:"
        # Value with or without units
        # IW_POWER_RELATIVE - value is *not* in s/ms/us
        if self.flags & pythonwifi.flags.IW_POWER_RELATIVE:
            result += "%f" % (float(self.value)/MEGA)
        else:
            if self.value >= MEGA:
                result += "%fs" % (float(self.value)/MEGA)
            elif self.value >= KILO:
                result += "%fms" % (float(self.value)/KILO)
            else:
                result += "%dus" % self.value

        return result

    def update(self):
        """ Updates Iwstruct object by a system call to the kernel
           and updates internal attributes.

        """
        iwstruct = Iwstruct()
        i, r = iwstruct.iw_get_ext(self.ifname, 
                                   self.ioctl)
        if i > 0:
            self.errorflag = i
            self.error = r
        self._parse(r)

    def _parse(self, data):
        """ Unpacks iwparam data. """
        iwstruct = Iwstruct()
        self.value, self.fixed, self.disabled, self.flags =\
            iwstruct.parse_data(self.fmt, data)

class Iwfreq(object):
    """ Class to hold iwfreq data.
        Delegates to Iwstruct class.
    """

    def __init__(self, data=None):
        self.fmt = "ihbb"
        if data is not None:
            self.frequency = self.parse(data)
        else:
            self.frequency = 0
        self.iwstruct = Iwstruct()

    def __getattr__(self, attr):
        return getattr(self.iwstruct, attr)

    def parse(self, data):
        """ Unpacks iwparam. """
        size = struct.calcsize(self.fmt)
        m, e, dummy, pad = struct.unpack(self.fmt, data[:size])
        # XXX well, its not *the* frequency - we need a better name
        if e == 0:
            return m
        else:
            return float(m)*10**e

    def getFrequency(self):
        """ Returns Frequency (str) or channel (int) depending on driver

           data - binary data returned by systemcall (iw_get_ext())

        """
        freq = self.frequency
        if freq >= GIGA:
            return "%0.3fGHz" % (freq/GIGA)
        if freq >= MEGA:
            return "%0.3fMHZ" % (freq/MEGA)
        if freq >= KILO:
            return "%0.3fKHz" % (freq/KILO)
        return freq

    def getBitrate(self):
        """ Returns bitrate in Mbit.

           data - binary data returned by systemcall (iw_get_ext())

        """
        bitrate = self.frequency
        if bitrate >= GIGA:
            return "%i Gb/s" % (bitrate/GIGA)
        if bitrate >= MEGA:
            return "%i Mb/s" % (bitrate/MEGA)
        if bitrate >= KILO:
            return "%i Kb/s" % (bitrate/KILO)

    def getTransmitPower(self):
        """ Returns transmit power in dBm. """
        # XXX something flaky is going on with m and e
        # eg. m = 50 and e should than be 0, because the number is stored in
        # m and don't needs to be recalculated
        return "%i dBm" %self.mw2dbm(self.frequency/10)

    def getChannel(self, freq, iwrange):
        """ Returns channel information given by frequency.

           returns None if frequency can't be converted
           freq = frequency to convert (int)
           iwrange = Iwrange object

        """
        if freq < KILO:
            return None
        # XXX
        # for frequency in iwrange.frequencies

    def mw2dbm(self, mwatt):
        """ Converts mW to dBm (float). """
        return math.ceil(10.0 * math.log10(mwatt))

    def _setFrequency(self, vallist):
        """ Sets self.frequency by given list.

            Currently only used by Iwrange.

        """
        assert len(vallist) == 4
        m, e, i, pad = vallist
        if e == 0:
            self.frequency = m
        else:
            self.frequency = float(m)*10**e


class Iwstats(object):
    """ Class to hold iwstat data. """

    def __init__(self, ifname):
        # (2B) status, 4B iw_quality, 6i iw_discarded
        self.fmt = "2B4B6i"
        self.status = 0
        self.qual = Iwquality()
        self.discard = {}
        self.missed_beacon = 0
        self.ifname = ifname
        self.errorflag = 0
        self.error = ""
        self.update()

    def update(self):
        """ Updates Iwstats object by a system call to the kernel
            and updates internal attributes.

        """
        iwstruct = Iwstruct()
        buff, s = iwstruct.pack_wrq(32)
        i, result = iwstruct.iw_get_ext(self.ifname, 
                                        pythonwifi.flags.SIOCGIWSTATS, 
                                        data=s)
        if i > 0:
            self.error = result
            self.errorflag = i
        self._parse(buff.tostring())

    def _parse(self, data):
        """ Unpacks iwstruct data. """
        iwstruct = Iwstruct()
        iwqual = Iwquality()
        iwstats_data = iwstruct.parse_data(self.fmt, data)

        self.status = iwstats_data[0:2]
        self.qual.quality, self.qual.siglevel, self.qual.nlevel, \
            self.qual.updated = iwstats_data[2:6]
        nwid, code, frag, retries, iwflags = iwstats_data[6:11]
        self.missed_beacon = iwstats_data[11:12][0]
        self.discard = makedict(nwid=nwid, code=code,
            fragment=frag, retries=retries, misc=iwflags)


class Iwquality(object):
    """ Class to hold iwquality data. """

    def __init__(self):
        self.quality = 0
        self.siglevel = 0
        self.nlevel = 0
        self.updated = 0
        self.fmt = "4B"

    def parse(self, data):
        """ Unpacks iwquality data. """
        iwstruct = Iwstruct()
        qual, siglevel, nlevel, iwflags = iwstruct.parse_data(self.fmt, data)

        # compute signal and noise level
        self.siglevel = siglevel
        self.nlevel = nlevel

        # asign the other values
        self.quality = qual
        self.updated = iwflags

    def setValues(self, vallist):
        """ Assigns values given by a list to our attributes. """
        attributes = ["quality", "siglevel", "nlevel", "updated"]
        assert len(vallist) == 4

        for i in range(len(vallist)):
            setattr(self, attributes[i], vallist[i])

    def getSignallevel(self):
        """ Returns signal level. """
        return self.siglevel

    def setSignallevel(self, siglevel):
        """ Sets signal level. """
        self.siglevel = siglevel
    signallevel = property(getSignallevel, setSignallevel)

    def getNoiselevel(self):
        """ Returns noise level. """
        return self.nlevel

    def setNoiselevel(self, val):
        # currently not implemented
        # XXX
        self.nlevel = val
    noiselevel = property(getNoiselevel, setNoiselevel)


class Iwpoint(object):
    """ Class to hold iw_point data. """

    def __init__(self, data=None, flags=0):
        # P pointer to data, H length, H flags
        self.fmt = 'PHH'
        self.buff = None
        self.packed_data = None
        self.setData(data, flags)

    def setData(self, data=None, flags=0):
        """ Set the data to be referred to ioctl. """
        self._pack(data, flags)

    def getData(self):
        """ Returns the data in the buffer. """
        if self.buff:
            return self.buff

    def getStruct(self):
        """ Returns the location information for the buffer. """
        return self.packed_data

    def updateStruct(self, packed_data):
        """ Update the location information for the buffer. """
        self.packed_data = packed_data

    def getFlags(self):
        """ Returns the flags value. """
        if self.packed_data:
            caddr_t, length, flags = struct.unpack(self.fmt, self.packed_data)
            return flags
        else:
            return None

    def getLength(self):
        """ Returns the length of the buffer. """
        if self.packed_data:
            caddr_t, length, flags = struct.unpack(self.fmt, self.packed_data)
            return length
        else:
            return None

    def _pack(self, data=None, flags=0):
        """ Make a buffer with user data and a struct with its
            location in memory.

        """
        if data:
            self.buff = array.array('c', data)
            caddr_t, length = self.buff.buffer_info()
            self.packed_data = struct.pack(self.fmt, caddr_t, length, flags)


class Iwrange(object):
    """ Holds iwrange struct. """

    def __init__(self, ifname):
        self.fmt = "IIIHB6Ii4B4BB" + pythonwifi.flags.IW_MAX_BITRATES*"i" + \
                   "2i2i2i2i3H" + pythonwifi.flags.IW_MAX_ENCODING_SIZES*"H" + \
                   "2BBHB" + pythonwifi.flags.IW_MAX_TXPOWER*"i" + \
                   "2B3H2i2iHB" + pythonwifi.flags.IW_MAX_FREQUENCIES*"ihBB" + \
                   "IiiHiI"

        self.ifname = ifname
        self.errorflag = 0
        self.error = ""

        # informative stuff
        self.throughput = 0

        # nwid (or domain id)
        self.min_nwid = self.max_nwid = 0

        # frequency for backward compatibility
        self.old_num_channels = self.old_num_frequency = self.old_freq = 0

        # signal level threshold
        self.sensitivity = 0

        # link quality
        self.max_qual = Iwquality()
        self.avg_qual = Iwquality()

        # rates
        self.num_bitrates = 0
        self.bitrates = []

        # rts threshold
        self.min_rts = self.max_rts = 0

        # fragmention threshold
        self.min_frag = self.max_frag = 0

        # power managment
        self.min_pmp = self.max_pmp = 0
        self.min_pmt = self.max_pmt = 0
        self.pmp_flags = self.pmt_flags = self.pm_capa = 0

        # encoder stuff
        self.encoding_size = 0
        self.num_encoding_sizes = self.max_encoding_tokens = 0
        self.encoding_login_index = 0

        # transmit power
        self.txpower_capa = self.num_txpower = self.txpower = 0

        # wireless extension version info
        self.we_vers_compiled = self.we_vers_src = 0

        # retry limits and lifetime
        self.retry_capa = self.retry_flags = self.r_time_flags = 0
        self.min_retry = self.max_retry = 0
        self.min_r_time = self.max_r_time = 0

        # frequency
        self.num_channels = self.num_frequency = 0
        self.frequencies = []

        # capabilities and power management
        self.enc_capa = 0
        self.min_pms = self.max_pms = self.pms_flags = 0
        self.modul_capa = 0
        self.bitrate_capa = 0

        self.update()

    def update(self):
        """ Updates Iwrange object by a system call to the kernel
            and updates internal attributes.

        """
        iwstruct = Iwstruct()
        buff, s = iwstruct.pack_wrq(640)
        i, result = iwstruct.iw_get_ext(self.ifname, 
                                        pythonwifi.flags.SIOCGIWRANGE, 
                                        data=s)
        if i > 0:
            self.errorflag = i
            self.error = result
        data = buff.tostring()
        self._parse(data)

    def _parse(self, data):
        iwstruct = Iwstruct()
        result = iwstruct.parse_data(self.fmt, data)

        # XXX there is maybe a much more elegant way to do this
        self.throughput, self.min_nwid, self.max_nwid = result[0:3]
        self.old_num_channels, self.old_num_frequency = result[3:5]
        self.old_freq = result[5:11]
        self.sensitivity = result[11]
        self.max_qual.setValues(result[12:16])
        self.avg_qual.setValues(result[16:20])
        self.num_bitrates = result[20] # <- XXX
        raw_bitrates = result[21:21+self.num_bitrates]
        for rate in raw_bitrates:
            iwfreq = Iwfreq()
            iwfreq.frequency = rate
            btr = iwfreq.getBitrate()
            if btr is not None:
                self.bitrates.append(btr)

        self.min_rts, self.max_rts = result[53:55]
        self.min_frag, self.max_frag = result[55:57]
        self.min_pmp, self.max_pmp = result[57:59]
        self.min_pmt, self.max_pmt = result[59:61]
        self.pmp_flags, self.pmt_flags, self.pm_capa = result[61:64]
        self.encoding_size = result[64:72]
        self.num_encoding_sizes, self.max_encoding_tokens = result[72:74]
        self.encoding_login_index = result[74]
        self.txpower_capa, self.num_txpower = result[75:77]
        self.txpower = result[77:85]
        self.we_vers_compiled, self.we_vers_src = result[85:87]
        self.retry_capa, self.retry_flags, self.r_time_flags = result[87:90]
        self.min_retry, self.max_retry = result[90:92]
        self.min_r_time, self.max_r_time = result[92:94]
        self.num_channels = result[94]
        self.num_frequency = result[95]

        freq = result[96:224]
        i = self.num_frequency
        for x in range(0, len(freq), 4):
            iwfreq = Iwfreq()
            iwfreq._setFrequency(freq[x:x+4])
            fq = iwfreq.getFrequency()
            if fq is not None:
                self.frequencies.append(fq)
            i -= 1
            if i <= 0:
                break
        self.enc_capa = result[224]
        self.min_pms = result[225]
        self.max_pms = result[226]
        self.pms_flags = result[227]
        self.modul_capa = result[228]
        self.bitrate_capa = result[229]


class Iwscan(object):
    """ Class to handle AP scanning. """

    def __init__(self, ifname):
        self.ifname = ifname
        self.range = Iwrange(ifname)
        self.errorflag = 0
        self.error = ""
        self.stream = None
        self.aplist = None

    def scan(self, fullscan=True):
        """ Completes a scan for available access points,
            and returns them in Iwscanresult format.

           fullscan: If False, data is read from a cache of the last scan
                     If True, a scan is conducted, and then the data is read

        """
        # By default everything is fine, do not wait
        result = 1
        if fullscan:
            self.setScan()
            if self.errorflag > pythonwifi.flags.EPERM:
                errormsg = "setScan failure %s %s" % (str(self.errorflag),
                                                   str(self.error))
                raise RuntimeError(errormsg)
                return None
            elif self.errorflag < pythonwifi.flags.EPERM:
                # Permission was NOT denied, therefore we must WAIT to get results
                result = 250
        while (result > 0):
            time.sleep(result/1000)
            result = self.getScan()
        if result < 0 or self.errorflag != 0:
            raise RuntimeError, 'getScan failure ' + str(self.errorflag) + " " + str(self.error)
        return self.aplist

    def setScan(self):
        """ Triggers the scan, if we have permission. """
        iwstruct = Iwstruct()
        datastr = iwstruct.pack('Pii', 0, 0, 0)
        status, result = iwstruct.iw_set_ext(self.ifname, 
                                             pythonwifi.flags.SIOCSIWSCAN, datastr)
        if status > 0:
            self.errorflag = status
            self.error = result
        return result

    def getScan(self):
        """ Retrieves results, stored from the most recent scan.
            Returns 0 if successful, a delay if the data isn't ready yet
            or -1 if something really nasty happened.

        """
        iwstruct = Iwstruct()
        i = pythonwifi.flags.E2BIG
        bufflen = pythonwifi.flags.IW_SCAN_MAX_DATA

        # Keep resizing the buffer until it's large enough to hold the scan
        while (i == pythonwifi.flags.E2BIG):
            buff, datastr = iwstruct.pack_wrq(bufflen)
            i, result = iwstruct.iw_get_ext(self.ifname, 
                                            pythonwifi.flags.SIOCGIWSCAN,
                                            data=datastr)
            if i == pythonwifi.flags.E2BIG:
                pbuff, newlen = iwstruct.unpack('Pi', datastr)
                if bufflen < newlen:
                    bufflen = newlen
                else:
                    bufflen = bufflen * 2

        if i == pythonwifi.flags.EAGAIN:
            return 100
        if i > 0:
            self.errorflag = i
            self.error = result
            return -1

        pbuff, reslen = iwstruct.unpack('Pi', datastr)
        if reslen > 0:
            # Initialize the stream, and turn it into an enumerator
            self.aplist = self._parse(buff.tostring())
            return 0

    def _parse(self, data):
        """ Parse the event stream, and return a list of Iwscanresult
            objects.

        """
        iwstruct = Iwstruct()
        scanresult = None
        aplist = []

        # Run through the stream, until broken
        while 1:
            # If we're the stream doesn't have enough space left for a
            # header, break
            if len(data) < pythonwifi.flags.IW_EV_LCP_LEN:
                break;

            # Unpack the header
            length, cmd = iwstruct.unpack('HH', data[:4])
            # If the header says the following data is shorter than the
            # header, then break
            if length < pythonwifi.flags.IW_EV_LCP_LEN:
                break;

            # Put the events into their respective result data
            if cmd == pythonwifi.flags.SIOCGIWAP:
                if scanresult is not None:
                    aplist.append(scanresult)
                scanresult = Iwscanresult(
                    data[pythonwifi.flags.IW_EV_LCP_LEN:length], self.range)
            elif scanresult is None:
                raise RuntimeError, 'Attempting to add an event without AP data'
            else:
                scanresult.addEvent(cmd,
                                    data[pythonwifi.flags.IW_EV_LCP_LEN:length])
            # We're finished with the previous event
            data = data[length:]

        if scanresult is None:
            raise RuntimeError(
                "No scanresult. You probably don't have permissions to scan.")

        # Don't forgset the final result
        if scanresult:
            if scanresult.bssid != "00:00:00:00:00:00":
                aplist.append(scanresult)
            else:
                raise RuntimeError, 'Attempting to add an AP without a bssid'
        return aplist


class Iwscanresult(object):
    """ An object to contain all the events associated with a single scanned AP.

    """

    def __init__(self, data, iwrange):
        """ Initialize the scan result with the access point data. """
        self.iwstruct = Iwstruct()
        self.range = iwrange
        self.bssid = "%02X:%02X:%02X:%02X:%02X:%02X" % (
            struct.unpack('BBBBBB', data[2:8]))
        self.essid = None
        self.mode = None
        self.rate = []
        self.quality = Iwquality() 
        self.frequency = None
        self.encode = None
        self.custom = []
        self.protocol = None

    def addEvent(self, cmd, data):
        """ Attempts to add the data from an event to a scanresult.
            Only certain data is accepted, in which case the result is True
            If the event data is invalid, None is returned
            If the data is valid but unused, False is returned

        """
        if cmd <= pythonwifi.flags.SIOCIWLAST:
            if cmd < pythonwifi.flags.SIOCIWFIRST:
                return None
        elif cmd >= pythonwifi.flags.IWEVFIRST:
            if cmd > pythonwifi.flags.IWEVLAST:
                return None
        else:
            return None

        if cmd == pythonwifi.flags.SIOCGIWESSID:
            self.essid = data[4:]
        elif cmd == pythonwifi.flags.SIOCGIWMODE:
            self.mode = data[self.iwstruct.unpack('i', data[:4])[0]]
        elif cmd == pythonwifi.flags.SIOCGIWRATE:
            # TODO, deal with multiple rates, or at least the highest rate
            freqsize = struct.calcsize("ihbb")
            while len(data) >= freqsize:
                iwfreq = Iwfreq(data)
                self.rate.append(iwfreq.getBitrate())
                data = data[freqsize:]
        elif cmd == pythonwifi.flags.IWEVQUAL:
            self.quality.parse(data)
        elif cmd == pythonwifi.flags.SIOCGIWFREQ:
            self.frequency = Iwfreq(data)
        elif cmd == pythonwifi.flags.SIOCGIWENCODE:
            self.encode = data
        elif cmd == pythonwifi.flags.IWEVCUSTOM:
            self.custom.append(data[1:])
        elif cmd == pythonwifi.flags.SIOCGIWNAME:
            self.protocol = data[:len(data)-2]
        else:
            print "Cmd:", cmd
            return False
        return True

    def display(self):
        print "ESSID:", self.essid
        print "Access point:", self.bssid
        print "Mode:", self.mode
        if len(self.rate) > 0:
            print "Highest Bitrate:", self.rate[len(self.rate)-1]
        print "Quality: Quality ", self.quality.quality,
        print "Signal ", self.quality.getSignallevel(), 
        print " Noise ", self.quality.getNoiselevel()
        print "Encryption:", map(lambda x: hex(ord(x)), self.encode)
        # XXX
        # print "Frequency:", self.frequency.getFrequency(), "(Channel", self.frequency.getChannel(self.range), ")"
        for custom in self.custom:
            print "Custom:", custom
        print ""

