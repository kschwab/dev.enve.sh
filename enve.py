#!/usr/bin/python3

# TODO: Add cowsay?
# TODO: Add exec spawn if we install/update a package at load
# TODO: Add sandbox option
# TODO: Add jsonnet banner option
# TODO: Look at switching extension/variable configs into object instead of list for explicit overriding (or, add an
# option that says to use the last extension specified)
# TODO: Clean up help

# TODO: Work on a way for developer to have own local config
# Note: pty2 lifted and modified from https://github.com/python/cpython/pull/21752/files

import os
ENVE_FLATPAK_APP_ID = 'dev.enve.sh'
ENVE_ROOT_PATH = '/usr/lib/sdk/enve'
ENVE_ETC_PATH = os.path.join(ENVE_ROOT_PATH, 'etc')
ENVE_LIB_PATH = os.path.join(ENVE_ROOT_PATH, 'lib')
ENVE_SRC_PATH = os.path.join(ENVE_ROOT_PATH, 'src')
ENVE_LIBSONNET_PATH = os.path.join(ENVE_ETC_PATH, 'enve.libsonnet')
ENVE_BASE_CONFIG_PATH = os.path.join(ENVE_ETC_PATH, 'enve.jsonnet')
ENVE_BASHRC_PATH = os.path.join(ENVE_ETC_PATH, 'enve_bashrc')
ENVE_PY_PATH = os.path.join(ENVE_SRC_PATH, 'enve.py')
ENVE_RUN_CMD_PATH = os.path.join(ENVE_SRC_PATH, 'enve_run_cmd.sh')

import site
site.addsitedir(os.path.join(ENVE_LIB_PATH, 'python3.8/site-packages'))

import re
import pty2
import collections
import click
import json
import _jsonnet
import subprocess
import logging
import configparser
import pprint
import textwrap

def add_enve_prompt_variable(enve_vars: dict, enve_options: dict) -> None:
    '''Add doc...'''

    heavy_seperator, light_seperator = ['▌','┆'] if enve_options['use-basic-prompt'] else ['', '']
    enve_prompt = r'\[\e[30;42m\]📦$ENVE_ID${ENVE_ID_VER:+ ${ENVE_ID_VER}}'

    if 'FLATPAK_ID' in os.environ and os.environ['FLATPAK_ID'] != ENVE_FLATPAK_APP_ID:
        enve_prompt += \
            r'\[\e[32;47m\]%s\[\e[30m\]$FLATPAK_ID\[\e[37;49m\]%s' % \
            (heavy_seperator, heavy_seperator)
    else:
        enve_prompt += r'\[\e[32;49m\]%s' % heavy_seperator

    enve_prompt += \
        r'\n\[\e[0;32m\]▍\[\e[0m\]\u@\h \[\e[32m\]%s\[\e[0m\] \W \[\e[32m\]%s\[\e[0m\] $ ' % \
        (light_seperator, light_seperator)

    enve_vars['ENVE_PROMPT'] = enve_prompt

def extension_verify_installed(flatpak_extension: dict) -> bool:
    '''Add doc...'''

    # Get the logger instance
    logger = logging.getLogger(__name__)

    # We have to run flatpak commands in the host environment. A return code of 0 from flatpak info indicates
    # the extension is installed.
    if subprocess.run(['flatpak-spawn', '--host', 'flatpak', 'info', flatpak_extension['flatpak']],
                      capture_output=True).returncode != 0:
        logger.warning('%s extension missing, installing...', flatpak_extension['id'])

        # The extension is missing, so attempt to install. A return code of 0 means it installed successfully.
        completed_output = subprocess.run(['flatpak-spawn', '--host', 'flatpak', 'install', '--user', '--assumeyes',
                                           flatpak_extension['remote_name'], flatpak_extension['flatpak']],
                                          capture_output=True, text=True)
        if completed_output.returncode != 0:
            # The installation of the extension failed, meaning we can't load the specified environment and will
            # have to abort.
            logger.error('%s extension install failed:\n%s', flatpak_extension['id'],
                         textwrap.indent(completed_output.stderr, '  '))
            return False

        logger.info('%s extension install succeeded.', flatpak_extension['id'])

    return True

