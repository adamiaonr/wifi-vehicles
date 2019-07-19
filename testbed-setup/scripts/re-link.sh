#!/bin/sh

if [ $# -lt 3 ]
then
	echo "usage : $0 <os> <hostname>"
	echo "options : "
	echo "    <os> : OS used by node : 'openwrt' or 'ubuntu'"
	echo "    <type> : ap, client or server"
	echo "    <hostname> : hostname, e.g.: 'it-eeepc-maroon-001'"
	exit 1
fi

if [ "$os" == "ubuntu" ]
then

	ln -sfv $HOME/workbench/wifi-vehicles/testbed-setup/configs/$1/$3/etc/network/interfaces.client /etc/network/interfaces
	ln -sfv $HOME/workbench/wifi-vehicles/testbed-setup/configs/$1/$3/etc/wpa_supplicant/wpa_supplicant.open.conf /etc/wpa_supplicant/wpa_supplicant.conf
	ln -sfv $HOME/workbench/wifi-vehicles/testbed-setup/configs/$1/$3/etc/wpa_supplicant/wpa_supplicant.timesynch.conf /etc/wpa_supplicant/
	ln -sfv $HOME/workbench/wifi-vehicles/testbed-setup/configs/$1/$3/etc/udev/rules.d/70-persistent-net.rules /etc/udev/rules.d/70-persistent-net.rules
	ln -sfv $HOME/workbench/wifi-vehicles/testbed-setup/configs/$1/$3/usr/local/bin/* /usr/local/bin/

	cp $HOME/workbench/wifi-vehicles/testbed-setup/configs/$1/$3/etc/ntp.conf /etc/ntp.conf
	cp $HOME/workbench/wifi-vehicles/testbed-setup/configs/$1/$3/etc/rc.local /etc/rc.local
fi

if [ "$type" == "server" ]

	cp $HOME/workbench/wifi-vehicles/testbed-setup/configs/$1/$3/etc/dnsmasq.conf /etc/dnsmasq.conf
	cp $HOME/workbench/wifi-vehicles/testbed-setup/configs/$1/$3/etc/exports /etc/exports
	cp $HOME/workbench/wifi-vehicles/testbed-setup/configs/$1/$3/etc/fstab /etc/fstab	
then
