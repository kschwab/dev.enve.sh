#!/usr/bin/python3

import os
ENVE_ROOT_PATH = '/usr/lib/sdk/enve'
ENVE_ETC_PATH = os.path.join(ENVE_ROOT_PATH, 'etc')
ENVE_BIN_PATH = os.path.join(ENVE_ROOT_PATH, 'bin')
ENVE_LIB_PATH = os.path.join(ENVE_ROOT_PATH, 'lib')
ENVE_LIBSONNET_PATH = os.path.join(ENVE_ETC_PATH, 'enve.libsonnet')
ENVE_BASE_CONFIG_PATH = os.path.join(ENVE_ETC_PATH, 'enve.jsonnet')
ENVE_RUN_PATH = os.path.join(ENVE_LIB_PATH, 'enve_run')
ENVE_RUN_DBG_PATH = os.path.join(ENVE_LIB_PATH, 'enve_run_dbg')

import site
site.addsitedir(os.path.join(ENVE_LIB_PATH, 'python3.8/site-packages'))

import re
import collections
import click
import json
import _jsonnet
import subprocess
import logging
import configparser
import pprint
import textwrap

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
        completed_output = subprocess.run(['flatpak-spawn', '--host', 'flatpak', 'install', '--user',
                                           flatpak_extension['flatpak']], capture_output=True, text=True)
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
            values = [os.path.join(extension_path, value) for value in values]

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

def load_environ_config(enve_config: str) -> [int, dict]:
    '''Add doc...'''

    # Initialize the ENVE variables dictionary
    enve_vars = { }
    # Get the logger instance
    logger = logging.getLogger(__name__)

    # If the enve_config file is not specified via the command line or environment variable, check to see if it
    # exists in git root directory (if we're in a git repo).
    if not enve_config:

        # Get the git root directory, where a return code of zero means we're not in a git repo.
        completed_output = subprocess.run(['git', 'rev-parse', '--show-toplevel'], capture_output=True, text=True)
        if completed_output.returncode == 0:

            # Check to see if the enve_config.jsonnet file exists in the git root directory.
            git_root_path_enve_config = os.path.join(completed_output.stdout.strip(), 'enve.jsonnet')
            if os.path.exists(git_root_path_enve_config):
                enve_config = git_root_path_enve_config

    # If no enve_config file was specified, prompt user on how to proceed
    if not enve_config:
        if click.confirm('Unable to locate ENVE config. Would you like you use the base environment?', default=True):
            enve_config = ENVE_BASE_CONFIG_PATH
        else:
            logger.error('Unable to locate ENVE config.')
            return 1, enve_vars

    # Jsonnet will validate the content for us and assert if anything is invalid.
    try:
        enve_json = json.loads(_jsonnet.evaluate_file(enve_config, import_callback=import_callback))['Enve']
    except Exception as err:
        logger.exception('Failed to load ENVE config "%s".', enve_config)
        return 1, enve_vars

    add_variables(enve_vars, enve_json['variables'])

    # Ensure all the specified flatpak extensions are installed with the right commit versions if specified.
    for flatpak_extension in reversed(enve_json['extensions']):
        logger.info('Verifying Extension: %s', flatpak_extension['flatpak'])
        logger.debug('%s:\n%s', flatpak_extension['flatpak'],
                     textwrap.indent(pprint.pformat(flatpak_extension), '  '))

        # Verify the extension is installed, and attempt to install if not found
        if not extension_verify_installed(flatpak_extension):
            logger.error('ENVE load failed.')
            return 1, enve_vars

        # Verify the extension commit matches the specified, and attempt to update if SHAs mismatch
        if not extension_verify_commit(flatpak_extension):
            logger.error('ENVE load failed.')
            return 1, enve_vars

        # Add the extension load directory paths to the load directories dictionary
        add_variables(enve_vars, flatpak_extension['variables'], flatpak_extension['id_alias'],
                      flatpak_extension['path'])

    logger.debug('ENVE Variables:\n%s', textwrap.indent(pprint.pformat(enve_vars), '  '))

    return 0, enve_vars