def extension_verify_commit(flatpak_extension: dict) -> bool:
    '''Add doc...'''

    # Get the logger instance
    logger = logging.getLogger(__name__)

    # Verify the installed flatpak extension matches the commit SHA if specified.
    if flatpak_extension['commit'] != '':

        # Get the flatpak extension commit SHA
        completed_output = subprocess.run(['flatpak-spawn', '--host', 'flatpak', 'info', '--show-commit'],
                                          capture_output=True, text=True)
        # We already verified the extension is installed earlier, so expect the flatpak query to succeed.
        if completed_output.returncode != 0:
            logger.error('Unable to get info for %s:\n%s', flatpak_extension['id'],
                         textwrap.indent(completed_output.stderr, '  '))
            return False

        # If the commit SHA does not match the currently installed commit SHA, update the installed flatpak to
        # the specified commit SHA.
        if flatpak_extension['commit'] != completed_output.stdout.strip()[:len(flatpak_extension['commit'])]:
            logger.warning('%s installed commit mismatch, updating...', flatpak_extension['id'])

            # Update the installed flatpak to the specified commit SHA
            completed_output = subprocess.run(['flatpak-spawn', '--host', 'flatpak', 'update', '--commit=',
                                               flatpak_extension['commit'], flatpak_extension['flatpak']],
                                              capture_output=True, text=True)
            if completed_output.returncode != 0:
                # The update of the extension failed, meaning we can't load the specified environment and will
                # have to abort loading the environment.
                logger.error('%s extension update failed:\n%s', flatpak_extension['id'],
                             textwrap.indent(completed_output.stderr, '  '))
                return False

            logger.info('%s extension install succeeded.', flatpak_extension['id'])

    return True

def import_callback(dir_path: str, filename:str) -> [str, str]:
    '''Add doc...'''

    if filename == 'enve.libsonnet':
        with open(ENVE_LIBSONNET_PATH) as enve_libsonnet:
            return ENVE_LIBSONNET_PATH, enve_libsonnet.read()

def add_variables(enve_vars: dict, variables: list, extension_alias: str ='', extension_path: str = '') -> None:
    '''Add doc...'''

    # Get the logger instance
    logger = logging.getLogger(__name__)

    for variable in variables:
        values = variable['values']
        if variable['values_are_paths'] and extension_path:
            values = [os.path.join(extension_path, value).rstrip('/') for value in values]

        value = variable['delimiter'].join(values) if len(values) > 1 else values[0]

        variable_names = ['ENVE_PATH'] if variable['path_export'] else []
        if extension_alias:
            variable_names += ['_'.join(['ENVE', extension_alias, variable['name']]).upper()]
        else:
            variable_names += ['_'.join(['ENVE', variable['name']]).upper()]

        for variable_name in variable_names:
            if variable_name in enve_vars:
                enve_vars[variable_name] += variable['delimiter'] + value
            elif variable['delimit_first']:
                enve_vars[variable_name] = variable['delimiter'] + value
            else:
                enve_vars[variable_name] = value

def load_enve_config(enve_options: dict) -> None:
    '''Add doc...'''

    # Initialize the ENVE variables dictionary
    enve_vars = { }
    # Get the logger instance
    logger = logging.getLogger(__name__)

    # Update use-config to defaults if they exist
    if enve_options['use-config'].lower() == 'base':
        enve_options['use-config'] = ENVE_BASE_CONFIG_PATH
    elif not enve_options['use-config']:
        enve_options['use-config'] = os.environ.get('ENVE_CONFIG', '')

    # If the enve_config file is not specified via the command line or environment variable, check to see if it
    # exists in git root directory (if we're in a git repo).
    if not enve_options['use-config']:

        # Get the git root directory, where a return code of zero means we're not in a git repo.
        completed_output = subprocess.run(['git', 'rev-parse', '--show-toplevel'], capture_output=True, text=True)
        if completed_output.returncode == 0:

            # Check to see if the enve_config.jsonnet file exists in the git root directory.
            git_root_path_enve_config = os.path.join(completed_output.stdout.strip(), 'enve.jsonnet')
            if os.path.exists(git_root_path_enve_config):
                enve_options['use-config'] = git_root_path_enve_config

    # If no enve_config file was specified, prompt user on how to proceed
    if not enve_options['use-config']:
        if click.confirm('Unable to locate ENVE config. Would you like you use the base environment?', default=True):
            enve_options['use-config'] = ENVE_BASE_CONFIG_PATH
        else:
            logger.error('Unable to locate ENVE config.')
            exit(1)

    # If the ENVE config path does not exist, exit with error
    if not os.path.exists(enve_options['use-config']):
        logger.error('ENVE config path does not exist: %s', enve_options['use-config'])
        exit(1)

    # Jsonnet will validate the content for us and assert if anything is invalid.
    try:
        enve_json = json.loads(_jsonnet.evaluate_file(enve_options['use-config'], import_callback=import_callback))['Enve']
    except Exception as err:
        logger.exception('Failed to load ENVE config "%s".', enve_options['use-config'])
        exit(1)

    # Add the ENVE global variables
    add_variables(enve_vars, enve_json['variables'])

    # Add the ENVE prompt variable
    add_enve_prompt_variable(enve_vars, enve_options)

    # Ensure all the specified flatpak extensions are installed with the right commit versions if specified.
    for flatpak_extension in reversed(enve_json['extensions']):
        logger.info('Verifying Extension: %s', flatpak_extension['flatpak'])
        logger.debug('%s:\n%s', flatpak_extension['flatpak'],
                     textwrap.indent(pprint.pformat(flatpak_extension), '  '))

        # Verify the extension is installed, and attempt to install if not found
        if not extension_verify_installed(flatpak_extension):
            logger.error('ENVE load failed.')
            exit(1)

        # Verify the extension commit matches the specified, and attempt to update if SHAs mismatch
        if not extension_verify_commit(flatpak_extension):
            logger.error('ENVE load failed.')
            exit(1)

        # Add the extension load directory paths to the load directories dictionary
        add_variables(enve_vars, flatpak_extension['variables'], flatpak_extension['id_alias'],
                      flatpak_extension['path'])

    logger.debug('ENVE Variables:\n%s', textwrap.indent(pprint.pformat(enve_vars), '  '))

    # Ensure that all enve_vars are prefixed with 'ENVE_'
    bad_enve_vars = [enve_var for enve_var in enve_vars if 'ENVE_' != enve_var[:len('ENVE_')]]
    if bad_enve_vars:
        for bad_enve_var in bad_enve_vars:
            logger.error('ENVE variable not prefixed with "ENVE_": %s', bad_enve_var)
        exit(1)

    # Export the ENVE variables into the current environment
    for enve_var in enve_vars:
        os.environ[enve_var] = enve_vars[enve_var]

