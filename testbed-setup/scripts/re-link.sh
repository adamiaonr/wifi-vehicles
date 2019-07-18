#!/bin/sh

if [ $# -lt 2 ]
then
	echo "usage : $0 <os> <hostname>"
	echo "options : "
	echo "    <os> : OS used by node : 'openwrt' or 'ubuntu'"
	echo "    <hostname> : hostname, e.g.: 'it-eeepc-maroon-001'"
	exit 1
fi

ln -sfv $HOME/workbench/wifi-vehicles/testbed-setup/configs/$1/$2/etc/network/interfaces.client /etc/network/interfaces
ln -sfv $HOME/workbench/wifi-vehicles/testbed-setup/configs/$1/$2/etc/wpa_supplicant/wpa_supplicant.open.conf /etc/wpa_supplicant/wpa_supplicant.conf
ln -sfv $HOME/workbench/wifi-vehicles/testbed-setup/configs/$1/$2/etc/wpa_supplicant/wpa_supplicant.timesynch.conf /etc/wpa_supplicant/
ln -sfv $HOME/workbench/wifi-vehicles/testbed-setup/configs/$1/$2/etc/udev/rules.d/70-persistent-net.rules /etc/udev/rules.d/70-persistent-net.rules

ln -sfv $HOME/workbench/wifi-vehicles/testbed-setup/configs/$1/$2/usr/local/bin/* /usr/local/bin/

cp $HOME/workbench/wifi-vehicles/testbed-setup/configs/$1/$2/etc/ntp.conf /etc/ntp.conf