from __future__ import print_function

import cStringIO
import json
import logging
import multiprocessing
import signal
import sys

import cwt

from cwt_cert import actions
from cwt_cert import node
from cwt_cert import operator
from cwt_cert import validators
from cwt_cert import exceptions

logger = logging.getLogger('cwt_cert.runner')


def default(x):
    if isinstance(x, cwt.Variable):
        data = x.parameterize()

        data['_type'] = 'variable'
    elif isinstance(x, cwt.Domain):
        data = x.parameterize()

        data['_type'] = 'domain'
    else:
        raise TypeError(type(x))

    return data


def object_hook(x):
    if '_type' in x:
        type = x.pop('_type')

        if type == 'variable':
            x = cwt.Variable.from_dict(x)
        elif type == 'domain':
            x = cwt.Domain.from_dict(x)

    return x


def json_encoder_to_file(x, fp, **kwargs):
    return json.dump(x, fp, default=default, **kwargs)


def json_encoder(x, **kwargs):
    return json.dumps(x, default=default, **kwargs)


def json_decoder(x):
    return json.loads(x, object_hook=object_hook)


class LogCapture(object):
    @property
    def value(self):
        return self.buffer.getvalue()

    def __enter__(self):
        self.buffer = cStringIO.StringIO()

        self.handler = logging.StreamHandler(self.buffer)

        self.handler.setLevel(logging.DEBUG)

        formatter = logging.Formatter(
            '%(asctime)s [[%(module)s.%(funcName)s] %(levelname)s]: '
            '%(message)s')

        self.handler.setFormatter(formatter)

        self.logger = logging.getLogger()

        self.logger.addHandler(self.handler)

        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.buffer.close()

        self.logger.removeHandler(self.handler)


def run_action(type, args=None, kwargs=None, **extra):
    assert type in actions.REGISTRY

    if args is None:
        args = []

    if kwargs is None:
        kwargs = {}

    action = actions.REGISTRY[type]

    try:
        output = action(*args, **kwargs)
    except Exception as e:
        logger.exception('Action failed')
        raise exceptions.CertificationError(str(e))

    return output


def run_validator(output, type, args=None, kwargs=None, **extra):
    assert type in validators.REGISTRY

    if args is None:
        args = []

    if kwargs is None:
        kwargs = {}

    validator = validators.REGISTRY[type]

    try:
        result = validator(output, *args, **kwargs)
    except Exception as e:
        raise exceptions.CertificationError(str(e))

    return result


def run_test(name, actions):
    with LogCapture() as capture:
        test_results = {
            'name': name,
        }

        test_result = validators.SUCCESS

        print('{:<40}'.format(name), end='\r')

        action_results = []

        for act_item in actions:
            action_result = act_item

            try:
                output = run_action(**act_item)
            except Exception as e:
                logger.exception('Action failed')

                act_item['error'] = str(e)

                act_item['result'] = validators.FAILURE

                action_results.append(action_result)

                print('{:<40}{:^40}'.format(name, act_item['result']))
                
                continue
            else:
                act_item['result'] = validators.SUCCESS

                print('{:<40}'.format(name))

            assert 'validations' in act_item

            for val_item in act_item['validations']:
                assert 'name' in val_item

                print('  {:<38}'.format(val_item['name']), end='\r')

                try:
                    result = run_validator(output, **val_item)
                except Exception as e:
                    logger.exception('Validator failed')

                    val_item['result'] = validators.FAILURE

                    val_item['error'] = str(e)
                else:
                    val_item['result'] = validators.SUCCESS

                    val_item['message'] = result

                print('  {:<38}{:^40}'.format(val_item['name'],
                                              val_item['result']))

            action_results.append(action_result)

        test_results['actions'] = action_results

        test_results['result'] = test_result

        test_results['log'] = capture.value

    return test_results


def run_test_unpack(kwargs):
    return run_test(**kwargs)


def runner(**kwargs):
    results = {'node': [], 'operator': []}

    pool = multiprocessing.Pool(5)

    node_tests = node.build_node_tests(**kwargs)

    async_result = pool.map_async(run_test_unpack, node_tests)

    results['node'] = async_result.get(120)

    operator_tests = operator.build_operator_tests(**kwargs)

    for test in operator_tests:
        test_result = pool.map(run_test_unpack, [test])

        results['operator'].append(test_result)

    pool.close()

    if kwargs['output'] is not None:
        with open(kwargs['output'], 'w') as outfile:
            json_encoder_to_file(results, outfile, indent=2)

    return results