def load_cmd_metadata(cmd: list) -> configparser.ConfigParser:
    '''Add doc...'''

    # Get the logger instance
    logger = logging.getLogger(__name__)

    cmd_metadata = configparser.ConfigParser()

    # Metadata only exists if the command is a flatpak app
    if re.match('\w+\.\w+\.\w+', cmd[0]):
        # Attempt to get the flatpak metadata information
        completed_output = subprocess.run(['flatpak-spawn', '--host', 'flatpak', 'info', '--show-metadata', cmd[0]],
                                          capture_output=True, text=True)

        # If we're successful with getting the flatpak metadata information, then proceed with running the flatpak app
        # using flatpak-spawn.
        if completed_output.returncode == 0:
            # Get the internal command ran by the flatpak app
            cmd_metadata.read_string(completed_output.stdout)
        else:
            # Log a warning about using suspected flatpak command as regular system command and prompt user on how to
            # proceed
            logger.warning('Command "%s" suspected as flatpak app but not found.', cmd[0])
            if not click.confirm('Treat "%s" as regular system command?' % cmd[0]):
                logger.error('Invalid command "%s" received.' % cmd[0])
                exit(1)

    return cmd_metadata

def run_cmd(cmd: list, enve_options: dict) -> None:
    '''Add doc...'''

    # Get the logger instance
    logger = logging.getLogger(__name__)

    # Load the command meta data if the command is a flatpak app. If the command is not a flatpak app,
    # cmd_metadata.sections() will be [], indicating nothing was loaded or found for the supplied command.
    cmd_metadata = load_cmd_metadata(cmd)

    if cmd_metadata.sections():
        # Grab the actual flatpak app command and use it as the command to run enve.py in the spawned environment
        cmd.insert(1, cmd_metadata['Application']['command'])

        # Pass the ENVE options through to the spawned command
        for option in enve_options:
            cmd += ['--ENVE', str(option), str(enve_options[option])]

        flatpak_spawn_cmd = ['flatpak-spawn', '--host', '--watch-bus', 'flatpak', 'run',
                             '--command=%s' % ENVE_PY_PATH,
                             '--runtime=%s' % cmd_metadata['Application']['sdk'],
                             '--filesystem=host',
                             '--socket=session-bus',
                             '--allow=devel',
                             '--allow=multiarch',
                             '--share=network',
                             '--device=all',
                             '--env=TERM=%s' % os.environ['TERM']]

        logger.debug('Spawn Command:\n%s', textwrap.indent(pprint.pformat(flatpak_spawn_cmd + cmd), '  '))

        # Run the command to completion
        exit(subprocess.run(flatpak_spawn_cmd + cmd).returncode)

    elif 'ENVE_ID' in os.environ:
        # If we're not running a flatpak app, the ENVE use-config option has been specified, and we're currently in an
        # ENVE shell, then pass the command through to flatpak-spawn to ensure correct isolation of the requested
        # environment. We could do more complicated diffing between the current ENVE environment and the requested,
        # however this would require a complex diff for what should be a corner case.

        # Pass the ENVE options through to the spawned command
        for option in enve_options:
            cmd += ['--ENVE', str(option), str(enve_options[option])]

        # Note we pass the TERM environment variable here to ensure if colors are supported they show up in the new
        # shell
        flatpak_spawn_cmd = ['flatpak-spawn', '--env=TERM=%s' % os.environ['TERM'], ENVE_PY_PATH]

        logger.debug('Spawn Command:\n%s', textwrap.indent(pprint.pformat(flatpak_spawn_cmd + cmd), '  '))

        # Run the command to completion
        exit(subprocess.run(flatpak_spawn_cmd + cmd).returncode)

    else:
        # Load the ENVE config
        load_enve_config(enve_options)

    if (not enve_options['use-debug-shell']) or click.confirm('Debug shell enabled. Run command "%s"?' % ' '.join(cmd)):

        # Run the command to completion
        logger.debug('Run Command:\n%s', textwrap.indent(pprint.pformat(cmd), '  '))
        if os.path.basename(cmd[0]) in ['sh', 'bash']:
            errno = pty2.wspawn([ENVE_RUN_CMD_PATH] + cmd)
        else:
            errno = subprocess.run([ENVE_RUN_CMD_PATH] + cmd).returncode

    if enve_options['use-debug-shell']:
        errno = pty2.wspawn([ENVE_RUN_CMD_PATH, 'sh'])

    exit(errno)

