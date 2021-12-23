#!/usr/bin/env python3

"""
This module consists of utilities which can be used.
"""

import datetime
import json
import os
import subprocess
import time

START_TIME = None


def date(ti_me):
    """
    Returns the duration.

    :param ti_me: time.
    """
    return str(datetime.datetime.now() - ti_me)


# pylint: disable=R1710
def str2bool(string: str) -> bool:
    """
    Converts a string to a boolean

    Args:
        string: string to convert

    Returns:
        boolean
    """
    if not isinstance(string, str):
        return string

    if string.lower() in ('yes', 'true', 't', 'y', '1'):
        return True

    if string.lower() in ('no', 'false', 'f', 'n', '0'):
        return False


def log(*message):
    """
    Adds time and date to the 'message' in a correct format.

    :param *message: message to be added in the log.
    """
    now = datetime.datetime.now()
    val = (now.date().isoformat() +
           ' ' + now.time().isoformat() +
           ': ' + str(*message))
    print(val)
    write_to_logfile(val)


def execute_command(command, log_command=True):
    """
    Executes commands.

    :param command: Commands to be executed
    :param log_command: If True will print the command executed
    """
    if log_command:
        log('Executing: ' + '"' + command + '"')
    try:
        output = subprocess.check_output(
            command.split(' '),
            stderr=subprocess.STDOUT).decode('UTF-8')
        print(output)
        return output
    except subprocess.CalledProcessError as error:
        print(error.output.decode('UTF-8'))
        if log_command is False:
            command = ""
        raise ValueError('There was an error while trying to execute the '
                         'command "{}"'.format(command)) from error


def write_to_logfile(val):
    """
    Writes to the log file.

    :param val: The string to be written to the log file.
    """
    file_p = open("/var/log/testdeploy.log", "a")
    file_p.write(val + '\n')
    file_p.close()


def get_options(key, custom_values=None):
    """
    Get options from environment variable 'options'

    :param key: (String) key to retrieve from the options dictionary.
    :param custom_values: (Dict) values that are used to templatizing\
         the options.
    :return: String with all the options requested
    """
    env_options = os.environ.get('options')

    if env_options is None:
        log("No ENV VAR option named 'options'. Return empty string")
        return ''

    options = json.loads(env_options)

    options_found = ''
    if options.get(key) is not None:
        options_found += " {}".format(options[key])

    if custom_values is None:
        return options_found

    formatted_options = ''
    try:
        formatted_options = options_found.format(**custom_values)
    except Exception as e_obj:
        log("Error while templating options: {}".format(e_obj))

    return formatted_options


def record_time(start=False):
    """
    This function acts as a timer to record the time passed between a start
    and end point. Firstly call record_time(True) to start the timer. Then
    perform any actions you wish to be timed. Call record_time() again but
    without arguments to retrieve the time elapsed since the timer started.

    :param start: set the global START_TIME to the current time
    :return time_elapsed: if start is False returns time passed since
    the START_TIME in seconds
    """
    global START_TIME
    if start:
        START_TIME = time.time()
    time_elapsed = time.time() - START_TIME
    return round(time_elapsed)


def generate_test_pod_prefix(script_path, script_name):
    """
    Generate prefix for test pod from environment variables (nose_test,
    test_cases_dir)

    :param script_path: (String) path to test cases directory
    :param script_name: (String) path to the Nose Python test file
    :return: pod prefix
    """
    script_path = script_path.replace("_", "-")
    if script_name == 'None':
        pod_name = script_path
    else:
        pod_name = script_path + '-' + os.path.splitext(script_name)[0]. \
            replace("_", "-")
    return pod_name