def run_cmd(cmd: list, enve_vars: dict, enve_use_debug_shell: bool, enve_enable_detached: bool) -> int:
    '''Add doc...'''

    # Get the logger instance
    logger = logging.getLogger(__name__)

    # First check to see if the command is a flatpak app
    if re.match('\w+\.\w+\.\w+', cmd[0]):
        # Attempt to get the flatpak metadata information
        completed_output = subprocess.run(['flatpak-spawn', '--host', 'flatpak', 'info', '--show-metadata', cmd[0]],
                                          capture_output=True, text=True)

        # If we're successful with getting the flatpak metadata information, then proceed with running the flatpak app
        # using flatpak-spawn.
        if completed_output.returncode == 0:

            # Get the internal command ran by the flatpak app
            config = configparser.ConfigParser()
            config.read_string(completed_output.stdout)
            cmd.insert(1, config['Application']['command'])

            flatpak_spawn_cmd = ['flatpak-spawn', '--host', 'flatpak', 'run',
                                 '--command=%s' % (ENVE_RUN_DBG_PATH if enve_use_debug_shell else ENVE_RUN_PATH),
                                 '--runtime=org.freedesktop.Sdk',
                                 '--filesystem=host',
                                 "--filesystem=/tmp",
                                 '--socket=session-bus',
                                 '--allow=devel',
                                 '--allow=multiarch',
                                 '--share=network',
                                 '--device=all'] + \
                                 ['--env=%s=%s' % (enve_var, enve_vars[enve_var]) for enve_var in enve_vars]

            flatpak_spawn_cmd += ['--parent-pid=%d' % os.getpid(), '--die-with-parent'] if not enve_enable_detached else []

            logger.debug('Exec Command:\n%s', textwrap.indent(pprint.pformat(flatpak_spawn_cmd + cmd), '  '))

            # Run the app using flatpak-spawn under the host system
            if enve_enable_detached:
                if enve_use_debug_shell:
                    logger.warning('Cannot run detached when debug shell is enabled. Disabling flatpak app detachment.')
                else:
                    # When running detached we have to use the subprocess.Popen method in order to gain access to the
                    # start_new_session flag
                    subprocess.Popen(flatpak_spawn_cmd + cmd, start_new_session=True)
                    return 0

            # Run the command to completion
            return subprocess.run(flatpak_spawn_cmd + cmd).returncode
        else:
            # Log a warning about using suspected flatpak command as regular system command
            logger.warning('Command "%s" suspected as flatpak app but not found.', cmd[0])
            logger.warning('Treating "%s" as regular system command.', cmd[0]) # PROMPT HERE??

    # The command does not appear to be a flatpak app, so we'll just run the command here locally without spawning a new
    # flatpak session.

    # Export the ENVE variables into the current environment
    for enve_var in enve_vars:
        os.environ[enve_var] = enve_vars[enve_var]

    # Update the cmd to use the enve_run script for running
    cmd.insert(0, ENVE_RUN_DBG_PATH if enve_use_debug_shell else ENVE_RUN_PATH)

    # Run the command to copmletion
    logger.debug('Exec Command:\n%s', textwrap.indent(pprint.pformat(cmd), '  '))
    return subprocess.run(cmd).returncode

ENVE_OPTION_PARAM = collections.namedtuple('ENVE_OPTION_PARAM', ['default', 'type'])

# TODO: Add sandbox option
ENVE_OPTIONS = {
    'use-config': ENVE_OPTION_PARAM('', click.STRING),
    'use-verbose': ENVE_OPTION_PARAM('warning', click.Choice(['debug', 'info', 'warning'])),
    'use-detached': ENVE_OPTION_PARAM(False, click.BOOL),
    'use-debug-shell': ENVE_OPTION_PARAM(False, click.BOOL),
}
# TODO: Clean up help
# @click.option('--enve-use-config', envvar='ENVE_CONFIG', type=click.Path(exists=True),
#               help='''Path to the enve configuration file. If not specified, the ENVE_CONFIG environment
#               variable will first be checked, followed by the "enve.jsonnet" file in the git root directory.''')
# @click.option('--enve-use-base-config', is_flag=True,
#               help='''If set, will use the ENVE base config for setting up the environment.''')
# @click.option('--enve-use-debug-shell', is_flag=True,
#               help='''Opens a debug shell in the environment before running the commands.''')
# @click.option('--enve-use-verbose', type=click.Choice(['warning', 'info', 'debug']), default='warning',
#               help='Set the verbose level. Default is "warning".')
# @click.option('--enve-enable-detached/--enve-disable-detached', is_flag=True,
#               help='''Enable/disable a flatpak app from running detached. Note, the detached flatpak app will still
#               retain ENVE sandbox configuration. The "detachment" is only accomplished from a system process point
#               of view. Default is disabled.''')

def enve_options_default() -> dict:
    return dict([(option, ENVE_OPTIONS[option].default) for option in ENVE_OPTIONS])

@click.command(context_settings={"ignore_unknown_options": True})
@click.option('--ENVE', type=(click.Choice(ENVE_OPTIONS), str), multiple=True)
@click.argument('shell_cmd', nargs=-1)
@click.pass_context
def cli(ctx, shell_cmd: tuple, enve: tuple) -> None:
    '''Add doc...'''

    enve_options = enve_options_default()
    for opt, value in enve:
        try:
            enve_options[opt] = ENVE_OPTIONS[opt].type.convert(value, opt, ctx)
        except click.exceptions.ClickException as e:
            print('Error: --ENVE', opt, 'option', e)
            exit(e.exit_code)

    if enve_options['use-config'].lower() == 'base':
        enve_options['use-config'] = ENVE_BASE_CONFIG_PATH
    elif enve_options['use-config']:
        try:
            click.Path(exists=True).convert(enve_options['use-config'], 'use-config', ctx)
        except click.exceptions.ClickException as e:
            print('Error: --ENVE', opt, 'option', e)
            exit(e.exit_code)

    # Set the logging default level and format
    logging.basicConfig(level=logging.DEBUG, format='%(levelname)s: %(message)s')

    # Get the logger instance
    logger = logging.getLogger(__name__)
    # Set the default log level
    logger.setLevel(logging.WARNING)
    # Update the logger verbosity level if specified
    if 'debug' == enve_options['use-verbose']:
        logger.setLevel(logging.DEBUG)
        logger.info('Debug log level set.')
    elif 'info' == enve_options['use-verbose']:
        logger.setLevel(logging.INFO)
        logger.info('Info log level set.')

    # Parse the environment configs
    errno, enve_vars = load_environ_config(enve_options['use-config'])

    # If no command is specified, start the shell by default
    if not shell_cmd:
        shell_cmd = ('sh',)

    # Run the requested shell cmd using ENVE only if the ENVE load was successful
    if errno == 0:
        errno = run_cmd(list(shell_cmd), enve_vars, enve_options['use-debug-shell'], enve_options['use-detached'])

    # Exit with error code
    exit(errno)

if __name__ == '__main__':
    cli(prog_name=os.environ['FLATPAK_ID'])


# TODO: We can skip doing work if already in the shell and the command is not a flatpak app... just simply pass it through or eval it...
