import logging
import re
import time
from datetime import datetime

import cwt

from cwt_cert import exceptions

logging.getLogger('urllib3').setLevel(logging.DEBUG)

logger = logging.getLogger('cwt_cert.actions')
logger.propagate = True
logger.setLevel(logging.DEBUG)

WPS_CAPABILITIES = 'wps_capabilities_action'
WPS_EXECUTE = 'wps_execute_action'


def wps_execute_action(url, identifier, inputs, api_key, domain=None,
                       parameters=None, *args, **kwargs):
    client = cwt.WPSClient(url, verify=False, api_key=api_key)

    try:
        process = [x for x in client.get_capabilities().processes if
                   re.match(identifier, x.identifier) is not None][0]
    except IndexError:
        raise exceptions.CertificationError(
            'Did not find a process matching {}'.format(identifier))

    start = datetime.now()

    client.execute(process, inputs=inputs)

    process.wait()

    elapsed = datetime.now() - start

    result = {
        'output': process.output,
        'elapsed': elapsed,
    }

    return result


def wps_capabilities_action(url, *args, **kwargs):
    client = cwt.WPSClient(url, verify=False)

    data = client.get_capabilities()

    return data


REGISTRY = {
    WPS_CAPABILITIES: wps_capabilities_action,
    WPS_EXECUTE: wps_execute_action,
}