def enve_options_default() -> dict:
    '''Add doc...'''

    return dict([(option, ENVE_OPTIONS[option].default) for option in ENVE_OPTIONS])

ENVE_OPTION_PARAM = collections.namedtuple('ENVE_OPTION_PARAM', ['default', 'click_type', 'help'])
ENVE_OPTIONS = {
    'use-config': ENVE_OPTION_PARAM(
        '', click.STRING,
        '''Path to the enve configuration file. If not specified, the ENVE_CONFIG environment variable will first be
        checked, followed by the "enve.jsonnet" file in the git root directory.
        ... If set, will use the ENVE base config for setting up the environment.'''
    ),

    'use-verbose': ENVE_OPTION_PARAM(
        'warning', click.Choice(['debug', 'info', 'warning']),
        '''Set the verbose level. Default is "warning".'''
    ),

    'use-debug-shell': ENVE_OPTION_PARAM(
        False, click.BOOL,
        '''Opens a debug shell in the environment after running the commands.'''
    ),

    # TODOS...
    'use-basic-prompt': ENVE_OPTION_PARAM(
        False, click.BOOL, ''
    ),

    'use-auto-switch': ENVE_OPTION_PARAM(
        False, click.BOOL, '' # We can prompt on first switch, or make a custom type
    ),

    'use-sandbox': ENVE_OPTION_PARAM(
        False, click.BOOL, ''
    )
}

@click.command(context_settings={"ignore_unknown_options": True})
@click.option('--ENVE', type=(click.Choice(ENVE_OPTIONS), str), multiple=True)
@click.argument('cmd', nargs=-1)
@click.pass_context
def cli(ctx, cmd: tuple, enve: tuple) -> None:
    '''Add doc...'''

    # Set the logging default level and format
    logging.basicConfig(level=logging.DEBUG, format='%(levelname)s: %(message)s')
    # Get the logger instance
    logger = logging.getLogger(__name__)
    # Set the default log level
    logger.setLevel(logging.WARNING)

    # Parse the ENVE options
    enve_options = enve_options_default()
    for opt, value in enve:
        try:
            enve_options[opt] = ENVE_OPTIONS[opt].click_type.convert(value, opt, ctx)
        except click.exceptions.ClickException as e:
            logger.error('--ENVE %s option %s', opt, e)
            exit(e.exit_code)

    # Update the logger verbosity level if specified
    if 'debug' == enve_options['use-verbose']:
        logger.setLevel(logging.DEBUG)
    elif 'info' == enve_options['use-verbose']:
        logger.setLevel(logging.INFO)

    # Convert the cmd tuple into a list
    cmd = list(cmd)

    # If no command is specified, start the shell by default
    if not cmd:
        cmd = ['sh']

    # Run the requested shell cmd using ENVE only if the ENVE load was successful
    run_cmd(cmd, enve_options)

if __name__ == '__main__':
    cli(prog_name=os.environ['FLATPAK_ID'])
