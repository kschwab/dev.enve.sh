#!/usr/bin/python3

import os
import re
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
    if flatpak_extension['commit'] != None:

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

def extension_add_paths(flatpak_extension: dict, load_directories: list, enve_vars: dict) -> None:
    '''Add doc...'''

    # Get the logger instance
    logger = logging.getLogger(__name__)

    # For each directory in the load directories, check to see if the path exists for the Project extension
    for directory in load_directories:

        # If the path exists for the Project extension, add the path to the dictionary to later be exported into the
        # environment
        flatpak_extension_path = os.path.join(flatpak_extension['path'], directory)
        if os.path.exists(flatpak_extension_path):

            # Add to project specific path environment variable
            flatpak_extension_path_enve_var = '_'.join(
                ['ENVE', flatpak_extension['enve_alias'], directory, 'PATH']).upper()
            if flatpak_extension_path_enve_var in enve_vars:
                enve_vars[flatpak_extension_path_enve_var].insert(0, flatpak_extension_path)
            else:
                enve_vars[flatpak_extension_path_enve_var] = [flatpak_extension_path]

            # Add to project cumulative path environment variable
            project_path_enve_var = '_'.join(['ENVE', directory, 'PATH']).upper()
            if project_path_enve_var in enve_vars:
                enve_vars[project_path_enve_var].insert(0, flatpak_extension_path)
            else:
                enve_vars[project_path_enve_var] = [flatpak_extension_path]

    logger.debug('Project Environment Variables:\n%s', textwrap.indent(pprint.pformat(enve_vars), '  '))

def load_environ_config(enve_config: str) -> [int, dict]:
    '''Add doc...'''

    # Initialize the project environment dictionary
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
        if click.confirm('Unable to locate Project config. Would you like you use the base environment?', default=True):
            return 0, enve_vars
        else:
            logger.error('Unable to locate Project config.')
            return 1, enve_vars

    # Jsonnet will validate the content for us and assert if anything is invalid.
    enve_json = json.loads(_jsonnet.evaluate_file(enve_config))['Enve']
    load_directories = enve_json['Flatpak']['Constant']['EXTENSION_LOAD_DIRECTORIES']

    # Ensure all the specified project flatpak extensions are installed with the right commit versions if
    # specified.
    for flatpak_extension in enve_json['Flatpak']['Extensions']:
        logger.info('Verifying Extension: %s', flatpak_extension['flatpak'])
        logger.debug('%s:\n%s', flatpak_extension['flatpak'],
                     textwrap.indent(pprint.pformat(flatpak_extension), '  '))

        # Verify the extension is installed, and attempt to install if not found
        if not extension_verify_installed(flatpak_extension):
            logger.error('Project environment load failed.')
            return 1, enve_vars

        # Verify the extension commit matches the specified, and attempt to update if SHAs mismatch
        if not extension_verify_commit(flatpak_extension):
            logger.error('Project environment load failed.')
            return 1, enve_vars

        # Add the extension load directory paths to the load directories dictionary
        extension_add_paths(flatpak_extension, load_directories, enve_vars)

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
                                 '--command=/usr/lib/sdk/enve/enve_run%s' % ('_dbg' if enve_use_debug_shell else ''),
                                 '--runtime=org.freedesktop.Sdk',
                                 '--filesystem=host',
                                 "--filesystem=/tmp",
                                 '--socket=session-bus',
                                 '--allow=devel',
                                 '--allow=multiarch',
                                 '--share=network',
                                 '--device=all'] + \
                                 ['--env=%s=%s' % (enve_var, ':'.join(enve_vars[enve_var])) for enve_var in enve_vars]
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
            logger.warning('Treating "%s" as regular system command.', cmd[0])

    # The command does not appear to be a flatpak app, so we'll just run the command here locally without spawning a new
    # flatpak session.

    # Export the project environment variables into the current environment
    for enve_var in enve_vars:
        os.environ[enve_var] = ':'.join(enve_vars[enve_var])

    # Update the cmd to use the enve_run script for running
    if enve_use_debug_shell:
        cmd.insert(0, '/usr/lib/sdk/enve/enve_run_dbg')
    else:
        cmd.insert(0, '/usr/lib/sdk/enve/enve_run')

    # Run the command to copmletion
    logger.debug('Exec Command:\n%s', textwrap.indent(pprint.pformat(cmd), '  '))
    return subprocess.run(cmd).returncode

@click.command(context_settings={"ignore_unknown_options": True})
@click.option('--enve-config', envvar='ENVE_CONFIG', type=click.Path(exists=True),
              help='''Path to the enve configuration file. If not specified, the ENVE_CONFIG environment
              variable will first be checked, followed by the "enve.jsonnet" file in the git root directory.''')
@click.option('--enve-use-base-config', is_flag=True,
              help='''If set, will use the ENVE base config for setting up the environment.''')
@click.option('--enve-use-debug-shell', is_flag=True,
              help='''Opens a debug shell in the environment before running the commands.''')
@click.option('--enve-use-verbose', type=click.Choice(['warning', 'info', 'debug']), default='warning',
              help='Set the verbose level. Default is "warning".')
@click.option('--enve-enable-detached/--enve-disable-detached', is_flag=True,
              help='''Enable/disable a flatpak app from running detached. Note, the detached flatpak app will still
              retain ENVE sandbox configuration. The "detachment" is only accomplished from a system process point
              of view. Default is disabled.''')
@click.argument('cmd', nargs=-1)
def cli(enve_config: str, enve_use_base_config: bool, enve_use_debug_shell: bool, enve_use_verbose: str,
        enve_enable_detached: bool, cmd: tuple) -> None:
    '''Add doc...'''

    # Set the logging default level and format
    logging.basicConfig(level=logging.DEBUG, format='%(levelname)s: %(message)s')

    # Get the logger instance
    logger = logging.getLogger(__name__)
    # Set the default log level
    logger.setLevel(logging.WARNING)
    # Update the logger verbosity level if specified
    if 'debug' == enve_use_verbose:
        logger.setLevel(logging.DEBUG)
        logger.info('Debug log level set.')
    elif 'info' == enve_use_verbose:
        logger.setLevel(logging.INFO)
        logger.info('Info log level set.')

    if enve_use_base_config:
        errno, enve_vars = [0, {}]
    else:
        # Parse the environment configs
        errno, enve_vars = load_environ_config(enve_config)

    # If no command is specified, start the shell by default
    if not cmd:
        cmd = ('sh',)

    # Run the requested cmd using the project environment only if the project environment load was successful
    if errno == 0:
        errno = run_cmd(list(cmd), enve_vars, enve_use_debug_shell, enve_enable_detached)

    # Exit with error code
    exit(errno)

if __name__ == '__main__':
    cli(prog_name=os.environ['FLATPAK_ID'])
