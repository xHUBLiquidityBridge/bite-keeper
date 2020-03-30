# This file is part of Maker Keeper Framework.
#
# Copyright (C) 2017 reverendus
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import argparse
import logging
import sys

from web3 import Web3, HTTPProvider

from pymaker import Address
from pymaker.gas import FixedGasPrice, DefaultGasPrice, IncreasingGasPrice
from pymaker.lifecycle import Lifecycle
from pymaker.sai import Tub, Vox
from pymaker.keys import register_keys
from pymaker.numeric import Wad, Ray


class BiteKeeper:
    """Keeper to bite undercollateralized cups."""

    logger = logging.getLogger('bite-all-keeper')

    def __init__(self, args: list, **kwargs):
        parser = argparse.ArgumentParser(prog='bite-keeper')
        parser.add_argument("--rpc-host", help="JSON-RPC host (default: `localhost')", default="localhost", type=str)
        parser.add_argument("--rpc-port", help="JSON-RPC port (default: `8545')", default=8545, type=int)
        parser.add_argument("--rpc-timeout", help="JSON-RPC timeout (in seconds, default: 10)", default=10, type=int)
        parser.add_argument("--eth-from", help="Ethereum account from which to send transactions", required=True, type=str)
        parser.add_argument("--eth-key", type=str, nargs='*', help="Ethereum private key(s) to use (e.g. 'key_file=/path/to/keystore.json,pass_file=/path/to/passphrase.txt')")
        parser.add_argument("--tub-address", help="Ethereum address of the Tub contract", required=True, type=str)
        parser.add_argument("--debug", help="Enable debug output", dest='debug', action='store_true')
        self.arguments = parser.parse_args(args)

        self.web3 = kwargs['web3'] if 'web3' in kwargs else Web3(HTTPProvider(endpoint_uri=f"https://{self.arguments.rpc_host}:{self.arguments.rpc_port}",
                                                                              request_kwargs={"timeout": self.arguments.rpc_timeout}))
        self.web3.eth.defaultAccount = self.arguments.eth_from
        self.our_address = Address(self.arguments.eth_from)
        register_keys(self.web3, self.arguments.eth_key)
        self.tub = Tub(web3=self.web3, address=Address(self.arguments.tub_address))
        self.vox = Vox(web3=self.web3, address=self.tub.vox())

        logging.basicConfig(format='%(asctime)-15s %(levelname)-8s %(message)s',
                            level=(logging.DEBUG if self.arguments.debug else logging.INFO))

    def main(self):
        with Lifecycle(self.web3) as lifecycle:
            lifecycle.on_block(self.check_all_cups)

    def check_all_cups(self):
        if self.tub._contract.functions.off().call():
            self.logger.info('Single Collateral Dai has been Caged')
            self.logger.info('Starting to bite all cups in the tub contract')

            # Read some things that wont change across cups
            axe = self.tub.axe() # Liquidation penalty [RAY] Fixed at 1 RAY at cage
            par = self.vox.par() # Dai Targe Price     [RAY] Typically 1 RAY
            tag = self.tub.tag() # Ref/Oracle price    [RAY] Fixed at shutdown

            for cup_id in range(self.tub.cupi()):
                self.check_cup(cup_id+1, axe, par, tag)
        else:
            self.logger.info('Single Collateral Dai live')

    def check_cup(self, cup_id, axe: Ray, par: Ray, tag: Ray):
        cup = self.tub.cups(cup_id)
        rue = Ray(self.tub.tab(cup_id)) # Amount of Debt[RAY]

        # Amount owed in SKR, including liquidation penalty
        # var owe = rdiv(rmul(rmul(rue, axe), vox.par()), tag());
        owe = ((rue * axe) * par) / tag

        # Bite cups with owe over a threshold that haven't been bitten before
        if owe > Ray.from_number(0) and cup.art != Wad.from_number(0):
            self.logger.info(f'Bite cup {cup_id} with owe of {owe} and ink of {cup.ink}')
            self.tub.bite(cup_id).transact(gas_price=self.gas_price())

    def gas_price(self):
        """ IncreasingGasPrice """
        GWEI = 1000000000

        return IncreasingGasPrice(initial_price=5*GWEI,
                                  increase_by=10*GWEI,
                                  every_secs=60,
                                  max_price=300*GWEI)


if __name__ == '__main__':
    BiteKeeper(sys.argv[1:]).main()
